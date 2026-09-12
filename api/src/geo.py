"""resolve_geography: names to Census `for`/`in`, legality from geography.json.

`geo_levels()[name]` is last-wins and is the wrong table for nesting. Scan
`geo_entries()` and pick the predicate whose `requires` match the `in` clause.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Any, Literal

import httpx
from langchain_core.tools import BaseTool
from pydantic import ConfigDict

from src.census_url import CENSUS_API, CensusURL
from src.retrieval.metadata import GeoLevel
from src.tools import ResolveGeographyInput, ToolResult

# Name, USPS, FIPS. USPS is matched only after a comma so OR does not eat "for".
STATES: tuple[tuple[str, str, str], ...] = (
    ("alabama", "AL", "01"),
    ("alaska", "AK", "02"),
    ("arizona", "AZ", "04"),
    ("arkansas", "AR", "05"),
    ("california", "CA", "06"),
    ("colorado", "CO", "08"),
    ("connecticut", "CT", "09"),
    ("delaware", "DE", "10"),
    ("district of columbia", "DC", "11"),
    ("florida", "FL", "12"),
    ("georgia", "GA", "13"),
    ("hawaii", "HI", "15"),
    ("idaho", "ID", "16"),
    ("illinois", "IL", "17"),
    ("indiana", "IN", "18"),
    ("iowa", "IA", "19"),
    ("kansas", "KS", "20"),
    ("kentucky", "KY", "21"),
    ("louisiana", "LA", "22"),
    ("maine", "ME", "23"),
    ("maryland", "MD", "24"),
    ("massachusetts", "MA", "25"),
    ("michigan", "MI", "26"),
    ("minnesota", "MN", "27"),
    ("mississippi", "MS", "28"),
    ("missouri", "MO", "29"),
    ("montana", "MT", "30"),
    ("nebraska", "NE", "31"),
    ("nevada", "NV", "32"),
    ("new hampshire", "NH", "33"),
    ("new jersey", "NJ", "34"),
    ("new mexico", "NM", "35"),
    ("new york", "NY", "36"),
    ("north carolina", "NC", "37"),
    ("north dakota", "ND", "38"),
    ("ohio", "OH", "39"),
    ("oklahoma", "OK", "40"),
    ("oregon", "OR", "41"),
    ("pennsylvania", "PA", "42"),
    ("rhode island", "RI", "44"),
    ("south carolina", "SC", "45"),
    ("south dakota", "SD", "46"),
    ("tennessee", "TN", "47"),
    ("texas", "TX", "48"),
    ("utah", "UT", "49"),
    ("vermont", "VT", "50"),
    ("virginia", "VA", "51"),
    ("washington", "WA", "53"),
    ("west virginia", "WV", "54"),
    ("wisconsin", "WI", "55"),
    ("wyoming", "WY", "56"),
    ("puerto rico", "PR", "72"),
)

_LEVELS = {
    "county": "county",
    "counties": "county",
    "state": "state",
    "states": "state",
    "place": "place",
    "places": "place",
    "city": "place",
    "cities": "place",
    "tract": "tract",
    "tracts": "tract",
    "zcta": "zip code tabulation area",
    "zctas": "zip code tabulation area",
    "zip": "zip code tabulation area",
}

_WILDCARD = re.compile(
    r"\b(?:all|every|each)\s+(counties|county|places|place|tracts|tract|"
    r"zctas|zcta|zip codes|zips)\s+in\s+(.+)",
    re.IGNORECASE,
)
_COUNTY = re.compile(
    r"\b([A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*)*)\s+count(?:y|ies)\b",
    re.IGNORECASE,
)
# "Washington, DC" must win over the state named Washington.
_DC = re.compile(
    r"district of columbia|\bwashington,\s*d\.?c\.?\b|\bwashington\s+d\.?c\.?\b",
    re.IGNORECASE,
)
_NOISE = frozenset(
    {"population", "of", "the", "in", "a", "an", "how", "many", "people", "what", "is", "are"}
)


class ResolveGeographyResult(ToolResult):
    matches: list[dict[str, str]]
    wildcard: bool
    legal: bool
    detail: str


ListGeographies = Callable[[str, dict[str, str]], list[dict[str, str]]]


def legal_predicate(
    for_level: str,
    in_names: frozenset[str],
    *,
    wildcard: bool,
    entries: list[GeoLevel],
) -> GeoLevel | None:
    """The geography.json row that authorizes this `for`/`in` combination."""
    hits: list[GeoLevel] = []
    for entry in entries:
        if entry.name != for_level:
            continue
        required = frozenset(entry.requires)
        if wildcard:
            parent = entry.wildcard_for
            if parent and parent in in_names and required <= in_names | {parent}:
                if in_names <= required or required <= in_names:
                    hits.append(entry)
            elif not required and not in_names:
                hits.append(entry)
        elif required == in_names:
            hits.append(entry)
    if not hits:
        return None
    return min(hits, key=lambda entry: (len(entry.requires), entry.code))


def find_state(text: str) -> tuple[str, str] | None:
    if _DC.search(text):
        return "district of columbia", "11"
    folded = text.casefold()
    for name, _usps, fips in sorted(STATES, key=lambda row: -len(row[0])):
        if re.search(rf"\b{re.escape(name)}\b", folded):
            return name, fips
    for name, usps, fips in STATES:
        if re.search(rf",\s*{usps}\b", text, re.IGNORECASE):
            return name, fips
    return None


def _token_is_dc(token: str) -> bool:
    """Washington / DC leftovers after place_token, including D.C. and 'Washington DC'."""
    words = token.replace(".", "").replace(",", " ").split()
    return bool(words) and all(word in {"washington", "dc", "d", "c"} for word in words)


def detect_level(text: str) -> str | None:
    folded = text.casefold()
    for alias, level in sorted(_LEVELS.items(), key=lambda item: -len(item[0])):
        if re.search(rf"\b{re.escape(alias)}\b", folded):
            return level
    return None


def place_token(query: str, state_name: str | None) -> str:
    match = _COUNTY.search(query)
    if match and match.group(1).casefold() not in {"all", "every", "each"}:
        return match.group(1).casefold()
    text = re.sub(r",\s*[A-Z]{2}\b", " ", query)
    for word in ("county", "counties", "city", "cities", "place", "places", "cdp", "town"):
        text = re.sub(rf"\b{word}\b", " ", text, flags=re.IGNORECASE)
    leftover = re.sub(r"[,\s]+", " ", text).strip().casefold()
    if not state_name:
        return leftover
    without_state = re.sub(rf"\b{re.escape(state_name)}\b", " ", leftover).strip()
    without_state = re.sub(r"[,\s]+", " ", without_state).strip()
    significant = " ".join(word for word in without_state.split() if word not in _NOISE)
    if significant:
        return significant
    return state_name if state_name in leftover else leftover


def filter_rows(token: str, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Match the place/county head (before the comma), never the state suffix."""
    if not token:
        return []
    hits: list[dict[str, str]] = []
    for row in rows:
        head = row["name"].casefold().split(",", 1)[0]
        if (
            head == token
            or head.startswith(f"{token} ")
            or re.search(rf"\b{re.escape(token)}\b", head)
        ):
            hits.append(row)
    return hits


