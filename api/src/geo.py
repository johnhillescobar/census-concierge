"""resolve_geography: the model's structured places to Census `for`/`in` codes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any, Literal

from langchain_core.tools import BaseTool
from pydantic import ConfigDict

from src.compare import unsupported_wildcard
from src.contract import GeoSpec, clause_codes
from src.geo_level import ZCTA, ResolveGeographyResult, declared_levels, level_name
from src.geo_list import (
    MAX_CANDIDATES,
    dominant,
    filter_rows,
    name_token,
    named_rows,
    rank_matches,
    state_of,
)
from src.geo_within import tracts_in_place
from src.retrieval.metadata import GeoLevel
from src.tools import ResolveGeographyInput

ListGeographies = Callable[..., list[dict[str, str]]]
GeoTable = Callable[[str, int], list[GeoLevel]]
LatestVintage = Callable[[str], int]
Reply = tuple[str, ResolveGeographyResult]


def _fail(detail: str, *, wildcard: bool = False, nested: bool = True) -> Reply:
    hit = ResolveGeographyResult(
        specs=[], wildcard=wildcard, legal=False, detail=detail, nested=nested
    )
    return detail, hit


def _compare_result(
    specs: list[GeoSpec], extra: list[GeoSpec], *, legal: bool, inferred: bool, detail: str = ""
) -> ResolveGeographyResult:
    return ResolveGeographyResult(
        specs=specs + extra,
        wildcard=False,
        legal=legal,
        detail=detail,
        compare=True,
        compare_count=len(specs),
        inferred=inferred,
    )


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


def track_geo_query(queries: list[str], query: str) -> list[str]:
    """Append `query` as a new comparison leg, or replace the last entry if
    it only adds a state/qualifier to the SAME name ("Springfield" ->
    "Springfield, Illinois") -- matched by the name before any comma, not a
    bare substring (which would also, wrongly, match "New York" against
    "New York City, NY", a different place)."""
    if queries:
        head = query.split(",", 1)[0].strip().casefold()
        prior_head = queries[-1].split(",", 1)[0].strip().casefold()
        if head == prior_head:
            return [*queries[:-1], query]
    return [*queries, query]


def _stated(level: str | None, entries: list[GeoLevel]) -> tuple[str | None, Reply | None]:
    """The model's level as published for the dataset, or the refusal that sends it back."""
    name = level_name(level)
    if name in {None, "us"} or name in {entry.name for entry in entries}:
        return name, None
    names = ", ".join(dict.fromkeys(entry.name for entry in entries))
    detail, refusal = _fail(f"unknown geography level {level!r}; published here: {names}")
    return None, (detail, refusal.model_copy(update={"refused": True}))


def _only_state(entry: str) -> bool:
    """The entry is the state itself ("New York"), not a place that lies in it ("New York, NY")."""
    return "," not in entry


def _spec(row: dict[str, str], dataset: str, year: int) -> GeoSpec:
    return GeoSpec(
        level=row["level"],
        name=row["name"],
        for_spec=row["for"],
        in_spec=row.get("in", ""),
        geoid=row.get("geoid", ""),
        dataset=dataset,
        vintage=year,
    )


