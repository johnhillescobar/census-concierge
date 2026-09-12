"""Census API URLs. Redaction is the type, not a step someone has to remember.

`__str__`, `__repr__` and the value we put on `AskResponse.url` are the form
without `&key=`. The key is reattached only at the httpx call site, via
`with_key`.
"""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

CENSUS_API = "https://api.census.gov/data"


def _strip_key(url: str) -> str:
    parts = urlsplit(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key != "key"
    ]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(kept, safe=":,"), parts.fragment)
    )


class CensusURL:
    """A Census API URL whose default form never carries the key."""

    def __init__(self, url: str) -> None:
        self._redacted = _strip_key(url)

    def __str__(self) -> str:
        return self._redacted

    def __repr__(self) -> str:
        return f"CensusURL({self._redacted!r})"

    def with_key(self, key: str) -> str:
        if not key:
            return self._redacted
        parts = urlsplit(self._redacted)
        query = parse_qsl(parts.query, keep_blank_values=True)
        query = [(name, value) for name, value in query if name != "key"]
        query.append(("key", key))
        return urlunsplit(
            (parts.scheme, parts.netloc, parts.path, urlencode(query, safe=":,"), parts.fragment)
        )
