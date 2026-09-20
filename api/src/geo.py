"""resolve_geography: names to Census `for`/`in`, legality from geography.json."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.tools import BaseTool
from pydantic import ConfigDict

from src.compare import parentless_tracts, unsupported_wildcard
from src.contract import GeoSpec, clause_codes
from src.geo_list import (
    filter_rows,
    find_state,
    named_rows,
    rank_matches,
    token_is_dc,
)
from src.retrieval.metadata import GeoLevel
from src.tools import ResolveGeographyInput, ToolResult

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
    "block group": "block group",
    "block groups": "block group",
    "zcta": "zip code tabulation area",
    "zctas": "zip code tabulation area",
    "zip": "zip code tabulation area",
}

_WILDCARD = re.compile(
    r"\b(?:all|every|each)\s+(counties|county|places|place|tracts|tract|"
    r"block groups|block group|"
    r"zctas|zcta|zip codes|zips)\s+in\s+(.+)",
    re.IGNORECASE,
)
_WITHIN = re.compile(
    r"\b(?:census\s+)?(tracts?|block groups?|zctas?|zip codes?|zips?|zip|"
    r"counties|county|places?|cities|city)(?:\s+\d{5})?\s+(?:within|inside)\s+(?:the\s+)?(.+)",
    re.IGNORECASE,
)
_COUNTY = re.compile(
    r"\b([A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*)*)\s+count(?:y|ies)\b",
    re.IGNORECASE,
)
_VERSUS = re.compile(r"\s+(?:versus|compared to|vs\.?)\s+", re.IGNORECASE)
_COMPARE_TO = re.compile(r"(?is)^\s*compare\b(.+)\bto\b(.+)$")
_NOISE = frozenset(
    {"population", "of", "the", "in", "a", "an", "how", "many", "people", "what", "is", "are"}
)
_AVERAGE = frozenset({"average", "avg", "mean"})
_US = re.compile(r"\b(?:u\.?s\.?a?\.?|united states|nationwide|the nation)\b", re.I)
_HAS_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")
_IN_PLACE = re.compile(
    r"\b(?:in|for)\s+(?!((?:19|20)\d{2})\b)([A-Za-z][A-Za-z.'-]*)",
    re.I,
)


class ResolveGeographyResult(ToolResult):
    specs: list[GeoSpec]
    wildcard: bool
    legal: bool
    detail: str
    nested: bool = True
    compare: bool = False


ListGeographies = Callable[..., list[dict[str, str]]]
GeoTable = Callable[[str, int], list[GeoLevel]]
LatestVintage = Callable[[str], int]


def _fail(
    detail: str, *, wildcard: bool = False, nested: bool = True
) -> tuple[str, ResolveGeographyResult]:
    hit = ResolveGeographyResult(
        specs=[], wildcard=wildcard, legal=False, detail=detail, nested=nested
    )
    return detail, hit


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
        parent = entry.wildcard_for
        allowed = required | ({parent} if parent else frozenset())
        nested = bool(parent) and parent in in_names and in_names <= allowed
        nested = nested and required <= in_names | {parent}
        wild_ok = wildcard and (nested or (not required and not in_names))
        if wild_ok or (not wildcard and required == in_names):
            hits.append(entry)
    return min(hits, key=lambda e: (len(e.requires), e.code)) if hits else None


def nests_in(child: str, parent: str, entries: list[GeoLevel]) -> bool:
    return any(
        e.name == child and (parent in e.requires or parent == e.wildcard_for) for e in entries
    )


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


def split_versus(query: str) -> tuple[str, str] | None:
    parts = [part.strip() for part in _VERSUS.split(query, maxsplit=1)]
    if len(parts) == 2 and all(parts):
        return parts[0], parts[1]
    match = _COMPARE_TO.match(query)
    if match:
        left, right = match.group(1).strip(), match.group(2).strip()
        if left and right:
            return left, right
    return None


def _nation(query: str) -> bool:
    if _WILDCARD.search(query) or _WITHIN.search(query):
        return False
    if detect_level(query) is not None or find_state(query) is not None:
        return False
    if any(match.group(2).casefold() not in _NOISE for match in _IN_PLACE.finditer(query)):
        return False
    if re.search(r"\bof\s+[A-Z][a-z]", query):
        return False
    leftover = re.sub(r"[^A-Za-z]+", " ", _HAS_YEAR.sub(" ", query)).strip()
    if not leftover:
        return False
    return bool(_US.search(query) or _HAS_YEAR.search(query))


class ResolveGeographyTool(BaseTool):
    name: str = "resolve_geography"
    description: str = "Turn a place name or 'all counties in X' into Census for/in codes."
    args_schema: type[ResolveGeographyInput] = ResolveGeographyInput
    response_format: Literal["content_and_artifact"] = "content_and_artifact"
    model_config = ConfigDict(arbitrary_types_allowed=True)

    list_geographies: ListGeographies
    geo_table: GeoTable
    latest_vintage: LatestVintage

    def _run(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("resolve_geography is async-only")

    async def _arun(
        self,
        query: str,
        level: str | None = None,
        dataset: str = "acs5",
        vintage: int | None = None,
    ) -> tuple[str, ResolveGeographyResult]:
        year = vintage if vintage is not None else self.latest_vintage(dataset)
        try:
            entries = await asyncio.to_thread(self.geo_table, dataset, year)
        except (OSError, ValueError, TypeError, KeyError):
            return _fail(f"no geography metadata for {dataset} {year}")
        packed = parentless_tracts(query, dataset=dataset, year=year)
        if packed:
            detail, specs = packed
            hit = ResolveGeographyResult(
                specs=specs, wildcard=False, legal=False, detail=detail, compare=True
            )
            return detail, hit
        sides = split_versus(query)
        if sides:
            hits = [(await self._resolve(side, None, dataset, year, entries))[1] for side in sides]
            if all(hit.legal and hit.specs for hit in hits):
                specs = [hit.specs[0] for hit in hits]
                extra = [row for hit in hits for row in hit.specs[1:]]
                result = ResolveGeographyResult(
                    specs=specs + extra, wildcard=False, legal=True, detail="", compare=True
                )
                return f"2 geographies: {specs[0].for_spec} vs {specs[1].for_spec}", result
            for hit in hits:
                if hit.legal and hit.specs:
                    return f"1 geography: {hit.specs[0].for_spec}", hit
        return await self._resolve(query, level, dataset, year, entries)

    async def _resolve(
        self,
        query: str,
        level: str | None,
        dataset: str,
        year: int,
        entries: list[GeoLevel],
    ) -> tuple[str, ResolveGeographyResult]:
        if level is None and _nation(query):
            spec = GeoSpec(
                level="us",
                name="United States",
                for_spec="us:1",
                geoid="0100000US",
                dataset=dataset,
                vintage=year,
            )
            result = ResolveGeographyResult(specs=[spec], wildcard=False, legal=True, detail="")
            return f"1 geography: {spec.for_spec}", result
        wildcard_match = _WILDCARD.search(query) or _WITHIN.search(query)
        wildcard = wildcard_match is not None
        parent_text = wildcard_match.group(2) if wildcard_match else query
        state = find_state(parent_text)
        known = {entry.name for entry in entries}
        if level:
            for_level = _LEVELS.get(level.casefold()) or (level if level in known else None)
            if for_level is None:
                return _fail(f"unknown geography level {level!r}")
        else:
            for_level = detect_level(wildcard_match.group(1) if wildcard_match else query)
        if for_level is None:
            token = place_token(query, state[0] if state else None)
            dc_as_state = token_is_dc(token) if state is not None and state[1] == "11" else False
            average = token in _AVERAGE
            if state is not None and (token in {"", state[0]} or dc_as_state or average):
                for_level = "state"
            else:
                for_level = "place"
        in_parts: dict[str, str] = {}
        parent_level = detect_level(parent_text) if wildcard else None
        if for_level != "state" and state is not None:
            host = place_token(parent_text, state[0]) if wildcard else state[0]
            named_parent = bool(parent_level) and parent_level not in {for_level, "state"}
            if host in {"", state[0], "state"} or named_parent:
                if nests_in(for_level, "state", entries):
                    in_parts["state"] = state[1]
                elif host in {"", state[0], "state"}:
                    return _fail(
                        f"{for_level} does not nest in state ({parent_text.strip()})",
                        wildcard=wildcard,
                        nested=False,
                    )
        if for_level == "state" and state is not None:
            if legal_predicate("state", frozenset(), wildcard=False, entries=entries) is None:
                return _fail("state with in={} is not a legal combination")
            spec = GeoSpec(
                level="state",
                name=state[0].title(),
                for_spec=f"state:{state[1]}",
                geoid=f"0400000US{state[1]}",
                dataset=dataset,
                vintage=year,
            )
            result = ResolveGeographyResult(specs=[spec], wildcard=False, legal=True, detail="")
            return f"1 geography: {spec.for_spec}", result

        leftover_parents: list[dict[str, str]] = []
        extra: set[str] = set()
        if parent_level and parent_level != for_level and parent_level not in in_parts:
            extra.add(parent_level)
        if extra:
            allowed = all(nests_in(for_level, parent, entries) for parent in extra)
            parents = ", ".join(sorted(extra))
            if not allowed:
                return _fail(
                    f"{for_level} does not nest in {parents} ({parent_text.strip()})",
                    wildcard=wildcard,
                    nested=False,
                )
            for parent in list(extra):
                list_in = dict(in_parts)
                if not list_in and parent == "county":
                    list_in = {"state": "*"}
                if not list_in:
                    return _fail(
                        f"{for_level} nested in unresolved {parents}",
                        wildcard=wildcard,
                        nested=True,
                    )
                rows = await asyncio.to_thread(
                    self.list_geographies, parent, list_in, dataset=dataset, vintage=year
                )
                token = place_token(parent_text, state[0] if state else None)
                matched = rank_matches(filter_rows(token, rows))
                if not matched:
                    return _fail(
                        f"{for_level} nested in unresolved {parents}",
                        wildcard=wildcard,
                        nested=True,
                    )
                pick = matched[0]
                leftover_parents.extend(matched[1:])
                in_parts.update(clause_codes(pick.get("in", "")))
                parsed = clause_codes(pick["for"])
                if parent in parsed:
                    in_parts[parent] = parsed[parent]
                extra.discard(parent)
        us = re.search(r"\b(?:u\.?s\.?a?\.?|united states)\b", parent_text, re.I)
        if wildcard and not extra and not in_parts and parent_text.strip() and not us:
            return _fail(f"{for_level} does not nest in ({parent_text.strip()})", nested=False)
        in_names = frozenset(in_parts) | extra
        predicate = legal_predicate(
            for_level, in_names, wildcard=wildcard or not in_parts, entries=entries
        )
        list_in = dict(in_parts)
        state_wildcard = legal_predicate(
            for_level, frozenset({"state"}), wildcard=True, entries=entries
        )
        skip_star = for_level in {"state", "zip code tabulation area", "us"}
        if not list_in and not skip_star and state_wildcard:
            list_in = {"state": "*"}
            predicate = predicate or state_wildcard
        if predicate is None:
            detail = f"{for_level} with in={dict(in_parts)} is not a legal combination"
            if not (wildcard or in_parts):
                return _fail(detail, wildcard=wildcard)
            spec = unsupported_wildcard(query, for_level, in_parts, dataset=dataset, year=year)
            unsupported = ResolveGeographyResult(
                specs=[spec], wildcard=wildcard, legal=False, detail=detail
            )
            return detail, unsupported
        # fmt: off
        zcta = for_level == "zip code tabulation area" and not wildcard
        hit = re.search(r"(?i)\b(?:zcta5?s?|zips?|zip codes?)\s+(\d{5})\b", query) if zcta else None
        if hit:
            code = hit.group(1)
            after = query[hit.end():]
            if re.search(r"\b(?:inside|within|in)\s+[A-Za-z]", after, re.I):
                return _fail(f"{for_level} does not nest in ({after.strip()})", nested=False)
            spec = GeoSpec(
                level=for_level, name=f"ZCTA5 {code}",
                for_spec=f"{for_level}:{code}", dataset=dataset, vintage=year)
            return f"1 geography: {spec.for_spec}", ResolveGeographyResult(
                specs=[spec], wildcard=False, legal=True, detail="")
        # fmt: on
        if wildcard:
            parent = " ".join(f"{k}:{v}" for k, v in list_in.items())
            spec = GeoSpec(
                level=for_level,
                name=query.strip(),
                for_spec=f"{for_level}:*",
                in_spec=parent,
                dataset=dataset,
                vintage=year,
            )
            others = [
                GeoSpec(
                    level=row["level"],
                    name=row["name"],
                    for_spec=row["for"],
                    in_spec=row.get("in", ""),
                    geoid=row.get("geoid", ""),
                    dataset=dataset,
                    vintage=year,
                )
                for row in leftover_parents
            ]
            result = ResolveGeographyResult(
                specs=[spec, *others], wildcard=True, legal=True, detail=""
            )
            return f"wildcard {spec.for_spec} {spec.in_spec}".strip(), result

        rows = await asyncio.to_thread(
            self.list_geographies, for_level, list_in, dataset=dataset, vintage=year
        )
        token = place_token(query, state[0] if state else None)
        matched = named_rows(token, rows)
        if not matched and for_level == "place" and not level and detect_level(query) is None:
            matched = named_rows(
                token,
                await asyncio.to_thread(
                    self.list_geographies, "county", list_in, dataset=dataset, vintage=year
                ),
            )
        specs = [
            GeoSpec(
                level=row["level"],
                name=row["name"],
                for_spec=row["for"],
                in_spec=row.get("in", ""),
                geoid=row.get("geoid", ""),
                dataset=dataset,
                vintage=year,
            )
            for row in matched
        ]
        detail = f"no {for_level} matched {query!r}" if not specs else ""
        result = ResolveGeographyResult(specs=specs, wildcard=False, legal=True, detail=detail)
        n = len(specs)
        chosen = specs[0] if specs else None
        one = (
            f"1 geography: {chosen.for_spec} {chosen.in_spec}"
            if chosen
            else f"0 {for_level} candidates"
        )
        many = (
            f"selected {chosen.for_spec} {chosen.in_spec}; {n - 1} alternatives" if chosen else one
        )
        summary = (many if n > 1 else one).strip()
        return (detail or summary), result
