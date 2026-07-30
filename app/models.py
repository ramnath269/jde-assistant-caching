from pydantic import BaseModel, Field
from typing import Any


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1)


class ChatResponse(BaseModel):
    response: str
    tool_calls: list[dict[str, Any]]
    usage: dict[str, Any]

class MCPTool(BaseModel):

    name: str

    description: str

    inputSchema: dict = {}


class PromptRequest(BaseModel):

    prompt: str


class PromptResponse(BaseModel):

    response: str

    token_usage: dict

    tools_used: list[str]


class ToolCallRequest(BaseModel):

    tool_name: str

    parameters: dict = {}