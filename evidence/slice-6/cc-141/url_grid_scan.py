"""CC-141: do the named cells of the generated URL-breadth grid carry a state? Run once.

The grid is generated from Census NAME strings (which end in the state), and `make demo` does not
run it. A named cell with no state or USPS code anywhere in its question is listed.
"""

import re
import sys
import tomllib

sys.path.insert(0, "api")
from src.geo_list import STATES  # noqa: E402

names = {n for n, _, _ in STATES} | {"puerto rico"}
codes = {c for _, c, _ in STATES} | {"PR"}
cells = tomllib.load(open("evals/url_breadth_grid.toml", "rb"))["cell"]
bare = []
for c in cells:
    q = c["question"]
    named = c["scope"] == "named"
    has = any(re.search(rf"\b{re.escape(n)}\b", q.casefold()) for n in names)
    has = has or any(re.search(rf"\b{k}\b", q) for k in codes)
    if named and not has:
        bare.append((c["id"], c["level"], q[:100]))
total = sum(c["scope"] == "named" for c in cells)
print("named cells:", total, "| no state in the question:", len(bare))
for row in bare:
    print(" ", row)
