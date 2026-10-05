#!/usr/bin/env python3
"""Enforce the invariants that are mechanically checkable.

Companion to `check_budgets.py`. Budgets count things; this checks that specific
mistakes have not been made. Everything here is greppable and unambiguous — the
judgment calls live in the review playbook, not in this file.

    python scripts/check_invariants.py
    python scripts/check_invariants.py --base origin/main   # adds budget-diff, new-regex

Exits non-zero on any violation. Every check is printed by name, pass or fail.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import subprocess
import sys
import tokenize
import tomllib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TypeGuard

import budget_log

ROOT = Path(__file__).resolve().parent.parent
API_SRC = ROOT / "api" / "src"
API_TESTS = ROOT / "api" / "tests"
WEB_SRC = ROOT / "web" / "src"
SCRIPTS = ROOT / "scripts"
EVIDENCE = ROOT / "evidence"

SKIP_DIRS = {"__pycache__", ".venv", "node_modules", ".git", "dist", "build"}

# Budget sections where a LARGER number is weaker, versus where a SMALLER one is.
CEILING_SECTIONS = ("size", "shape", "performance")
FLOOR_SECTIONS = ("quality",)

BANNED_MODULE = re.compile(
    r"_(manager|orchestrator|factory|policy|strategy|service)\.(py|ts|tsx|js|jsx)$"
)
EMPTY_SECRET = re.compile(
    r"""(?:os\.environ\.get|os\.getenv)\(\s*["'](CENSUS_API_KEY|OPENAI_API_KEY|GEMINI_API_KEY)["']\s*,\s*["']{2}\s*\)"""
)
KEY_LEAK = re.compile(r"""(?i)[?&]key=(?!REDACTED(?:["'&\s]|$))[^&\s"']+""")
KEY_IN_URL = re.compile(r"[?&]key=", re.IGNORECASE)


@dataclass(frozen=True)
class Violation:
    where: str
    message: str


def _py_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return [p for p in root.rglob("*.py") if not SKIP_DIRS & set(p.parts)]


def _scan(files: list[Path], pattern: re.Pattern[str], message: str) -> list[Violation]:
    found: list[Violation] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                rel = path.relative_to(ROOT).as_posix()
                found.append(Violation(f"{rel}:{lineno}", message))
    return found


def check_banned_agent_frameworks() -> list[Violation]:
    """The loop is ours. langchain_core.tools is fine; the agent runtime is not."""
    return _scan(
        _py_files(API_SRC),
        re.compile(r"\b(from langchain\.agents|create_agent|AgentExecutor)\b"),
        "the agent loop is hand-rolled: langchain.agents / create_agent / "
        "AgentExecutor are banned (see .cursor/rules/10-api-python.mdc)",
    )


def check_no_sqlite() -> list[Violation]:
    """The predecessor shipped a local checkpoints.db. This app is multi-user."""
    return _scan(
        _py_files(API_SRC),
        re.compile(r"\bimport sqlite3\b|\bsqlite3\.connect\b|sqlite\+|sqlite:///"),
        "SQLite cannot serve a multi-user app - use Postgres",
    )


def check_no_contextvars() -> list[Violation]:
    """The set/reset-token pattern is one refactor from cross-user leakage."""
    return _scan(
        _py_files(API_SRC),
        re.compile(r"\bimport contextvars\b|\bContextVar\b"),
        "pass context as function arguments; contextvars leak across users",
    )


def check_test_naming() -> list[Violation]:
    """A test named after a ticket cannot be interpreted or deleted later."""
    found: list[Violation] = []
    ticket = re.compile(r"test_[a-z]*_?\d{2,}[_.]", re.IGNORECASE)
    for path in _py_files(API_TESTS):
        if ticket.search(path.name):
            found.append(
                Violation(
                    path.relative_to(ROOT).as_posix(),
                    "tests are named for behaviour, not tickets - nobody can "
                    "later interpret or delete test_census_43_*",
                )
            )
    return found


def check_tests_do_not_touch_prompts() -> list[Violation]:
    """Asserting on prompt wording breaks on edits and survives regressions."""
    return _scan(
        _py_files(API_TESTS),
        re.compile(r"\bfrom\s+\S*prompts?\s+import\b|\bimport\s+\S*\.prompts\b"),
        "never assert on prompt wording - test behaviour (question in, table and URL out)",
    )


def check_banned_module_names() -> list[Violation]:
    """Those suffixes hid orchestration the predecessor could not delete."""
    found: list[Violation] = []
    for root in (API_SRC, WEB_SRC):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or SKIP_DIRS & set(path.parts):
                continue
            if BANNED_MODULE.search(path.name):
                rel = path.relative_to(ROOT).as_posix()
                found.append(
                    Violation(
                        rel,
                        "forbidden module suffix: *_manager, *_orchestrator, "
                        "*_factory, *_policy, *_strategy, *_service",
                    )
                )
    return found


def check_no_clarification_layer() -> list[Violation]:
    """A clarification subsystem is a blocking question wearing a directory."""
    found: list[Violation] = []
    for root in (API_SRC, WEB_SRC):
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if SKIP_DIRS & set(path.parts):
                continue
            if "clarif" in path.name.casefold():
                rel = path.relative_to(ROOT).as_posix()
                found.append(
                    Violation(
                        rel,
                        "blocking clarification is forbidden - candidates are results, "
                        "not a question the user cannot answer",
                    )
                )
    return found


def check_census_key_not_in_artifacts() -> list[Violation]:
    """Committed evidence JSON is user-visible. A live Census key must not be in it."""
    if not EVIDENCE.is_dir():
        return []
    found: list[Violation] = []
    for path in EVIDENCE.rglob("*.json"):
        if SKIP_DIRS & set(path.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if KEY_LEAK.search(text):
            rel = path.relative_to(ROOT).as_posix()
            found.append(Violation(rel, "Census API key leaked into evidence JSON; redact &key="))
    return found


def check_no_empty_secret_defaults() -> list[Violation]:
    """`.get("CENSUS_API_KEY", "")` turns a missing key into an unauthenticated call."""
    return _scan(
        [*_py_files(API_SRC), *_py_files(SCRIPTS)],
        EMPTY_SECRET,
        "missing CENSUS_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY must fail closed, "
        "not default to empty",
    )


def check_key_attached_only_in_census_url() -> list[Violation]:
    """`&key=` in api/src belongs on CensusURL, not on a second formatter."""
    files = [path for path in _py_files(API_SRC) if path.name != "census_url.py"]
    return _scan(
        files,
        KEY_IN_URL,
        "&key= is attached only inside census_url.py (CensusURL.with_key / redact_text)",
    )


def _budgets_at(ref: str) -> dict[str, dict[str, float]] | None:
    try:
        blob = subprocess.run(
            ["git", "show", f"{ref}:budgets.toml"],
            cwd=ROOT,
            capture_output=True,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    try:
        return tomllib.loads(blob.decode("utf-8"))
    except (UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None


def check_budgets_not_weakened(base: str) -> list[Violation]:
    """The one check that matters most: nobody may quietly widen a limit.

    Raising a ceiling or lowering a floor is a standalone human commit with a
    reason in the budget log. It is never part of a change that would otherwise
    fail.
    """
    old = _budgets_at(base)
    if old is None:
        return []
    with (ROOT / "budgets.toml").open("rb") as handle:
        new = tomllib.load(handle)

    found: list[Violation] = []
    for section, weakened in (
        *((s, lambda a, b: a > b) for s in CEILING_SECTIONS),
        *((s, lambda a, b: a < b) for s in FLOOR_SECTIONS),
    ):
        for key, new_value in new.get(section, {}).items():
            old_value = old.get(section, {}).get(key)
            if old_value is None or not isinstance(new_value, (int, float)):
                continue
            if weakened(new_value, old_value):
                found.append(
                    Violation(
                        f"budgets.toml [{section}] {key}",
                        f"{old_value:g} -> {new_value:g} weakens the budget. "
                        "This belongs in its own commit, by a human, with a "
                        "reason appended to the change log - never bundled "
                        "with the change it would otherwise block.",
                    )
                )
    return found


REGEX_FUNCS = {
    "compile",
    "search",
    "match",
    "fullmatch",
    "sub",
    "subn",
    "findall",
    "finditer",
    "split",
}


REGEX_MODULES = ("re", "regex")


def _regex_names(nodes: list[ast.AST]) -> set[str]:
    """Names bound to `re`, or to the third-party `regex` module, under any alias."""
    return set(REGEX_MODULES) | {
        a.asname
        for n in nodes
        if isinstance(n, ast.Import)
        for a in n.names
        if a.name in REGEX_MODULES and a.asname
    }


def _is_regex_call(node: ast.AST, names: set[str]) -> TypeGuard[ast.Call]:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in names
        and node.func.attr in REGEX_FUNCS
    )


def _regex_calls(source: str) -> int:
    """Count regex call sites with the AST: `re.<fn>()` (any alias), `from re import <fn>`
    or `*`, and `import regex`, so adopting another engine is ratcheted too."""
    try:
        # A byte-order mark would otherwise be a SyntaxError that counts the file as zero.
        tree = ast.parse(source.lstrip(chr(0xFEFF)))
    except SyntaxError:
        return 0
    nodes = list(ast.walk(tree))
    names = _regex_names(nodes)
    calls = sum(_is_regex_call(n, names) for n in nodes)
    imports = sum(
        a.name in REGEX_FUNCS or a.name == "*"
        for n in nodes
        if isinstance(n, ast.ImportFrom) and n.module in REGEX_MODULES
        for a in n.names
    )
    third_party = sum(
        a.name == "regex" for n in nodes if isinstance(n, ast.Import) for a in n.names
    )
    return calls + imports + third_party


def _regex_counts_now() -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in _py_files(API_SRC):
        count = _regex_calls(path.read_text(encoding="utf-8"))
        if count:
            counts[path.relative_to(ROOT).as_posix()] = count
    return counts


def _regex_counts_at(ref: str) -> dict[str, int] | None:
    try:
        names = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", ref, "--", "api/src"],
            cwd=ROOT,
            capture_output=True,
            check=True,
            text=True,
        ).stdout.split()
        counts: dict[str, int] = {}
        for name in (n for n in names if n.endswith(".py")):
            blob = subprocess.run(
                ["git", "show", f"{ref}:{name}"], cwd=ROOT, capture_output=True, check=True
            ).stdout.decode("utf-8", errors="replace")
            if count := _regex_calls(blob):
                counts[name] = count
        return counts
    except (OSError, subprocess.CalledProcessError):
        return None


def check_no_new_regex(base: str) -> list[Violation]:
    """Regex is a last resort in this agent: the count in api/src may only go down.

    Understanding a question is the model's job; a pattern covers the phrasings its
    author imagined and silently fails the rest. A new regex needs a human commit that
    states why no non-regex code plus the model can do the job.
    """
    old = _regex_counts_at(base)
    if old is None:
        return []
    return [
        Violation(
            where,
            f"{old.get(where, 0)} -> {count} regex call(s). Regex is a last resort: let the "
            "model compose structure and have code validate it (CLAUDE.md, Do not).",
        )
        for where, count in sorted(_regex_counts_now().items())
        if count > old.get(where, 0)
    ]


def _logged_targets(text: str) -> tuple[dict[tuple[str, str], float], list[str]]:
    """The last `[section] field old -> new` value per budget field, and any limit change
    that names an arrow but cannot be read (`4300->4340`, `4340,`), so it cannot hide."""
    last: dict[tuple[str, str], float] = {}
    unreadable: list[str] = []
    for words in budget_log.entries(text):
        is_limit = len(words) > 1 and words[1].startswith("[") and words[1] != "[waiver]"
        if not (is_limit and any("->" in word for word in words)):
            continue
        try:
            arrow = words.index("->")
            field, target = words[2], words[arrow + 1 : arrow + 3]
            try:
                value = float(target[0])
            except ValueError:  # a rename: `old_field 0.95 -> new_field 0.50`
                if not target[0].isidentifier():
                    raise
                field, value = target[0], float(target[1])
        except (ValueError, IndexError):
            unreadable.append(" ".join(words[:7]))
            continue
        last[(words[1].strip("[]"), field)] = value
    return last, unreadable


def check_budget_log_matches_values() -> list[Violation]:
    """A limit and its change log must agree, or a raise can hide in an unexplained gap.

    CC-103 moved api_src_loc 4300 -> 4400 while its log line said 4340. Fields with no
    arrow line in the log are not checked: there is nothing to compare against.
    """
    try:
        text = (ROOT / "budgets.toml").read_text(encoding="utf-8")
        values = tomllib.loads(text)
    except (OSError, tomllib.TOMLDecodeError):
        return []
    if "budget change log" not in text.lower():
        return [
            Violation(
                "budgets.toml",
                "the 'budget change log' header is missing, so no limit change can be read.",
            )
        ]
    targets, unreadable = _logged_targets(text)
    found = [
        Violation(
            f"budgets.toml [{section}] {field}",
            f"the file says {values[section][field]:g} but the last log line says {logged:g}. "
            "A limit changes only in a human commit with a written reason: log the change "
            f"that set {values[section][field]:g}.",
        )
        for (section, field), logged in targets.items()
        if isinstance(values.get(section, {}).get(field), (int, float))
        and values[section][field] != logged
    ]
    found += [
        Violation(
            "budgets.toml change log",
            f"cannot read this limit change: '{entry}'. Write it as '[section] field old -> new'.",
        )
        for entry in unreadable
    ]
    return found


# Eval phrasing in api/src (CC-3 AC8). The visible evals are `evals/*.toml`; the sealed set
# is never read. A known hit lives in the baseline, which may only shrink: a new hit fails,
# and so does a baseline entry whose hit is gone.
LEAK_BASELINE = "evals/leakage_baseline.txt"
LEAK_STOP = frozenset(
    {
        *("a", "an", "and", "are", "as", "at", "be", "by", "do", "does", "for", "from", "has"),
        *("have", "how", "in", "is", "it", "of", "on", "or", "per", "than", "that", "the"),
        *("their", "there", "to", "was", "were", "what", "when", "where", "which", "who"),
        *("with", "without", "within", "across", "each", "every", "all", "not", "no"),
    }
)
LEAK_GENERIC_CAPS = frozenset(
    {"Census", "American", "Community", "Survey", "County", "Counties", "State", "States", "United"}
)
LEAK_PLACE_FILES = ("prompts.py", "tools.py")
# tier, words per phrase, drop stop words. `regex2` is only read inside regex-call arguments:
# a pattern fitted to an eval question is the leak this catches.
LEAK_TIERS = (("gram4", 4, False), ("content3", 3, True), ("regex2", 2, True))


def _leak_words(text: str) -> list[str]:
    """Lowercase alphanumeric words; a regex word boundary (`\\b`) separates words."""
    words: list[str] = []
    current: list[str] = []
    for ch in text.replace("\\b", " ").lower():
        if ch.isalnum():
            current.append(ch)
        elif current:
            words.append("".join(current))
            current = []
    if current:
        words.append("".join(current))
    return words


def _leak_grams(words: list[str], size: int, content: bool) -> set[str]:
    if content:
        words = [w for w in words if w not in LEAK_STOP and len(w) >= 3 and not w.isdigit()]
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def _leak_proper_nouns(text: str, skip_first: bool) -> set[str]:
    tokens = [t.strip("()[]{}.,;:?\"'") for t in text.split()]
    return {
        t.lower()
        for i, t in enumerate(tokens)
        if not (skip_first and i == 0)
        and t.isalpha()
        and len(t) >= 4
        and t[0].isupper()
        and t not in LEAK_GENERIC_CAPS
    }


def _eval_questions() -> list[str]:
    questions: list[str] = []
    for path in sorted((ROOT / "evals").glob("*.toml")):
        try:
            stack = [tomllib.loads(path.read_text(encoding="utf-8"))]
        except (OSError, tomllib.TOMLDecodeError):
            continue
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                for key, value in item.items():
                    if key in ("text", "question") and isinstance(value, str):
                        questions.append(value)
                    else:
                        stack.append(value)
            elif isinstance(item, list):
                stack.extend(item)
    return questions


def _leak_hits() -> dict[tuple[str, str, str], int]:
    """(tier, phrase, file) -> first line, for visible eval phrasing found in api/src."""
    questions = _eval_questions()
    eval_grams = {
        tier: set().union(*(_leak_grams(_leak_words(q), size, content) for q in questions))
        for tier, size, content in LEAK_TIERS
    }
    places = set().union(*(_leak_proper_nouns(q, skip_first=True) for q in questions))
    hits: dict[tuple[str, str, str], set[int]] = {}
    for path in _py_files(API_SRC):
        rel = path.relative_to(ROOT).as_posix()
        source = path.read_text(encoding="utf-8-sig")
        try:
            nodes = list(ast.walk(ast.parse(source)))
        except SyntaxError:
            continue
        names = _regex_names(nodes)
        bare = {
            a.asname or a.name
            for n in nodes
            if isinstance(n, ast.ImportFrom) and n.module in REGEX_MODULES
            for a in n.names
            if a.name in REGEX_FUNCS
        }
        named: dict[str, list[ast.AST]] = {}
        for n in nodes:
            targets = n.targets if isinstance(n, ast.Assign) else [getattr(n, "target", None)]
            value = getattr(n, "value", None)
            if isinstance(n, (ast.Assign, ast.AnnAssign)) and isinstance(value, ast.Constant):
                for target in targets:
                    if isinstance(target, ast.Name):
                        named.setdefault(target.id, []).append(value)
        # The pattern of a regex call: first positional or `pattern=`, with its f-string parts
        # and, when it is a name, the strings assigned to that name. Not the replacement.
        in_regex: set[int] = set()
        for n in nodes:
            is_bare = isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in bare
            if not (is_bare or _is_regex_call(n, names)):
                continue
            for arg in (*n.args[:1], *(k.value for k in n.keywords if k.arg == "pattern")):
                in_regex.update(id(part) for part in ast.walk(arg))
                if isinstance(arg, ast.Name):
                    in_regex.update(id(value) for value in named.get(arg.id, []))
        texts = [
            (n.lineno, n.value, id(n) in in_regex)
            for n in nodes
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        ]
        texts += [
            (tok.start[0], tok.string, False)
            for tok in tokenize.generate_tokens(io.StringIO(source).readline)
            if tok.type == tokenize.COMMENT
        ]
        for line, text, is_regex in texts:
            words = _leak_words(text)
            for tier, size, content in LEAK_TIERS:
                if tier == "regex2" and not is_regex:
                    continue
                for gram in _leak_grams(words, size, content) & eval_grams[tier]:
                    hits.setdefault((tier, gram, rel), set()).add(line)
            if path.name in LEAK_PLACE_FILES:
                for place in _leak_proper_nouns(text, skip_first=False) & places:
                    hits.setdefault(("place", place, rel), set()).add(line)
    return _drop_subsumed(hits)


def _drop_subsumed(
    hits: dict[tuple[str, str, str], set[int]],
) -> dict[tuple[str, str, str], int]:
    """Drop a phrase only on the lines where a longer one already says it: 'median gross rent'
    covers 'gross rent' there, and a new 'gross rent' elsewhere in the file still shows."""
    kept: dict[tuple[str, str, str], int] = {}
    longer: list[tuple[str, str, set[int]]] = []
    for key in sorted(hits, key=lambda k: (-len(k[1].split()), k)):
        _, phrase, rel = key
        covered = {
            line
            for p, r, lines in longer
            if r == rel and p != phrase and f" {phrase} " in f" {p} "
            for line in lines
        }
        if remaining := hits[key] - covered:
            kept[key] = min(remaining)
        longer.append((phrase, rel, hits[key]))
    return kept


def _baseline_entries(text: str) -> set[tuple[str, str, str]]:
    entries = set()
    for raw in text.splitlines():
        parts = [p.strip() for p in raw.split("#", 1)[0].split("|")]
        if len(parts) == 3 and all(parts):
            entries.add((parts[0], parts[1], parts[2]))
    return entries


def _leak_baseline() -> set[tuple[str, str, str]]:
    try:
        return _baseline_entries((ROOT / LEAK_BASELINE).read_text(encoding="utf-8"))
    except OSError:
        return set()


def check_no_eval_phrasing_in_api_src() -> list[Violation]:
    """A prompt, tool description or pattern fitted to an eval question tunes the instrument.

    The model then passes the eval because the eval's own words are in its instructions.
    """
    hits = _leak_hits()
    baseline = _leak_baseline()
    found = [
        Violation(
            f"{rel}:{line}",
            f"eval phrasing in api/src ({tier}: '{phrase}'). Remove it. Plain domain vocabulary "
            f"may be added to {LEAK_BASELINE} as `{tier}|{phrase}|{rel}  # reason`, by a human.",
        )
        for (tier, phrase, rel), line in sorted(hits.items(), key=lambda kv: (kv[0][2], kv[1]))
        if (tier, phrase, rel) not in baseline
    ]
    found += [
        Violation(
            LEAK_BASELINE,
            f"stale entry {tier}|{phrase}|{rel}: the hit is gone. Delete it; the baseline only "
            "shrinks. If the phrase moved (a table, a variable, an f-string) it is still a leak.",
        )
        for tier, phrase, rel in sorted(baseline - set(hits))
    ]
    return found


def _text_at(ref: str, rel: str) -> str | None:
    try:
        blob = subprocess.run(
            ["git", "show", f"{ref}:{rel}"], cwd=ROOT, capture_output=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None
    return blob.decode("utf-8", errors="replace")


def _waivers(text: str) -> set[str]:
    return {" ".join(w) for w in budget_log.entries(text) if len(w) > 1 and w[1] == "[waiver]"}


def _baseline_lines(text: str) -> set[str]:
    return {"|".join(entry) for entry in _baseline_entries(text)}


def check_no_new_exemptions(base: str) -> list[Violation]:
    """A waiver or a leakage-baseline entry is an exemption. It is never added in the same
    change it excuses, or `# [waiver]` and `tier|phrase|file` become the way around both gates.

    A file that does not exist at the base is skipped: its first commit is the owner's review.
    """
    found: list[Violation] = []
    for rel, read in (("budgets.toml", _waivers), (LEAK_BASELINE, _baseline_lines)):
        old = _text_at(base, rel)
        if old is None:
            continue
        try:
            now = (ROOT / rel).read_text(encoding="utf-8")
        except OSError:
            continue
        found += [
            Violation(
                rel,
                f"new exemption '{entry}'. It belongs in its own commit, by a human, with a "
                "reason - never bundled with the change it would otherwise block.",
            )
            for entry in sorted(read(now) - read(old))
        ]
    return found


def check_mandatory_catalogs() -> list[Violation]:
    """Agent catalogs must exist. Does not validate their prose."""
    found: list[Violation] = []
    for rel in (
        "docs/requirements.md",
        "docs/ask-path.md",
        "docs/retrieval.md",
        "docs/slices.md",
    ):
        if not (ROOT / rel).is_file():
            found.append(Violation(rel, "mandatory agent catalog is missing"))
    return found


CHECKS: tuple[tuple[str, Callable[[], list[Violation]]], ...] = (
    ("banned agent frameworks", check_banned_agent_frameworks),
    ("sqlite", check_no_sqlite),
    ("contextvars", check_no_contextvars),
    ("ticket-named tests", check_test_naming),
    ("prompt assertions", check_tests_do_not_touch_prompts),
    ("forbidden module names", check_banned_module_names),
    ("blocking clarification", check_no_clarification_layer),
    ("census key in artifacts", check_census_key_not_in_artifacts),
    ("empty secret defaults", check_no_empty_secret_defaults),
    ("key attached only via CensusURL", check_key_attached_only_in_census_url),
    ("mandatory catalogs", check_mandatory_catalogs),
    ("budget log matches values", check_budget_log_matches_values),
    ("eval phrasing in api/src", check_no_eval_phrasing_in_api_src),
)


def collect(base: str | None) -> list[tuple[str, list[Violation]]]:
    rows = [(name, check()) for name, check in CHECKS]
    if base:
        rows.append(("budget increases", check_budgets_not_weakened(base)))
        rows.append(("new regex", check_no_new_regex(base)))
        rows.append(("new exemptions", check_no_new_exemptions(base)))
    else:
        rows.append(("budget increases", []))
        rows.append(("new regex", []))
        rows.append(("new exemptions", []))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        help="git ref to diff budgets.toml against, e.g. origin/main. "
        "Skipped silently when the ref is unavailable.",
    )
    parser.add_argument(
        "--print-leakage-hits",
        action="store_true",
        help=f"print the current eval-phrasing hits in {LEAK_BASELINE} format and exit",
    )
    args = parser.parse_args()

    if args.print_leakage_hits:
        for tier, phrase, rel in sorted(_leak_hits()):
            print(f"{tier}|{phrase}|{rel}")
        return 0

    rows = collect(args.base)
    width = max(len(name) for name, _ in rows)
    print("\nINVARIANTS\n")
    failed = 0
    for name, violations in rows:
        if name in {"budget increases", "new regex", "new exemptions"} and not args.base:
            print(f"  skip  {name:<{width}}  pass --base to diff against a ref")
            continue
        if not violations:
            print(f"  ok    {name:<{width}}")
            continue
        failed += len(violations)
        print(f"  FAIL  {name:<{width}}")
        for violation in violations:
            print(f"        {violation.where}")
            print(f"        {violation.message}")
    if args.base and (before := _regex_counts_at(args.base)) is not None:
        now, then = sum(_regex_counts_now().values()), sum(before.values())
        print(f"\n  info  api/src regex call sites: {now} (base {then}, delta {now - then:+d})")
    print()
    if not failed:
        print("All invariants held.\n")
        return 0
    print(f"{failed} violation(s).\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
