"""The level a question asks for: stated by the model in `resolve_geography` (null = none named),
run exactly by code, and compared with the URLs fetched. A level the model did not state is shown
as unverified, never guessed quietly."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.census_url import CensusURL
from src.contract import AskWarning, GeoSpec
from src.tools import ToolResult

ZCTA = "zip code tabulation area"
# Spellings of a level the model may write for a published name. Not a reading of the question.
LEVELS = {
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
    "census tract": "tract",
    "census tracts": "tract",
    "census block group": "block group",
    "census block groups": "block group",
    "zip code": ZCTA,
    "zip codes": ZCTA,
    "zcta5": ZCTA,
    "zcta": ZCTA,
    "zctas": ZCTA,
    "zip": ZCTA,
}


class ResolveGeographyResult(ToolResult):
    specs: list[GeoSpec]
    wildcard: bool
    legal: bool
    detail: str
    nested: bool = True
    compare: bool = False
    # Leading `specs` entries that are genuine one-per-place picks; entries
    # after this count are leftover ambiguous candidates, not places to
    # fetch. Only meaningful when `compare` is True.
    compare_count: int = 0
    # The level came from the place name or the query's words, not from the model's stated level.
    inferred: bool = False
    # The level the model stated is not published for the dataset; the refusal must stand.
    refused: bool = False
    # Executable but wider than asked (the counties a place lies in): warn, still run.
    wider: bool = False
    # The name matched several places, none dominates: the specs are candidates, none is selected.
    ambiguous: bool = False
    # The best NAME match is far larger than the next (or the only one).
    dominant: bool = True


def level_name(token: str | None) -> str | None:
    """The published spelling of a level the model wrote; None when none, or not a string."""
    folded = token.strip().casefold() if isinstance(token, str) else ""
    return LEVELS.get(folded, folded) or None


def declared_levels(args: dict[str, Any]) -> list[str | None]:
    """One level per leg the call resolves: what the model stated, null included."""
    given, raw = args.get("places"), args.get("levels")
    places = (
        [p for p in given if isinstance(p, str) and p.strip()] if isinstance(given, list) else []
    )
    stated = raw if isinstance(raw, list) else []
    legs = max(len(places), len(stated), 1)  # per-leg levels also count the legs they pair with
    if legs >= 2 and len(stated) == legs:
        return [level_name(item) for item in stated]
    return [level_name(args.get("level"))] * legs


@dataclass
class GeoIntent:
    """What the model asked for, in one place, from both of its reports. This is the requested
    side only: what ran is `record.geographies`, what the lookup guessed is
    `geo_status["inferred"]`, and a value code supplies is never written here. The loop's own
    resolve_geography calls fill the first group (a repair call never does); the split call fills
    the second, read once by `adopt`."""

    levels: list[str | None] = field(default_factory=list)  # one per leg the model stated, null too
    legs: list[str] = field(default_factory=list)  # single-place legs resolved so far
    unmet: set[str] = field(default_factory=set)  # stated, and not later served by a legal call
    reported: bool = False
    level: str | None = None
    named: list[Any] = field(default_factory=list)
    numbered: list[Any] = field(default_factory=list)
    given: list[Any] | None = None
    asks_for: str | None = None
    county_named: bool = False
    pointing: bool = False
    places: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)
    unit: str | None = None
    parent_level: str | None = None

    @property
    def tables_only(self) -> bool:
        """The question asks which table holds something: no geography is wanted or flagged."""
        return str(self.asks_for or "").strip().casefold() == "tables"

    def adopt(self, report: GeoIntent | None) -> None:
        """Take the split call's fields, once; the loop's own fields are never touched."""
        if report is None or self.reported:
            return
        for name in ("level", "named", "numbered", "given", "asks_for", "county_named"):
            setattr(self, name, getattr(report, name))
        for name in ("pointing", "places", "parents", "unit", "parent_level"):
            setattr(self, name, getattr(report, name))
        self.reported = True


def intent_of(record: Any) -> GeoIntent:
    """The record's intent; a record that has none states nothing."""
    return getattr(record, "intent", None) or GeoIntent()


