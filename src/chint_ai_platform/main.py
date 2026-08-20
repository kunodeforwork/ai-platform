"""FastAPI application factory and ASGI entry point."""

from fastapi import FastAPI

from chint_ai_platform.api import router as agent_runs_router


def create_app() -> FastAPI:
    """Create a configured FastAPI application."""
    application = FastAPI(title="CHINT Enterprise AI Agent Platform", version="0.1.0")
    application.include_router(agent_runs_router)

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
