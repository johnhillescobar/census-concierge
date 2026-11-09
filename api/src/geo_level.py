"""The level a question asks for: stated by the model in `resolve_geography` (null = none named),
run exactly by code, and compared with the URLs fetched. A level the model did not state is shown
as unverified, never guessed quietly."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.census_url import CensusURL
from src.contract import AskWarning, GeoSpec
from src.tools import ToolResult

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
    "zcta": "zip code tabulation area",
    "zctas": "zip code tabulation area",
    "zip": "zip code tabulation area",
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


def level_name(token: str | None) -> str | None:
    """The published spelling of a level the model wrote, or None when it wrote none."""
    folded = (token or "").strip().casefold()
    return LEVELS.get(folded, folded) or None


def declared_levels(args: dict[str, Any]) -> list[str | None]:
    """One level per leg the call resolves: what the model stated, null included."""
    places = [p for p in args.get("places") or [] if isinstance(p, str) and p.strip()]
    raw = args.get("levels")
    stated = raw if isinstance(raw, list) else []
    legs = max(len(places), len(stated), 1)  # per-leg levels also count legs split by "versus"
    if legs >= 2 and len(stated) == legs:
        return [level_name(item) for item in stated]
    return [level_name(args.get("level"))] * legs


def note_intent(record: Any, name: str, call: dict[str, Any], failed: bool = False) -> None:
    """Keep the level the model stated in its own geography call; a repair call never changes it."""
    args = call.get("args") or {}
    if name != "resolve_geography" or "level" not in args or call.get("origin") == "repair":
        return
    stated, status = declared_levels(args), record.geo_status or {}
    unserved = failed or status.get("legal") is False  # a refused level is unserved too
    for level in filter(None, stated):  # a level asked for and not served must not just vanish
        (record.unmet_levels.add if unserved else record.unmet_levels.discard)(level)
    if failed or not record.geographies:  # a failed, refused or empty call keeps the legs it left
        return
    legs = len(getattr(record, "geo_queries", None) or [])
    # Single-place calls resolve the legs of a comparison one at a time: keep each leg's own level.
    record.asked_levels = [*record.asked_levels[: legs - 1], *stated] if legs else stated


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
    }


def geography_level_mismatch(record: Any) -> AskWarning | None:
    """A URL whose `for=` level the model never stated: the substitution this ticket forbids."""
    plan = getattr(getattr(record, "override", None), "geographies", None)  # the user's own plan
    asked = [g.level for g in plan] if plan else list(getattr(record, "asked_levels", None) or [])
    unmet = set(getattr(record, "unmet_levels", ()))
    if not (asked or unmet) or getattr(record, "tables_only", False):
        return None
    allowed = {level for level in asked if level}
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
    if getattr(record, "tables_only", False) or not getattr(record, "geographies", None):
        return None
    if getattr(getattr(record, "override", None), "geographies", None):
        return None  # the user's own plan names the places; no model reading is involved
    status = getattr(record, "geo_status", None) or {}
    stated = bool(getattr(record, "asked_levels", None) or getattr(record, "unmet_levels", None))
    if stated and not status.get("inferred"):
        return None
    how = "inferred from the place name or its words" if stated else "never stated by the model"
    return AskWarning(
        code="geography_level_unverified",
        detail=f"the level was {how}; check the URL's for= level before relying on it",
    )
