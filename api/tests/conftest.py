"""Shared fixtures. psycopg async needs the selector loop on Windows."""

import asyncio
import os
import sys
from collections.abc import AsyncIterator

import pytest
from psycopg_pool import AsyncConnectionPool
from src import store

URL = os.environ.get("DATABASE_URL")


@pytest.fixture(scope="session")
def event_loop_policy() -> asyncio.AbstractEventLoopPolicy:
    if sys.platform == "win32":
        return asyncio.WindowsSelectorEventLoopPolicy()
    return asyncio.DefaultEventLoopPolicy()


@pytest.fixture
async def pool() -> AsyncIterator[AsyncConnectionPool]:
    if not URL:
        if os.environ.get("CI") == "true":
            pytest.fail("DATABASE_URL must be set in CI; store tests never skip there")
        pytest.skip("DATABASE_URL unset; start Postgres per the README to run store tests")
    opened = await store.open_pool(URL)
    yield opened
    await opened.close()
