from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from kombu import Connection
from qdrant_client import AsyncQdrantClient
from sqlalchemy import text

from src.config.postgres_config import engine
from src.config.qdrant_config import QDRANT_API_KEY, QDRANT_URL
from src.config.rabbitmq_config import RABBITMQ_URL
from src.controllers.chats.main import router as chats_router
from src.controllers.ingest.main import router as ingest_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ------------------------------------------------------------------ #
    # Verify Postgres & create tables if they don't exist
    # ------------------------------------------------------------------ #
    import src.models  # noqa: F401 — registers all models with Base

    from src.models.base import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))

    # ------------------------------------------------------------------ #
    # Qdrant — verify reachability (collection created lazily by worker)
    # ------------------------------------------------------------------ #
    app.state.qdrant = AsyncQdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
    await app.state.qdrant.get_collections()

    # ------------------------------------------------------------------ #
    # RabbitMQ — verify reachability
    # ------------------------------------------------------------------ #
    amqp_conn = Connection(RABBITMQ_URL)
    amqp_conn.connect()
    app.state.amqp = amqp_conn

    yield

    await engine.dispose()
    await app.state.qdrant.close()
    app.state.amqp.release()


app = FastAPI(
    title="GitHub Repository Intelligence Tool",
    description="Ingest any public GitHub repo and query its codebase in natural language.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_router = APIRouter(prefix="/api")


@api_router.get("/health", tags=["health"])
async def health():
    return {"status": "ok"}


api_router.include_router(ingest_router)
api_router.include_router(chats_router)

app.include_router(api_router)