def list_census_names(
    for_level: str,
    in_parts: dict[str, str],
    *,
    dataset: str = "acs5",
    vintage: int = 2024,
    key: str = "",
) -> list[dict[str, str]]:
    """NAME listing from the Census API. One request; `in=state:*` is legal."""
    query = f"get=NAME,GEO_ID&for={for_level}:*"
    if in_parts:
        query += "&in=" + " ".join(f"{k}:{v}" for k, v in in_parts.items())
    built = CensusURL(f"{CENSUS_API}/{vintage}/acs/{dataset}?{query}")
    try:
        response = httpx.get(built.with_key(key), timeout=60.0)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError, TypeError):
        raise RuntimeError(f"geography listing failed; URL {built}") from None
    header, *body = payload
    rows: list[dict[str, str]] = []
    for raw in body:
        rec = {str(k): str(v) for k, v in zip(header, raw, strict=False)}
        code = rec.get(for_level, "*")
        parents = {name: rec[name] for name in rec if name not in {"NAME", "GEO_ID", for_level}}
        rows.append(
            {
                "name": rec.get("NAME", ""),
                "level": for_level,
                "for": f"{for_level}:{code}",
                "in": " ".join(f"{k}:{v}" for k, v in parents.items()),
                "geoid": rec.get("GEO_ID", ""),
            }
        )
    return rows


