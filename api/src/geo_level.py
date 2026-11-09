"""The level a question asks for: stated by the model in `resolve_geography` (null = none named),
run exactly by code, and compared with the URLs fetched. A level the model did not state is shown
as unverified, never guessed quietly."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.census_url import CensusURL
from src.contract import AskWarning

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


def note_intent(record: Any, name: str, call: dict[str, Any]) -> None:
    """Keep the level the model stated in its own geography call; a repair call never changes it."""
    args = call.get("args") or {}
    if name != "resolve_geography" or "level" not in args or call.get("origin") == "repair":
        return
    stated, legs = declared_levels(args), len(getattr(record, "geo_queries", None) or [])
    # Single-place calls resolve the legs of a comparison one at a time: keep each leg's own level.
    record.asked_levels = [*record.asked_levels[: legs - 1], *stated] if legs > 1 else stated


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
    }


def geography_level_mismatch(record: Any) -> AskWarning | None:
    """A URL whose `for=` level the model never stated: the substitution this ticket forbids."""
    plan = getattr(getattr(record, "override", None), "geographies", None)  # the user's own plan
    asked = [g.level for g in plan] if plan else list(getattr(record, "asked_levels", None) or [])
    if not asked or getattr(record, "tables_only", False):
        return None
    allowed = {level for level in asked if level}
    if None in asked:  # a leg with no stated level may be answered at the level the lookup chose
        allowed |= {g.level for g in record.geographies}
    urls = list(getattr(getattr(record, "fetch", None), "urls", None) or [])
    urls = urls or ([str(record.url)] if getattr(record, "url", None) else [])
    fetched = {CensusURL(url).for_level() for url in urls} - {""}
    wrong = sorted(fetched - allowed)
    if not wrong:
        return None
    return AskWarning(
        code="geography_level_mismatch",
        detail=(
            f"the question asks for {', '.join(sorted(allowed)) or 'no stated level'}; the URL "
            f"fetches {', '.join(wrong)}. The URL is shown, but its rows answer another geography"
        ),
    )


def geography_level_unverified(record: Any) -> AskWarning | None:
    """A geography was resolved without a level the model stated, or the code had to infer one."""
    if getattr(record, "tables_only", False) or not getattr(record, "geographies", None):
        return None
    if getattr(getattr(record, "override", None), "geographies", None):
        return None  # the user's own plan names the places; no model reading is involved
    status = getattr(record, "geo_status", None) or {}
    stated = bool(getattr(record, "asked_levels", None))
    if stated and not status.get("inferred"):
        return None
    why = (
        "the level was chosen from the place name or its words, not stated by the model"
        if stated
        else "the model never stated which geography level the question asks for"
    )
    return AskWarning(
        code="geography_level_unverified",
        detail=f"{why}; check the level in the URL's for= clause before relying on it",
    )
