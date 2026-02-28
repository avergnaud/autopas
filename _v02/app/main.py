"""PAS Assistant — FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import load_config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load configuration at startup."""
    load_config()
    logger.info("PAS Assistant started")
    yield
    logger.info("PAS Assistant stopped")


app = FastAPI(
    title="PAS Assistant",
    description="API REST — Plans d'Assurance Sécurité",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/api/health")
async def health() -> dict:
    """Health check — no authentication required."""
    return {"status": "ok"}