class ResolveGeographyTool(BaseTool):
    name: str = "resolve_geography"
    description: str = "Turn a place name or 'all counties in X' into Census for/in codes."
    args_schema: type[ResolveGeographyInput] = ResolveGeographyInput
    response_format: Literal["content_and_artifact"] = "content_and_artifact"
    model_config = ConfigDict(arbitrary_types_allowed=True)

    list_geographies: ListGeographies
    entries: list[GeoLevel]

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("resolve_geography is async-only")

    async def _arun(
        self, query: str, level: str | None = None
    ) -> tuple[str, ResolveGeographyResult]:
        wildcard_match = _WILDCARD.search(query)
        wildcard = wildcard_match is not None
        parent_text = wildcard_match.group(2) if wildcard_match else query
        state = find_state(parent_text)
        for_level = level or (detect_level(wildcard_match.group(1) if wildcard_match else query))
        if for_level is None:
            token = place_token(query, state[0] if state else None)
            dc_as_state = _token_is_dc(token) if state is not None and state[1] == "11" else False
            if state is not None and (token in {"", state[0]} or dc_as_state):
                for_level = "state"
            else:
                for_level = "place"
        in_parts: dict[str, str] = {}
        if for_level != "state" and state is not None:
            in_parts["state"] = state[1]
        if for_level == "state" and state is not None:
            predicate = legal_predicate("state", frozenset(), wildcard=False, entries=self.entries)
            match = {
                "name": state[0].title(),
                "level": "state",
                "for": f"state:{state[1]}",
                "in": "",
                "geoid": f"0400000US{state[1]}",
            }
            result = ResolveGeographyResult(
                matches=[match], wildcard=False, legal=predicate is not None, detail=""
            )
            return f"1 geography: {match['for']}", result

        parent_level = detect_level(parent_text) if wildcard else None
        extra = (
            {parent_level}
            if parent_level and parent_level != for_level and parent_level not in in_parts
            else set()
        )
        in_names = frozenset(in_parts) | extra
        predicate = legal_predicate(
            for_level, in_names, wildcard=wildcard or not in_parts, entries=self.entries
        )
        # National listing uses state:* when the level needs a state and none was named.
        list_in = dict(in_parts)
        state_wildcard = legal_predicate(
            for_level, frozenset({"state"}), wildcard=True, entries=self.entries
        )
        if (
            not list_in
            and for_level not in {"state", "zip code tabulation area", "us"}
            and state_wildcard
        ):
            list_in = {"state": "*"}
            if predicate is None:
                predicate = state_wildcard

        if wildcard:
            if predicate is None:
                result = ResolveGeographyResult(
                    matches=[],
                    wildcard=True,
                    legal=False,
                    detail=f"{for_level} with in={dict(in_parts)} is not a legal combination",
                )
                return result.detail, result
            parent = " ".join(f"{k}:{v}" for k, v in in_parts.items())
            match = {
                "name": query.strip(),
                "level": for_level,
                "for": f"{for_level}:*",
                "in": parent,
                "geoid": "",
            }
            result = ResolveGeographyResult(matches=[match], wildcard=True, legal=True, detail="")
            return f"wildcard {match['for']} {match['in']}".strip(), result

        rows = await asyncio.to_thread(self.list_geographies, for_level, list_in)
        token = place_token(query, state[0] if state else None)
        matched = filter_rows(token, rows)
        if not matched and token:
            # Whole-question queries still contain the place as a substring.
            matched = filter_rows(token.split()[-1], rows) if token.split() else []
        legal = predicate is not None
        if not legal:
            detail = f"{for_level} with in={dict(in_parts)} is not a legal combination"
        elif not matched:
            detail = f"no {for_level} matched {query!r}"
        else:
            detail = ""
        result = ResolveGeographyResult(
            matches=matched, wildcard=False, legal=legal and bool(matched), detail=detail
        )
        summary = (
            f"{len(matched)} {for_level} candidates"
            if len(matched) != 1
            else f"1 geography: {matched[0]['for']} {matched[0].get('in', '')}".strip()
        )
        if detail:
            summary = detail
        return summary, result
