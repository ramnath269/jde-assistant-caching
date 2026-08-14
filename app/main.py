from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI

from app.api.auth import router as auth_router
from app.api.health import router as health_router
from app.api.process import router as process_router
from app.api.tools import router as tools_router
from app.api.conversation import router as conversation_router
from app.core.logger import logger
from app.services.dependencies import (
    claude_service,
    jde_auth_client,
    mcp_client,
    tool_manager,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("1. Starting lifespan")

    print("2. Before MCP initialize")
    await mcp_client.initialize()
    print("3. After MCP initialize")

    print("4. Before tool load")
    await tool_manager.load()
    print("5. After tool load")

    print("6. Before Claude initialize")
    await claude_service.initialize()
    print("7. After Claude initialize")

    yield

    print("8. Shutdown")
    await mcp_client.close()
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