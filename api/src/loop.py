"""Event loop factory for Windows. psycopg async cannot run on the default Proactor loop.

uv run uvicorn src.main:app --loop src.loop:selector_factory
"""

import asyncio


def selector_factory() -> asyncio.AbstractEventLoop:
    return asyncio.SelectorEventLoop()
