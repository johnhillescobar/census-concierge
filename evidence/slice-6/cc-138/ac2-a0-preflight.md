# CC-138 AC2 A0 scorer preflight

The frozen A0 cohort contains 62 questions. Their expected geography levels are 52 strings and 10 nulls. The cohort hashes match the comparison revision for all three tiers. The two scorer hashes differ because `is_answered` delegates geography checking to the added `level_problems` function. The ASTs for `census_urls`, `fetched_level`, `http_ok`, and `_WARNING_WITHOUT_FETCH` match.

| Input | Revision | Scorer hash |
| --- | --- | --- |
| Registered A0 | `4b24f77f647ffa20de3e3c4eeed75ad416affc95` | `78a504c5cbb4b5ff` |
| Comparison | `918ffb98c5de4c417bc211af583e4ad220f90e47` | `6054312479188110` |

For a scalar expected level, the original `any(actual != expected)` and the current nonempty set difference `{actual levels} - {expected}` both reject exactly when any URL has a different level. A null expectation skips the check in both versions. List expectations can require missing legs in the new implementation and are outside this cohort.

The command below executes the pinned graders over **15,872 synthetic response combinations with zero unequal scores**. It varies HTTP status, URLs and levels, table match, row presence, warning presence, and alternatives presence for every frozen A0 expectation. Run from the `cc138-quality-followup` worktree with the repository’s Python 3.12 environment.

```powershell
@'
import ast
from collections import Counter
from itertools import product
import subprocess
from typing import Any
from urllib.parse import parse_qs, urlparse

from scripts import metric_compare as metrics

anchor = "4b24f77f647ffa20de3e3c4eeed75ad416affc95"
comparison = "918ffb98c5de4c417bc211af583e4ad220f90e47"
protocol = metrics.load_protocol(comparison)
symbols = set(protocol["scorer"]["symbols"])
assert metrics.protocol_hash(comparison) == "8239289b06c79e1f"
assert metrics.scorer_hash(protocol, anchor) == "78a504c5cbb4b5ff"
assert metrics.scorer_hash(protocol, comparison) == "6054312479188110"
assert metrics.cohort_hashes(protocol, anchor) == metrics.cohort_hashes(protocol, comparison)

def grader(head):
    source = subprocess.check_output(
        ["git", "show", f"{head}:scripts/run_demo.py"], encoding="utf-8"
    )
    definitions = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.FunctionDef) and node.name in symbols:
            definitions[node.name] = node
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in symbols:
                    definitions[target.id] = node
    scope = {"Any": Any, "parse_qs": parse_qs, "urlparse": urlparse}
    module = ast.Module(body=list(definitions.values()), type_ignores=[])
    exec(compile(module, head, "exec"), scope)
    return scope["is_answered"], {name: ast.dump(node) for name, node in definitions.items()}

old, old_defs = grader(anchor)
new, new_defs = grader(comparison)
changed = sorted(name for name in symbols if old_defs.get(name) != new_defs.get(name))
assert changed == ["is_answered", "level_problems"]
expected_levels = Counter()
checked = unequal = 0
for tier in protocol["cohorts"]:
    for entry in metrics.cohort(protocol, tier, anchor):
        level = entry.get("expect_geo_level")
        assert level is None or isinstance(level, str)
        expected_levels[type(level).__name__] += 1
        matching, other = level or "", "arbitrary"
        for status, levels, table, rows, warning, alternatives in product(
            [199, 200, 299, 300], [[], [matching], [other], [matching, other]],
            [False, True], [False, True], [False, True], [False, True],
        ):
            body = {
                "urls": [f"https://api.census.gov/data/example?for={value}:*" for value in levels],
                "table_id": entry.get("expect_table") if table else None,
                "rows": [{}] if rows else [],
                "warnings": [{"code": entry.get("expect_warning")}] if warning else [],
                "alternatives": [{}] if alternatives else [],
            }
            unequal += old(entry, status_code=status, body=body) != new(
                entry, status_code=status, body=body
            )
            checked += 1
assert expected_levels == {"str": 52, "NoneType": 10}
assert (checked, unequal) == (15872, 0)
print(f"Changed definitions: {changed}")
print(f"A0 geography expectations: {dict(expected_levels)}")
print(f"Synthetic response combinations: {checked}; unequal scores: {unequal}")
'@ | & '../../.venv/Scripts/python.exe' -B -
```

The CC-133 closure record says the archive lacks original response bodies. This proof supports an owner decision about the treatment of A0. A literal re-score of the original responses remains unavailable from that archive. The preflight used visible cohort metadata and synthetic bodies only. Registry edits, bridge approval, and promotions are outside the preflight.
