"""Shared fixtures. psycopg async needs the selector loop on Windows."""

import asyncio
import os
import sys
import zipfile
from collections.abc import AsyncIterator
from pathlib import Path

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


# (state, county FIPS, county name): enough counties for the grid label and scorer tests, so
# they never read the git-ignored Gazetteer under data/raw (absent on CI).
_COUNTIES = [
    ("IL", "17031", "Cook County"), ("GA", "13075", "Cook County"),
    ("IL", "17043", "DuPage County"), ("IL", "17097", "Lake County"),
    ("TX", "48201", "Harris County"), ("GA", "13145", "Harris County"),
    ("IN", "18097", "Marion County"), ("OH", "39101", "Marion County"),
    ("IN", "18057", "Hamilton County"), ("OH", "39061", "Hamilton County"),
    ("IN", "18089", "Lake County"), ("OH", "39085", "Lake County"),
    ("IN", "18003", "Allen County"), ("OH", "39003", "Allen County"),
]  # fmt: skip


@pytest.fixture
def gazetteer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the grid tooling at a small Gazetteer file built here."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import label_grid_ambiguity as labels

    rows = ["USPS\tGEOID\tANSICODE\tNAME\tALAND"]
    rows += [f"{usps}\t{geoid}\t0\t{name}\t0" for usps, geoid, name in _COUNTIES]
    path = tmp_path / "counties.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("counties.txt", "\n".join(rows))
    monkeypatch.setattr(labels, "GAZETTEER", path)
    labels.county_geoids.cache_clear()
    yield
    labels.county_geoids.cache_clear()
