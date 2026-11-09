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
    stated = args.get("levels")
    if len(places) >= 2 and isinstance(stated, list) and len(stated) == len(places):
        return [level_name(item) for item in stated]
    return [level_name(args.get("level"))] * (len(places) if len(places) >= 2 else 1)


def note_intent(record: Any, name: str, call: dict[str, Any]) -> None:
    """Keep the level the model stated in its own geography call; a repair call never changes it."""
    args = call.get("args") or {}
    if name == "resolve_geography" and "level" in args and call.get("origin") != "repair":
        record.asked_levels = declared_levels(args)


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


def _answer_urls(record: Any) -> list[str]:
    fetch = getattr(record, "fetch", None)
    urls = list(getattr(fetch, "urls", None) or [])
    built = getattr(record, "url", None)
    return urls or ([str(built)] if built else [])


def geography_level_mismatch(record: Any) -> AskWarning | None:
    """A URL whose `for=` level the model never stated: the substitution this ticket forbids."""
    asked = list(getattr(record, "asked_levels", None) or [])
    if not asked or getattr(record, "tables_only", False):
        return None
    allowed = {level for level in asked if level}
    if None in asked:  # a leg with no stated level may be answered at the level the lookup chose
        allowed |= {g.level for g in record.geographies}
    fetched = {CensusURL(url).for_level() for url in _answer_urls(record)} - {""}
    wrong = sorted(fetched - allowed)
    if not wrong:
        return None
    return AskWarning(
        code="geography_level_mismatch",
        detail=(
            f"the question asks for {', '.join(sorted(allowed))}; the URL fetches "
            f"{', '.join(wrong)}. The URL is shown, but its rows answer a different geography"
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
