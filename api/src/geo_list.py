"""State FIPS lookup and Census NAME listings for resolve_geography."""

from __future__ import annotations

import re

import httpx

from src.census_url import CENSUS_API, CensusURL

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
# "Washington, DC" must win over the state named Washington.
_DC = re.compile(
    r"district of columbia|\bwashington,\s*d\.?c\.?\b|\bwashington\s+d\.?c\.?\b",
    re.IGNORECASE,
)


def find_state(text: str) -> tuple[str, str] | None:
    if _DC.search(text):
        return "district of columbia", "11"
    for name, usps, fips in STATES:
        if re.search(rf",\s*{usps}\b", text, re.IGNORECASE):
            return name, fips
    folded = text.casefold()
    last: tuple[int, int, str, str] | None = None
    for name, _usps, fips in STATES:
        for match in re.finditer(rf"\b{re.escape(name)}\b", folded):
            candidate = (match.end(), len(name), name, fips)
            if last is None or candidate[:2] > last[:2]:
                last = candidate
    return None if last is None else (last[2], last[3])


def token_is_dc(token: str) -> bool:
    """Washington / DC leftovers after place_token, including D.C. and 'Washington DC'."""
    words = token.replace(".", "").replace(",", " ").split()
    return bool(words) and all(word in {"washington", "dc", "d", "c"} for word in words)


_COUNTY = re.compile(
    r"\b([A-Za-z][A-Za-z.'-]*(?:\s+[A-Za-z][A-Za-z.'-]*)*)\s+count(?:y|ies)\b",
    re.IGNORECASE,
)
_PLACE_SPAN = re.compile(
    r"\b(?i:in|for|of)\s+(?:(?:the|a)\s+)?(?!((?:19|20)\d{2})\b)"
    r"([A-Z][A-Za-z.'-]*(?:\s+(?:(?:of|the|and)\s+)*[A-Z][A-Za-z.'-]*)*)"
)
_TOKEN_NOISE = frozenset(
    {"population", "of", "the", "in", "a", "an", "how", "many", "people", "what", "is", "are"}
)


def place_token(query: str, state_name: str | None) -> str:
    match = _COUNTY.search(query)
    if match:
        words = match.group(1).casefold().split()
        cut = 0
        for i, word in enumerate(words):
            if word in _TOKEN_NOISE | {"for"} and word not in {"of", "the", "and"}:
                cut = i + 1
        words = words[cut:]
        while words and words[0] in _TOKEN_NOISE:
            words.pop(0)
        if words and words[0] not in {"all", "every", "each"}:
            return " ".join(words)
    spans = [hit.group(2).casefold() for hit in _PLACE_SPAN.finditer(query)]
    if state_name:
        kept: list[str] = []
        for span in spans:
            span = re.sub(rf"\b{re.escape(state_name)}\b", " ", span)
            span = re.sub(r"[,\s]+", " ", span).strip()
            if span and span != state_name:
                kept.append(span)
        spans = kept
    if spans:
        return spans[-1]
    text = re.sub(r",\s*[A-Z]{2}\b", " ", query)
    for word in ("county", "counties", "city", "cities", "place", "places", "cdp", "town"):
        text = re.sub(rf"\b{word}\b", " ", text, flags=re.IGNORECASE)
    leftover = re.sub(r"[,\s]+", " ", text).strip().casefold()
    if not state_name:
        return leftover
    without_state = re.sub(rf"\b{re.escape(state_name)}\b", " ", leftover).strip()
    without_state = re.sub(r"[,\s]+", " ", without_state).strip()
    significant = " ".join(word for word in without_state.split() if word not in _TOKEN_NOISE)
    if significant:
        return significant
    return state_name if state_name in leftover else leftover


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
