"""The level the model states is the level whose `for=` clause is built, whatever the query says."""

from __future__ import annotations

from ask_fixtures import _tools
from src.ask import ExecutionRecord, dispatch


async def test_a_stated_state_level_builds_a_state_for_clause_for_a_county_worded_query() -> None:
    record = ExecutionRecord(question="population of Texas")
    tools = _tools(record)
    await dispatch(tools["search_tables"], {"id": "1", "args": {"question": "population"}}, record)
    call = {"id": "2", "args": {"level": "state", "query": "Harris County, Texas"}}
    await dispatch(tools["resolve_geography"], call, record)
    await dispatch(tools["build_url"], {"id": "3", "args": {"table_id": "B01003"}}, record)
    assert record.url is not None and record.url.for_level() == "state"
