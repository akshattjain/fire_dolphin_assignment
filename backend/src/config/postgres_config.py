import os

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/fire_dolphin",
)

DATABASE_SYNC_URL = os.getenv(
    "DATABASE_SYNC_URL",
    "postgresql+psycopg2://postgres:postgres@localhost:5432/fire_dolphin",
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Synchronous engine used by Celery workers (which cannot run in an async context)
sync_engine = create_engine(DATABASE_SYNC_URL, echo=False, pool_pre_ping=True)
sync_session_factory = sessionmaker(sync_engine, expire_on_commit=False)
