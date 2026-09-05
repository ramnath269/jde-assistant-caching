from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.process import router as process_router
from app.api.tools import router as tools_router
from app.api.conversation import router as conversation_router
from app.core.logger import logger
from app.services.dependencies import jde_auth_client, session_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # No MCP session is established here anymore: the MCP server gates its
    # whole /mcp surface behind OAuth, so there is nothing to connect as
    # until a real user logs in via /login. Each login builds its own
    # MCPClient + ToolManager (see app/api/auth.py).
    logger.info("Starting up.")

    yield

    logger.info("Shutting down.")
    await session_manager.close_all()
    await jde_auth_client.close()


app = FastAPI(
    title="JDE Assistant",
    version="1.0.0",
    lifespan=lifespan,
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "*",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(health_router)
app.include_router(process_router)
app.include_router(tools_router)
app.include_router(conversation_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
