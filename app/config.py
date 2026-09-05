from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):

    mcp_server_url: str = Field(..., alias="MCP_SERVER_URL")

    # Same host as mcp_server_url unless JDE_MCP_URL is set separately -
    # the JSON-RPC tools/* endpoint and the REST /auth/* endpoints
    # currently live on the same MCP server.
    jde_mcp_url: str | None = Field(default=None, alias="JDE_MCP_URL")

    jde_mcp_client_secret: str = Field(..., alias="JDE_MCP_CLIENT_SECRET")

    claude_api_key: str = Field(..., alias="CLAUDE_API_KEY")

    claude_model: str = Field(
        default="claude-haiku-4-5-20251001",
        alias="CLAUDE_MODEL",
    )

    app_name: str = "JDE Assistant"

    app_version: str = "2.0"

    request_timeout: int = 60

    class Config:
        env_file = ".env"
        extra = "ignore"

    @model_validator(mode="after")
    def _default_jde_mcp_url(self) -> "Settings":
        if not self.jde_mcp_url:
            self.jde_mcp_url = self.mcp_server_url
        return self


settings = Settings()