def note_intent(record: Any, name: str, call: dict[str, Any], failed: bool = False) -> None:
    """Keep the level the model stated in its own geography call; a repair call never changes it."""
    args = call.get("args") or {}
    if name != "resolve_geography" or "level" not in args or call.get("origin") == "repair":
        return
    stated, status = declared_levels(args), record.geo_status or {}
    shown = max(int(status.get("compare_count") or 0), 1)  # legs the lookup actually resolved
    served = not failed and bool(record.geographies) and status.get("legal") is not False
    served = served and len(stated) <= shown
    intent = record.intent
    for level in filter(None, stated):  # a level asked for and not served must not just vanish
        (intent.unmet.discard if served else intent.unmet.add)(level)
    if not served:  # a failed, refused, empty or partial call keeps the legs it left
        return
    legs = len(intent.legs)
    # Single-place calls resolve the legs of a comparison one at a time: keep each leg's own level.
    intent.levels = [*intent.levels[: legs - 1], *stated] if legs else stated


def geo_status(get: Callable[[str, Any], Any]) -> dict[str, str | bool | int]:
    """The resolve_geography result as the record keeps it."""
    return {
        "legal": bool(get("legal", True)),
        "detail": str(get("detail", "") or ""),
        "nested": get("nested", True) is not False,
        "compare": bool(get("compare", False)),
        "compare_count": int(get("compare_count", 0) or 0),
        "inferred": bool(get("inferred", False)),
        "refused": bool(get("refused", False)),
        "wider": bool(get("wider", False)),
        "ambiguous": bool(get("ambiguous", False)),
    }


def geography_level_mismatch(record: Any) -> AskWarning | None:
    """A URL whose `for=` level the model never stated: the substitution this ticket forbids."""
    plan = getattr(getattr(record, "override", None), "geographies", None)  # the user's own plan
    intent = intent_of(record)
    asked = [g.level for g in plan] if plan else list(intent.levels)
    unmet = set(intent.unmet)
    if not (asked or unmet) or intent.tables_only:
        return None
    allowed = {level for level in asked if level} | unmet  # fetching a stated level is not a swap
    if None in asked:  # a leg with no stated level may be answered at the level the lookup chose
        allowed |= {g.level for g in record.geographies}
    urls = list(getattr(getattr(record, "fetch", None), "urls", None) or [])
    urls = urls or ([str(record.url)] if getattr(record, "url", None) else [])
    fetched = {CensusURL(url).for_level() for url in urls} - {""}
    wrong = sorted(fetched - allowed)
    wanted = {level for level in asked if level} | unmet
    lacking = sorted(wanted - fetched) if fetched else []
    if not wrong and not lacking:
        return None
    return AskWarning(
        code="geography_level_mismatch",
        detail=(
            f"the question asks for {', '.join(sorted(allowed | wanted)) or 'no stated level'}; "
            f"the URL fetches {', '.join(wrong) or 'nothing else'}"
            f"{'; no URL fetches ' + ', '.join(lacking) if lacking else ''}. "
            "The URL is shown, but its rows do not answer the geography asked"
        ),
    )


def geography_level_unverified(record: Any) -> AskWarning | None:
    """A geography was resolved without a level the model stated, or the code had to infer one."""
    intent = intent_of(record)
    if intent.tables_only or not getattr(record, "geographies", None):
        return None
    if getattr(getattr(record, "override", None), "geographies", None):
        return None  # the user's own plan names the places; no model reading is involved
    status = getattr(record, "geo_status", None) or {}
    stated = bool(intent.levels or intent.unmet)
    if stated and not status.get("inferred"):
        return None
    how = "inferred from the place name or its words" if stated else "never stated by the model"
    return AskWarning(
        code="geography_level_unverified",
        detail=f"the level was {how}; check the URL's for= level before relying on it",
    )
