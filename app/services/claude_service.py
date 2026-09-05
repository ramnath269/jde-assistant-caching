from __future__ import annotations
from dataclasses import asdict, dataclass
from typing import Any
import pprint
from anthropic import AsyncAnthropic
import json
from anthropic.types import TextBlock, ToolUseBlock
from app.config import settings
from app.core.logger import logger
from app.models import MCPTool
from app.services.conversation_manager import ConversationManager
from app.services.mcp_client import MCPAuthExpiredError
from app.services.session_manager import SessionManager, UserSession
import json
import time
import uuid

from app.core.metrics_logger import metrics_logger

#
# Tools that must never be exposed to Claude (e.g. because they take
# raw credentials).
#
HIDDEN_TOOLS = {"jde_get_token"}


class AuthExpiredError(Exception):
    """Raised when the MCP server reports the user's bearer token is dead."""


def convert_tool(tool: MCPTool) -> dict[str, Any]:
    return {
        "name": tool.name,
        "description": tool.description,
        "input_schema": tool.inputSchema,
    }


def build_claude_tools(tools: list[MCPTool]) -> tuple[dict[str, Any], ...]:
    """
    Turn one user's RBAC-filtered tool catalog into the Claude tools=[...]
    shape. Called at login (and again on /tools/reload) - NOT once globally,
    since different users can have a different tool set here.
    """

    converted = [
        convert_tool(tool)
        for tool in tools
        if tool.name not in HIDDEN_TOOLS
    ]

    # Add a cache checkpoint after the last tool
    if converted:
        converted[-1] = {**converted[-1], "cache_control": {"type": "ephemeral"}}

    return tuple(converted)


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
        conversation_manager: ConversationManager,
        session_manager: SessionManager,
    ) -> None:

        self._conversation_manager = conversation_manager
        self._session_manager = session_manager

        self._client = AsyncAnthropic(
            api_key=settings.claude_api_key,
        )

        self._system_prompt: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": SYSTEM_PROMPT,
                "cache_control": {
                    "type": "ephemeral"
                },
            }
        ]

        self._metrics = ClaudeMetrics()

    @staticmethod
    def _find_tool_calls(response) -> list[ToolUseBlock]:
        return [
            block
            for block in response.content
            if isinstance(block, ToolUseBlock)
        ]

    def _update_metrics(
        self,
        response,
    ) -> None:

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
        tools: tuple[dict[str, Any], ...],
    ):

        logger.info("Sending request to Claude...")

        pprint.pp(messages)

        response = await self._client.messages.create(

            model=settings.claude_model,

            max_tokens=4096,

            system=self._system_prompt,

            tools=list(tools),

            messages=messages,
        )

        tool_name = None

        if response.stop_reason == "tool_use":
            tool_name = response.content[-1].name

        self._log_metrics(
            request_id=request_id,
            usage=response.usage,
            tool_name=tool_name,
        )

        self._update_metrics(response)

        return response

    async def _execute_tool(
        self,
        session: UserSession,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:

        self._metrics.tool_calls += 1

        try:
            return await session.tool_manager.execute(
                tool_name,
                arguments,
            )

        except MCPAuthExpiredError:
            # Let this propagate to process(), which turns it into
            # AuthExpiredError - it is not a tool failure, it is "this whole
            # session needs a fresh login", so it must not be swallowed into
            # a {"success": False} result the model would just retry.
            raise

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
        session: UserSession,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        conversation_id = conversation_id or str(uuid.uuid4())

        self._conversation_manager.create_if_not_exists(conversation_id)
        self._session_manager.add_conversation(session.username, conversation_id)

        request_id = str(uuid.uuid4())

        user_message = {
            "role": "user",
            "content": prompt,
        }

        self._conversation_manager.append(conversation_id, user_message)

        messages = self._conversation_manager.get_messages(conversation_id)


        executed_tools = []

        while True:
            response = await self._call_claude(request_id, messages, session.claude_tools)

            tool_calls = self._find_tool_calls(response)

            #
            # Claude is finished
            #
            logger.info("Usage: %s", response.usage)
            if not tool_calls:

                assistant_message = {
                    "role": "assistant",
                    "content": self._extract_text(response),
                }

                self._conversation_manager.append(
                    conversation_id,
                    assistant_message,
                )

                return {
                    "conversation_id": conversation_id,

                    "response": assistant_message["content"],

                    "tool_calls": executed_tools,

                    "usage": response.usage.model_dump(),

                }

            assistant_message = {
                "role": "assistant",
                "content": response.content,
            }

            self._conversation_manager.append(conversation_id, assistant_message)

            tool_results = []

            for tool in tool_calls:

                logger.info(
                    "Claude requested tool '%s'",
                    tool.name,
                )

                try:
                    result = await self._execute_tool(
                        session,
                        tool.name,
                        tool.input,
                    )
                except MCPAuthExpiredError:
                    logger.warning(
                        "MCP bearer token expired for user '%s' during tool '%s'.",
                        session.username,
                        tool.name,
                    )
                    await session.mcp_client.close()
                    self._session_manager.logout(session.session_token)

                    raise AuthExpiredError(
                        "Your JDE session has expired. Please log in again."
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
            tool_message = {
                "role": "user",
                "content": tool_results,
            }
            self._conversation_manager.append(conversation_id, tool_message)
            messages = self._conversation_manager.get_messages(
                conversation_id
            )

    def health(self) -> dict:

        return {

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
