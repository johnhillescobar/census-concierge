"""State FIPS lookup and Census NAME listings for resolve_geography."""

from __future__ import annotations

import re

import httpx

from src.census_url import CENSUS_API, CensusURL

# Name, USPS, FIPS.
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


def _bare(text: str) -> str:
    return text.replace(".", "").strip().casefold()


def state_of(entry: str) -> tuple[str, str] | None:
    """(name, FIPS) of the state an entry from the model names: "Name, ST", "Name, State" or a bare
    state. An exact lookup on the part after the last comma (or the whole entry); never a scan."""
    for part in (entry.rsplit(",", 1)[-1], entry):
        key = _bare(part)
        word, _, code = key.partition(" ")  # "state 21", "FIPS 39049": a code with its own label
        code = code if word in {"state", "fips", "geoid"} and code.isdigit() else ""
        for name, usps, fips in STATES:
            coded = code[:2] == fips and (word != "state" or len(code) == 2)
            if key in {name, usps.casefold()} or coded:
                return name, fips
    return None


def name_token(entry: str) -> str:
    """The place name an entry carries: the part before its first comma, folded."""
    return entry.split(",", 1)[0].strip().casefold()


_CLASS = re.compile(
    r"^(?:city|town|village|cdp|borough|county|parish|township|municipality|"
    r"census area|metro township|ut)\b"
)


def _name_hit(token: str, head: str) -> bool:
    if head == token:
        return True
    rest = head[len(token) :].lstrip() if head.startswith(f"{token} ") else ""
    if rest and _CLASS.match(rest):
        return True
    return bool(re.search(rf"\b{re.escape(token)}\b", head) and not head.startswith(token))


def filter_rows(token: str, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Match the NAME head (before the comma), never the state suffix."""
    if not token:
        return []
    hits: list[dict[str, str]] = []
    for row in rows:
        head = row["name"].casefold().split(",", 1)[0].strip()
        if _name_hit(token, head):
            hits.append(row)
    return hits


def named_rows(token: str, rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return rank_matches(filter_rows(token, rows))


def _rank_key(row: dict[str, str]) -> tuple[int, int, float, str]:
    head = row.get("name", "").casefold().split(",", 1)[0]
    if row.get("level") == "place":
        klass = 2 if re.search(r"\bcdp\b", head) else 0 if re.search(r"\bcity\b", head) else 1
    else:
        klass = 0
    try:
        return (klass, 0, -float(row["population"]), row.get("geoid", ""))
    except (KeyError, TypeError, ValueError):
        return (klass, 1, 0.0, row.get("geoid", ""))


def rank_matches(matches: list[dict[str, str]]) -> list[dict[str, str]]:
    """Place class, then population descending, then GEO_ID. Missing pop last."""
    return sorted(matches, key=_rank_key)


def list_census_names(
    for_level: str,
    in_parts: dict[str, str],
    *,
    dataset: str = "acs5",
    vintage: int = 2024,
    key: str = "",
) -> list[dict[str, str]]:
    """NAME listing from the Census API. One request; `in=state:*` is legal."""
    query = f"get=NAME,GEO_ID,B01003_001E&for={for_level}:*"
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
    skip = {"NAME", "GEO_ID", "B01003_001E", for_level}
    rows: list[dict[str, str]] = []
    for raw in body:
        rec = {str(k): str(v) for k, v in zip(header, raw, strict=False)}
        code = rec.get(for_level, "*")
        parents = {name: rec[name] for name in rec if name not in skip}
        rows.append(
            {
                "name": rec.get("NAME", ""),
                "level": for_level,
                "for": f"{for_level}:{code}",
                "in": " ".join(f"{k}:{v}" for k, v in parents.items()),
                "geoid": rec.get("GEO_ID", ""),
                "population": rec.get("B01003_001E", ""),
            }
        )
    return rows
