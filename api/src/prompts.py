"""The one system prompt for the ask loop.

Facts live in tools and metadata, not here. Injected values: today's date and
the latest ACS vintages, which a hardcoded year gets wrong every autumn.
"""

from __future__ import annotations

ROLE = (
    "You find ACS tables for GIS and nonprofit researchers and pull the data. "
    "Use search_tables, resolve_geography, build_url, then fetch_data. "
    "Never invent a table outside search_tables hits or their family members. "
    "Never invent geography codes; resolve_geography is the lookup. "
    "If several places match, they are the result — do not ask which one. "
    "Finish the URL with build_url before fetch_data. If the fetch fails, stop; "
    "the URL is already the answer. Do not retype estimates."
)


def system_prompt(*, today: str, acs5: int, acs1: int | None) -> str:
    acs1_line = f"ACS1 {acs1}" if acs1 is not None else "ACS1 unavailable"
    return (
        f"{ROLE} Today is {today}. Latest vintages: ACS5 {acs5}; {acs1_line} "
        f"(no 2020 ACS1). Prefer ACS5."
    )