class ResolveGeographyTool(BaseTool):
    name: str = "resolve_geography"
    description: str = (
        "Turn the places a question names, or a listing's parents, into Census codes."
    )
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
        places: list[str] | None = None,
        parents: list[str] | None = None,
        parent_level: str | None = None,
        level: str | None = None,
        levels: list[str | None] | None = None,
        dataset: str = "acs5",
        vintage: int | None = None,
    ) -> Reply:
        year = vintage if vintage is not None else self.latest_vintage(dataset)
        try:
            entries = await asyncio.to_thread(self.geo_table, dataset, year)
        except (OSError, ValueError, TypeError, KeyError):
            return _fail(f"no geography metadata for {dataset} {year}")
        legs = [leg.strip() for leg in places or [] if isinstance(leg, str) and leg.strip()]
        owners = [
            o.strip() if isinstance(o, str) and o.strip() else "(blank)" for o in parents or []
        ]
        if owners or level_name(parent_level) == "us":
            repeats = {leg.casefold() for leg in legs} <= {own.casefold() for own in owners}
            # the same names again are redundant; anything else is a second ask
            if levels or not repeats:
                return _fail(
                    "a listing takes parents; send places in their own call", wildcard=True
                )
            by_name = level_name(parent_level) not in {None, "state", "us"}
            if len(owners) > 1 and by_name and not all(state_of(o) for o in owners):
                # each would search every state: name each parent with its state instead
                return _fail(
                    "name each parent with its state when there are several", wildcard=True
                )
            args = (level, parent_level, dataset, year, entries)
            picks = await asyncio.gather(*(self._list(owner, *args) for owner in owners or [""]))
            if len(owners) < 2:
                return await tracts_in_place(self, owners, level, dataset, year, entries, picks[0])
            pairs = zip(owners, picks, strict=True)
            bad = [owner for owner, (_d, hit) in pairs if not (hit.legal and hit.specs)]
            if bad:
                return _fail(f"unresolved wildcard parent(s): {', '.join(bad)}", wildcard=True)
            specs = [hit.specs[0] for _d, hit in picks]
            extra = [row for _d, hit in picks for row in hit.specs[1:]]
            flag = any(hit.inferred for _d, hit in picks)
            return f"{len(specs)} wildcard geographies", _compare_result(
                specs, extra, legal=True, inferred=flag
            )
        if levels and (len(legs) < 2 or len(levels) != len(legs)):
            return _fail("levels pairs with two or more places, one entry each")
        if len(legs) >= 2:
            stated = declared_levels({"places": legs, "levels": levels, "level": level})
            resolved = await asyncio.gather(
                *(
                    self._place(leg, lv, dataset, year, entries)
                    for leg, lv in zip(legs, stated, strict=True)
                )
            )
            hits = [hit for _detail, hit in resolved]
            if all(hit.legal and hit.specs for hit in hits):
                specs = [hit.specs[0] for hit in hits]
                extra = [row for hit in hits for row in hit.specs[1:]]
                summary = " vs ".join(spec.for_spec for spec in specs)
                inferred = any(h.inferred for h in hits)
                return f"{len(specs)} geographies: {summary}", _compare_result(
                    specs, extra, legal=True, inferred=inferred
                )
            for hit in hits:
                if hit.legal and hit.specs:
                    return f"1 geography: {hit.specs[0].for_spec}", hit
        if len(legs) > 1:
            return resolved[0]  # no leg resolved: the first leg's own answer, not a second lookup
        if not legs and level_name(level) != "us":
            return _fail(
                "name the place in places (parents for a listing); level 'us' is the nation"
            )
        return await self._place(legs[0] if legs else "", level, dataset, year, entries)

    async def _list(
        self,
        owner: str,
        level: str | None,
        parent_level: str | None,
        dataset: str,
        year: int,
        entries: list[GeoLevel],
    ) -> Reply:
        """Every `level` unit inside one parent the model named."""
        for_level, refusal = _stated(level, entries)
        if refusal:
            return refusal
        if for_level in {None, "us"}:
            return _fail("a listing needs level: the kind of unit to list", wildcard=True)
        parent, refusal = _stated(parent_level, entries)
        if refusal:
            return refusal
        parent = parent or "state"
        in_parts: dict[str, str] = {}
        leftover: list[dict[str, str]] = []
        if parent != "us":
            state = state_of(owner) if "," in owner or parent == "state" else None
            if parent == "state" and (state is None or not _only_state(owner)):
                return _fail(
                    f"{owner!r} is not a state; send parent_level for what it is",
                    wildcard=True,
                    nested=False,
                )
            if state is not None:
                in_parts["state"] = state[1]
            if not (nests_in(for_level, "state", entries) and nests_in(for_level, parent, entries)):
                return _fail(
                    f"{for_level} does not nest in {parent} ({owner})", wildcard=True, nested=False
                )
        if parent not in {"us", "state"}:
            # a parent named without its state: every state is searched, the largest match wins
            star = legal_predicate(parent, frozenset({"state"}), wildcard=True, entries=entries)
            where = dict(in_parts) or ({"state": "*"} if star else {})
            if not where:
                return _fail(f"{for_level} nested in unresolved {parent}", wildcard=True)
            rows = await asyncio.to_thread(
                self.list_geographies, parent, where, dataset=dataset, vintage=year
            )
            matched = rank_matches(filter_rows(name_token(owner), rows))
            if not matched:
                return _fail(f"{for_level} nested in unresolved {parent}", wildcard=True)
            if where.get("state") == "*" and not dominant(matched):
                names = "; ".join(row["name"] for row in matched[:MAX_CANDIDATES])
                detail = f"{owner!r} matches {len(matched)} places ({names}); name its state"
                found = [_spec(row, dataset, year) for row in matched[:MAX_CANDIDATES]]
                return detail, ResolveGeographyResult(
                    specs=found, wildcard=False, legal=True, detail=detail, ambiguous=True
                )
            pick, leftover = matched[0], matched[1:]
            in_parts.update(clause_codes(pick.get("in", "")))
            parsed = clause_codes(pick["for"])
            if parent in parsed:
                in_parts[parent] = parsed[parent]
        star = legal_predicate(for_level, frozenset({"state"}), wildcard=True, entries=entries)
        if not in_parts and for_level != ZCTA and star:
            in_parts = {"state": "*"}  # nationwide: the state wildcard the URL writes itself
        label = f"every {for_level} in {owner}" if owner else f"every {for_level}"
        predicate = legal_predicate(for_level, frozenset(in_parts), wildcard=True, entries=entries)
        if predicate is None:
            detail = f"{for_level} with in={in_parts} is not a legal combination"
            spec = unsupported_wildcard(label, for_level, in_parts, dataset=dataset, year=year)
            return detail, ResolveGeographyResult(
                specs=[spec], wildcard=True, legal=False, detail=detail
            )
        spec = GeoSpec(
            level=for_level,
            name=label,
            for_spec=f"{for_level}:*",
            in_spec=" ".join(f"{k}:{v}" for k, v in in_parts.items()),
            dataset=dataset,
            vintage=year,
        )
        others = [_spec(row, dataset, year) for row in leftover]
        result = ResolveGeographyResult(specs=[spec, *others], wildcard=True, legal=True, detail="")
        return f"wildcard {spec.for_spec} {spec.in_spec}".strip(), result

    async def _place(
        self, entry: str, level: str | None, dataset: str, year: int, entries: list[GeoLevel]
    ) -> Reply:
        """The place(s) one entry names, matched by NAME at the level the model stated."""
        for_level, refusal = _stated(level, entries)
        if refusal:
            return refusal
        if for_level == "us":
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
        state = state_of(entry) if "," in entry or for_level in {None, "state"} else None
        if for_level is None:
            for_level = "state" if state and _only_state(entry) else "place"
        in_parts: dict[str, str] = {}
        if for_level != "state" and state is not None:
            if not nests_in(for_level, "state", entries):
                return _fail(f"{for_level} does not nest in state ({entry})", nested=False)
            in_parts["state"] = state[1]
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
        predicate = legal_predicate(
            for_level, frozenset(in_parts), wildcard=not in_parts, entries=entries
        )
        list_in = dict(in_parts)
        state_wildcard = legal_predicate(
            for_level, frozenset({"state"}), wildcard=True, entries=entries
        )
        if not list_in and for_level not in {"state", ZCTA, "us"} and state_wildcard:
            list_in = {"state": "*"}
            predicate = predicate or state_wildcard
        if predicate is None:
            return _fail(f"{for_level} with in={in_parts} is not a legal combination")
        token = name_token(entry)
        token = next((w for w in token.split() if len(w) == 5 and w.isdigit()), token)
        if for_level == ZCTA and len(token) == 5 and token.isdigit():
            spec = GeoSpec(
                level=for_level,
                name=f"ZCTA5 {token}",
                for_spec=f"{for_level}:{token}",
                dataset=dataset,
                vintage=year,
            )
            result = ResolveGeographyResult(specs=[spec], wildcard=False, legal=True, detail="")
            return f"1 geography: {spec.for_spec}", result
        rows = await asyncio.to_thread(
            self.list_geographies, for_level, list_in, dataset=dataset, vintage=year
        )
        matched = named_rows(token, rows)
        inferred = False
        if not matched and for_level == "place" and level_name(level) is None:
            inferred = True  # no place matched; the county listing is a different level
            county = await asyncio.to_thread(
                self.list_geographies, "county", list_in, dataset=dataset, vintage=year
            )
            matched = named_rows(token, county)
        specs = [_spec(row, dataset, year) for row in matched]
        detail = f"no {for_level} matched {entry!r}" if not specs else ""
        result = ResolveGeographyResult(
            specs=specs,
            wildcard=False,
            legal=True,
            detail=detail,
            inferred=inferred,
            dominant=dominant(matched),
        )
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
