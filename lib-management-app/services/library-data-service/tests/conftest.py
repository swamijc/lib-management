"""
Test fixtures — in-memory SQLite database for all library-data-service tests.
No external dependencies; no writes to the real library_management.db.
"""
from __future__ import annotations
import os

# Set required env vars BEFORE any src imports (pydantic-settings reads at module load)
os.environ.setdefault("INTERNAL_SERVICE_KEY", "test-internal-key")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("LOG_LEVEL", "WARNING")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.database import Base, get_db
from src.main import app
from src.models.orm import Library

# ── In-memory test database ───────────────────────────────────────────────────
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(scope="function")
async def test_db():
    """Creates fresh in-memory DB for each test function."""
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(
        bind=engine, class_=AsyncSession,
        expire_on_commit=False, autoflush=False,
    )
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_client(test_db):
    """FastAPI test client with DB dependency overridden to use in-memory DB."""
    async def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def sample_library(test_db: AsyncSession) -> Library:
    """Inserts one test library into the in-memory DB."""
    lib = Library(
        sl_no=1,
        package="com.example:test-lib",
        sdk_name="Test Library",
        platform="Android",
        current_version="1.0.0",
        latest_version="2.0.0",
        update_needed="Mandatory",
        status="Active",
        priority="PI 31",
        ecosystem="mobile",
        framework_language="kotlin",
        alert_priority="Normal",
    )
    test_db.add(lib)
    await test_db.commit()
    await test_db.refresh(lib)
    return lib
