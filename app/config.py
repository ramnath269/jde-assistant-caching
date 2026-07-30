from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    mcp_server_url: str = Field(..., alias="MCP_SERVER_URL")

    claude_api_key: str = Field(..., alias="CLAUDE_API_KEY")

    claude_model: str = Field(
        default="claude-sonnet-5",
        alias="CLAUDE_MODEL",
    )

    app_name: str = "JDE Assistant"

    app_version: str = "2.0"

    request_timeout: int = 60

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()