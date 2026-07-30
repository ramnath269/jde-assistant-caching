from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from anthropic import AsyncAnthropic
import json
from anthropic.types import TextBlock, ToolUseBlock
from app.config import settings
from app.core.logger import logger
from app.models import MCPTool
from app.services.mcp_client import MCPClient
from app.services.tool_manager import ToolManager
import json
import time
import uuid

from app.core.metrics_logger import metrics_logger

SYSTEM_PROMPT = """
You are JD Edwards EnterpriseOne AI Assistant.

You help users by answering questions and by using the available MCP tools
whenever external information or actions are required.

Rules:

- Prefer using tools over making assumptions.
- Never invent tool outputs.
- If multiple tools are required, use them.
- Keep responses concise unless the user asks for details.
- Format tables using markdown.
- Explain failures clearly.
""".strip()


# ---------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------


@dataclass
class ClaudeMetrics:

    requests: int = 0

    input_tokens: int = 0

    output_tokens: int = 0

    cache_creation_tokens: int = 0

    cache_read_tokens: int = 0

    tool_calls: int = 0

    failed_tool_calls: int = 0


# ---------------------------------------------------------------------
# Claude Service
# ---------------------------------------------------------------------


class ClaudeService:

    def __init__(
        self,
        tool_manager: ToolManager,
    ) -> None:

        self._tool_manager = tool_manager

        self._client = AsyncAnthropic(
            api_key=settings.claude_api_key,
        )

        #
        # Immutable after initialize()
        #
        self._tools: tuple[dict[str, Any], ...] = ()

        self._system_prompt: list[dict[str, Any]] = []

        self._metrics = ClaudeMetrics()

        self._initialized = False

    async def initialize(self) -> None:

      if self._initialized:
          return

      logger.info("Initializing Claude service...")

      all_tools = self._tool_manager.all()
      # selected_tools = all_tools[:5]

      tools = [
          self._convert_tool(tool)
          for tool in all_tools
      ]

      # Add a cache checkpoint after the last tool
      if tools:
          tools[-1]["cache_control"] = {
              "type": "ephemeral"
          }

      self._tools = tuple(tools)

      self._system_prompt = [
          {
              "type": "text",
              "text": SYSTEM_PROMPT,
              "cache_control": {
                  "type": "ephemeral"
              },
          }
      ]

      self._initialized = True

      logger.info(
          "Claude initialized with %d tools.",
          len(self._tools),
      )

    @staticmethod
    def _find_tool_calls(response) -> list[ToolUseBlock]:
        return [
            block
            for block in response.content
            if isinstance(block, ToolUseBlock)
        ]

    def _convert_tool(
      self,
      tool: MCPTool,
  ) -> dict[str, Any]:

      return {
          "name": tool.name,
          "description": tool.description,
          "input_schema": tool.inputSchema,
      }

    def _update_metrics(
        self,
        response,
    ) -> None:

        usage = response.usage
        usage = response.usage

        cached = usage.cache_read_input_tokens
        processed = usage.input_tokens

        total = cached + processed

        hit_rate = (cached / total * 100) if total else 0

        logger.info(
            "Cache hit: %.1f%% (%d/%d tokens)",
            hit_rate,
            cached,
            total,
        )

        self._metrics.requests += 1

        self._metrics.input_tokens += usage.input_tokens

        self._metrics.output_tokens += usage.output_tokens

        self._metrics.cache_creation_tokens += getattr(
            usage,
            "cache_creation_input_tokens",
            0,
        )

        self._metrics.cache_read_tokens += getattr(
            usage,
            "cache_read_input_tokens",
            0,
        )

    def metrics(self) -> dict:

      return asdict(self._metrics)


    def reset_metrics(self) -> None:

      self._metrics = ClaudeMetrics()

    async def _call_claude(
        self,
        request_id: str,
        messages: list[dict[str, Any]],
    ):

        logger.info("Sending request to Claude...")

        response = await self._client.messages.create(

            model=settings.claude_model,

            max_tokens=4096,

            system=self._system_prompt,

            tools=list(self._tools),

            messages=messages,
        )

        tool_name = None

        if response.stop_reason == "tool_use":
            tool_name = response.content[-1].name

        self._log_metrics(
            request_id=request_id,
            # request_type="initial",
            usage=response.usage,
            tool_name=tool_name,
        )

        self._update_metrics(response)

        return response

    async def _execute_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:

        self._metrics.tool_calls += 1

        try:
            return await self._tool_manager.execute(
                tool_name,
                arguments,
            )

        except Exception as ex:
            self._metrics.failed_tool_calls += 1
            logger.exception("Tool execution failed")

            return {
                "success": False,
                "error": str(ex),
            }

    @staticmethod
    def _extract_text(response) -> str:

        text = []

        for block in response.content:

            if isinstance(block, TextBlock):
                text.append(block.text)

        return "\n".join(text).strip()

    async def process(
        self,
        prompt: str,
    ) -> dict[str, Any]:
        if not self._initialized:
            raise RuntimeError(
                "ClaudeService.initialize() was not called."
            )

        request_id = str(uuid.uuid4())
        messages = [
            {
                "role": "user",
                "content": prompt,
            }
        ]

        executed_tools = []

        while True:

            response = await self._call_claude(request_id, messages)

            tool_calls = self._find_tool_calls(response)

            #
            # Claude is finished
            #
            logger.info("Usage: %s", response.usage)
            if not tool_calls:

                return {

                    "response": self._extract_text(response),

                    "tool_calls": executed_tools,

                    "usage": response.usage.model_dump(),

                }

            #
            # Add Claude message
            #
            messages.append(
                {
                    "role": "assistant",
                    "content": response.content,
                }
            )

            tool_results = []

            for tool in tool_calls:

                logger.info(
                    "Claude requested tool '%s'",
                    tool.name,
                )

                result = await self._execute_tool(
                    tool.name,
                    tool.input,
                )

                executed_tools.append(
                    {
                        "tool": tool.name,
                        "arguments": tool.input,
                    }
                )

                #
                # Claude requires JSON/string content
                #
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": tool.id,
                        "content": json.dumps(
                            result,
                            default=str,
                        ),
                    }
                )

            #
            # Give tool results back to Claude
            #
            messages.append(
                {
                    "role": "user",
                    "content": tool_results,
                }
            )

    async def reload_tools(self) -> None:

        logger.info("Reloading Claude tool definitions...")

        await self._tool_manager.reload()

        tools = self._tool_manager.all()

        self._tools = tuple(
            self._convert_tool(tool)
            for tool in tools
        )

        logger.info(
            "Reloaded %d Claude tools.",
            len(self._tools),
        )

    def health(self) -> dict:

        return {

            "initialized": self._initialized,

            "tool_count": len(self._tools),

            "metrics": self.metrics(),
        }

    async def shutdown(self):

      logger.info("Shutting down Claude service...")

      await self._client.close()

    def _log_metrics(
      self,
      request_id: str,
      usage,
      tool_name: str | None = None,
  ):
      cached = usage.cache_read_input_tokens
      processed = usage.input_tokens

      total = cached + processed

      hit_rate = (
          cached / total * 100
          if total else 0
      )

      metrics = {
          "request_id": request_id,
          "timestamp": time.time(),
          "tool": tool_name,
          "input_tokens": usage.input_tokens,
          "output_tokens": usage.output_tokens,
          "cache_read_tokens": usage.cache_read_input_tokens,
          "cache_creation_tokens": usage.cache_creation_input_tokens,
          "cache_hit_percent": round(hit_rate, 2),
      }

      metrics_logger.info(json.dumps(metrics))