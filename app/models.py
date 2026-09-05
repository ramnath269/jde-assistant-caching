from pydantic import BaseModel, Field
from typing import Any


class ChatRequest(BaseModel):
    prompt: str = Field(..., min_length=1)
    conversation_id: str | None = Field(None, min_length=1)


class ChatResponse(BaseModel):
    response: str
    tool_calls: list[dict[str, Any]]
    usage: dict[str, Any]
    conversation_id: str | None = None

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


class LoginRequest(BaseModel):

    username: str = Field(..., min_length=1)

    # Base64-encoded by the login page; decoded in app/api/auth.py
    # before it is handed to the MCP server.
    password: str = Field(..., min_length=1)

    environment: str = Field(..., min_length=1)


class LoginResponse(BaseModel):

    session_token: str

    username: str

    environment: str