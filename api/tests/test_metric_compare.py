"""The comparator turns frozen cohorts and run files into a verdict that a better-looking number
cannot buy and that unchanged code does not fail: noisy rates are judged by the tolerances in
[rule], pooled over runs, and a lost trial, a changed scorer, a smaller denominator or a missing
contract field fails whatever the rates did."""

from __future__ import annotations

import copy
import functools
import hashlib
import itertools
import json
import random
import shutil
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_invariants as ci  # noqa: E402
import metric_compare as mc  # noqa: E402

Failing = set[tuple[str, str, int]]  # (tier, family, repeat) trials that were not answered
STAMP = {"head": "f" * 40, "scorer": "s1", "cohorts": {"c": "h"}, "protocol": "p1", "dirty": False}


@pytest.fixture
def protocol() -> dict[str, Any]:
    loaded = mc.load_protocol()
    loaded["sampling"]["resamples"] = 400
    return loaded


def _trials(
    protocol: dict[str, Any],
    failing: Failing,
    rows: Callable[[str, str], int],
    seconds: float,
) -> list[dict[str, Any]]:
    out = []
    for name, spec in protocol["cohorts"].items():
        for entry in mc.cohort(protocol, name):
            for repeat in (1, 2, 3):
                key = (spec["tier"], entry["id"], repeat)
                out.append(
                    {
                        "id": entry["id"],
                        "repeat": repeat,
                        "tier": spec["tier"],
                        "answered": key not in failing,
                        "http_ok": True,
                        "rows": 0 if key in failing else rows(spec["tier"], entry["id"]),
                        "latency_s": seconds,
                    }
                )
    return out


def run(
    protocol: dict[str, Any],
    failing: Failing | None = None,
    *,
    rows: Callable[[str, str], int] = lambda tier, family: 5,
    seconds: float = 10.0,
    scalars: dict[str, float] | None = None,
    trials: list[dict[str, Any]] | None = None,
    stamp: dict[str, Any] | None = None,
) -> mc.Run:
    made = trials if trials is not None else _trials(protocol, failing or set(), rows, seconds)
    tail = [t for t in made if t["tier"] == "long_tail"]
    rate = sum(t["answered"] for t in tail) / len(tail)
    return mc.Run(
        path="synthetic",
        repeat=3,
        index_hash="index",
        p95_reported=mc.percentile([t["latency_s"] for t in made], 95),
        scalars=scalars or {"retrieval_at_10": 0.9, "selector_at_1": 0.8, "answered_rate": rate},
        trials=made,
        hashes=dict(STAMP) if stamp is None else stamp,  # {} is a run that predates provenance
    )


def families_of(protocol: dict[str, Any], tier_name: str, count: int) -> list[str]:
    return [e["id"] for e in mc.cohort(protocol, tier_name)][:count]


def losing(tier: str, ids: list[str]) -> Failing:
    return {(tier, family, repeat) for family in ids for repeat in (1, 2, 3)}


def _long_tail_misses(families: list[str], counts: list[int]) -> Failing:
    return {
        ("long_tail", family, repeat)
        for family, count in zip(families, counts, strict=True)
        for repeat in range(1, count + 1)
    }


def row(checks: list[mc.Check], name: str, ref: str | None = None) -> mc.Check:
    return next(c for c in checks if c.name == name and ref in (None, c.ref))


def status(checks: list[mc.Check], name: str, ref: str | None = None) -> str:
    return row(checks, name, ref).status


def beyond(protocol: dict[str, Any], key: str, questions: int) -> int:
    """The fewest whole questions, of `questions`, whose loss is past the tolerance `key`. One
    fewer is the most that still passes, so a test built on it moves with the ratified number."""
    return int(protocol["rule"][key] * questions + 1e-9) + 1


# --- the rule: a noisy rate fails past its tolerance, never for moving -------------------------


def test_a_run_compared_with_itself_passes(protocol: dict[str, Any]) -> None:
    same = run(protocol, losing("long_tail", families_of(protocol, "long_tail", 10)))
    checks = mc.evaluate(same, same, "B", protocol)
    assert mc.verdict(checks) == "PASS"
    assert status(checks, "long_tail trial rate") == "PASS"


def test_a_fall_inside_the_tolerance_passes_and_one_past_it_fails(protocol: dict[str, Any]) -> None:
    ids = families_of(protocol, "long_tail", 40)
    past = beyond(protocol, "rate_drop_max", len(ids))
    base = run(protocol)
    inside = mc.evaluate(run(protocol, losing("long_tail", ids[: past - 1])), base, "B", protocol)
    outside = mc.evaluate(run(protocol, losing("long_tail", ids[:past])), base, "B", protocol)
    assert status(inside, "long_tail trial rate") == "PASS"
    assert status(outside, "long_tail trial rate") == "FAIL"
    assert mc.verdict(outside) == "FAIL"


def test_a_rate_row_says_how_much_worse_the_candidate_is(protocol: dict[str, Any]) -> None:
    ids = families_of(protocol, "long_tail", 40)
    base, lower = run(protocol), run(protocol, losing("long_tail", ids[:2]))
    assert row(mc.evaluate(lower, base, "B", protocol), "long_tail trial rate").worse == 0.05
    assert row(mc.evaluate(base, lower, "B", protocol), "long_tail trial rate").worse == -0.05
    assert row(mc.evaluate(lower, base, "B", protocol), "long_tail trial rate").kind == "rate"


def test_equal_empty_counts_do_not_fail_coverage(protocol: dict[str, Any]) -> None:
    ids = sorted(families_of(protocol, "long_tail", 40))[:3]
    reference = run(protocol, _long_tail_misses(ids, [2, 2, 3]))
    candidate = run(protocol, _long_tail_misses(ids, [1, 3, 3]))
    checks = mc.evaluate(candidate, reference, "B", protocol)
    assert status(checks, "empty answers (long_tail)") == "PASS"


def test_a_candidate_better_in_one_cohort_and_worse_in_another_is_rejected(
    protocol: dict[str, Any],
) -> None:
    ref = run(protocol, losing("long_tail", families_of(protocol, "long_tail", 8)))
    trap = families_of(protocol, "trap", 18)
    past = beyond(protocol, "small_group_lost_questions", 1)  # trap is a small group
    candidate = run(protocol, losing("trap", trap[:past]))
    checks = mc.evaluate(candidate, ref, "B", protocol)
    assert status(checks, "long_tail trial rate") == "PASS"
    assert status(checks, "trap trial rate") == "FAIL"
    assert mc.verdict(checks) == "FAIL"


def test_a_group_under_the_minimum_gets_a_verdict_from_the_small_group_number(
    protocol: dict[str, Any],
) -> None:
    core = families_of(protocol, "core", 4)
    assert len(core) < protocol["sampling"]["min_families"]
    past = beyond(protocol, "small_group_lost_questions", 1)
    base = run(protocol)
    inside = mc.evaluate(run(protocol, losing("core", core[: past - 1])), base, "B", protocol)
    outside = mc.evaluate(run(protocol, losing("core", core[:past])), base, "B", protocol)
    assert status(inside, "core trial rate") == "PASS"
    assert status(outside, "core trial rate") == "FAIL"
    assert "INCONCLUSIVE" not in {c.status for c in (*inside, *outside)}


def test_a_small_group_is_not_judged_by_the_large_group_tolerance(protocol: dict[str, Any]) -> None:
    # one whole core question is a 25-point fall: far past rate_drop_max, inside the small-group
    # allowance. The two numbers are different rules, and the cohort's size picks between them.
    core = families_of(protocol, "core", 4)
    one = mc.evaluate(run(protocol, losing("core", core[:1])), run(protocol), "B", protocol)
    assert row(one, "core trial rate").worse > protocol["rule"]["rate_drop_max"]
    assert status(one, "core trial rate") == "PASS"
    protocol["sampling"]["min_families"] = 4  # core is no longer small
    one = mc.evaluate(run(protocol, losing("core", core[:1])), run(protocol), "B", protocol)
    assert status(one, "core trial rate") == "FAIL"


def test_a_cohort_with_no_questions_is_unknown_not_a_crash(
    protocol: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    same = run(protocol)
    protocol["cohorts"]["empty"] = {"source": "evals/golden_questions.toml", "tier": "no_such"}
    checks = mc.evaluate(same, same, "B", protocol)
    assert status(checks, "empty trial rate") == "UNKNOWN"
    assert mc.verdict(checks) == "UNKNOWN"


def test_extra_repeats_of_one_family_are_not_extra_observations(protocol: dict[str, Any]) -> None:
    base = run(protocol)
    padded = [*base.trials, {**base.trials[0], "repeat": 4}, {**base.trials[0], "repeat": 5}]
    checks = mc.evaluate(run(protocol, trials=padded), base, "B", protocol)
    assert status(checks, "planned trials") == "FAIL"


def test_a_dropped_trial_fails_instead_of_scoring_the_rest(protocol: dict[str, Any]) -> None:
    base = run(protocol)
    candidate = run(protocol, trials=base.trials[1:])
    assert status(mc.evaluate(candidate, base, "B", protocol), "planned trials") == "FAIL"


def test_dropping_the_failed_questions_cannot_lift_the_rate(protocol: dict[str, Any]) -> None:
    ids = families_of(protocol, "long_tail", 6)
    ref = run(protocol, losing("long_tail", ids))
    kept = [t for t in ref.trials if not (t["tier"] == "long_tail" and t["id"] in ids)]
    checks = mc.evaluate(run(protocol, trials=kept), ref, "B", protocol)
    assert mc.verdict(checks) == "FAIL"


def test_faster_failures_are_not_a_speed_gain(protocol: dict[str, Any]) -> None:
    ref = run(protocol, seconds=20.0)
    lost = families_of(protocol, "long_tail", beyond(protocol, "rate_drop_max", 40))
    candidate = run(protocol, losing("long_tail", lost), seconds=2.0)
    checks = mc.evaluate(candidate, ref, "B", protocol)
    assert status(checks, "long_tail trial rate") == "FAIL"
    assert "not credited" in row(checks, "p95 vs reference").detail
    assert mc.verdict(checks) == "FAIL"


def test_a_p95_rise_past_its_tolerance_fails_and_one_inside_it_passes(
    protocol: dict[str, Any],
) -> None:
    limit = protocol["rule"]["p95_rise_max_seconds"]
    ref = run(protocol, seconds=20.0)
    inside = mc.evaluate(run(protocol, seconds=20.0 + limit), ref, "B", protocol)
    outside = mc.evaluate(run(protocol, seconds=20.0 + limit + 0.01), ref, "B", protocol)
    assert status(inside, "p95 vs reference") == "PASS"
    assert status(outside, "p95 vs reference") == "FAIL"


def test_questions_returning_fewer_rows_when_answered_fail_past_their_limit(
    protocol: dict[str, Any],
) -> None:
    ids = families_of(protocol, "long_tail", 40)
    past = beyond(protocol, "rows_lost_questions_max", 1)
    ref = run(protocol, rows=lambda tier, family: 5)

    def thinner(count: int) -> mc.Run:
        return run(protocol, rows=lambda tier, family: 1 if family in ids[:count] else 5)

    assert status(mc.evaluate(thinner(past - 1), ref, "B", protocol), "rows per question") == "PASS"
    assert status(mc.evaluate(thinner(past), ref, "B", protocol), "rows per question") == "FAIL"


def test_an_unanswered_trial_is_not_a_question_returning_fewer_rows(
    protocol: dict[str, Any],
) -> None:
    # a miss returns no rows; counting it here would fail this row for what the rate row measures
    ids = families_of(protocol, "long_tail", 40)
    misses = {("long_tail", family, 1) for family in ids[:10]}  # one repeat of ten questions
    checks = mc.evaluate(run(protocol, misses), run(protocol), "B", protocol)
    assert row(checks, "rows per question").worse == 0


def test_more_empty_answers_than_the_tolerance_fail(protocol: dict[str, Any]) -> None:
    ids = families_of(protocol, "long_tail", 40)
    past = beyond(protocol, "empty_rise_max", len(ids))
    ref = run(protocol)

    def refusing(count: int) -> mc.Run:
        trials = [dict(t) for t in ref.trials]
        for trial in trials:
            if trial["tier"] == "long_tail" and trial["id"] in ids[:count]:
                trial["rows"] = 0  # still marked answered: a refusal that the scorer let through
        return run(protocol, trials=trials)

    inside = mc.evaluate(refusing(past - 1), ref, "B", protocol)
    outside = mc.evaluate(refusing(past), ref, "B", protocol)
    assert status(inside, "empty answers (long_tail)") == "PASS"
    assert status(outside, "empty answers (long_tail)") == "FAIL"


@pytest.mark.parametrize(
    ("key", "tolerance"),
    [("retrieval_at_10", "retrieval_drop_max"), ("selector_at_1", "selector_drop_max")],
)
def test_a_retrieval_or_selector_drop_fails_past_its_tolerance(
    protocol: dict[str, Any], key: str, tolerance: str
) -> None:
    limit = protocol["rule"][tolerance]

    def scored(value: float) -> mc.Run:
        scalars = {"retrieval_at_10": 0.9, "selector_at_1": 0.8, "answered_rate": 1.0}
        return run(protocol, scalars={**scalars, key: value})

    ref = scored(0.9)
    assert status(mc.evaluate(scored(0.9 - limit), ref, "B", protocol), key) == "PASS"
    assert status(mc.evaluate(scored(0.9 - limit - 0.01), ref, "B", protocol), key) == "FAIL"


def test_a_different_index_is_not_comparable(protocol: dict[str, Any]) -> None:
    base = run(protocol)
    other = run(protocol)
    other.index_hash = "another"
    assert status(mc.evaluate(other, base, "B", protocol), "index") == "FAIL"


def test_the_scorer_hash_ignores_formatting_and_moves_with_logic(
    protocol: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def hashed(source: str) -> str:
        monkeypatch.setattr(mc, "_source", lambda rel, head: source)
        return mc.scorer_hash(protocol)

    plain = "def is_answered(entry):\n    return entry['x'] > 1\n"
    spaced = "# a comment\ndef is_answered(entry):\n    return  entry['x']  >  1  # same\n"
    looser = "def is_answered(entry):\n    return entry['x'] > 0\n"
    assert hashed(plain) == hashed(spaced)
    assert hashed(plain) != hashed(looser)


# --- pooled runs ----------------------------------------------------------------------------------


def test_pooled_runs_are_judged_as_one_sample(protocol: dict[str, Any]) -> None:
    ids = families_of(protocol, "long_tail", 40)
    past = beyond(protocol, "rate_drop_max", len(ids))
    base, good = run(protocol), run(protocol)
    bad = run(protocol, losing("long_tail", ids[:past]))
    assert status(mc.evaluate(bad, base, "B", protocol), "long_tail trial rate") == "FAIL"
    mixed = mc.evaluate([bad, good], [base, base], "B", protocol)
    assert status(mixed, "long_tail trial rate") == "PASS"  # half the trials, half the fall
    assert row(mixed, "long_tail trial rate").worse == past / len(ids) / 2
    both = mc.evaluate([bad, bad], [base, base], "B", protocol)
    assert status(both, "long_tail trial rate") == "FAIL"


def test_a_pool_keeps_every_trial_and_averages_what_each_run_reports(
    protocol: dict[str, Any],
) -> None:
    scalars = {"retrieval_at_10": 0.9, "answered_rate": 1.0}
    high = run(protocol, scalars={**scalars, "selector_at_1": 0.8}, seconds=10.0)
    low = run(protocol, scalars={**scalars, "selector_at_1": 0.4}, seconds=30.0)
    pooled = mc.sample([high, low], protocol)
    assert pooled.scalars["selector_at_1"] == pytest.approx(0.6)
    assert len(pooled.seconds) == len(high.trials) + len(low.trials)
    assert {len(trials) for group in pooled.trials.values() for trials in group.values()} == {6}
    assert mc.percentile(pooled.seconds, 95) == 30.0  # the p95 of all the trials, not a mean of two


def test_pools_of_different_sizes_compare_rates_not_counts(protocol: dict[str, Any]) -> None:
    same = run(protocol, losing("long_tail", families_of(protocol, "long_tail", 6)))
    checks = mc.evaluate(same, [same, same], "L", protocol)  # one post-merge run against two in L
    assert row(checks, "long_tail trial rate").worse == 0
    assert mc.verdict(checks) == "PASS"


def test_a_pool_whose_runs_have_different_indexes_is_not_comparable(
    protocol: dict[str, Any],
) -> None:
    other = run(protocol)
    other.index_hash = "another"
    checks = mc.evaluate([run(protocol), other], [run(protocol), run(protocol)], "B", protocol)
    assert status(checks, "index") == "FAIL"


# --- references: L is the anchor, A and A0 are reported, a changed scorer needs a bridge ---------


WRITTEN = itertools.count()
MIDNIGHT = datetime(2026, 11, 24, tzinfo=UTC)


def write_run(path: Path, made: mc.Run, hours: float | None = None) -> str:
    """A run file. Each is its own run, collected a second after the one written before it, or
    `hours` after midnight when a test is about the window."""
    after = timedelta(seconds=next(WRITTEN)) if hours is None else timedelta(hours=hours)
    demo = {
        "generated_at": (MIDNIGHT + after).isoformat(),
        "repeat": 3,
        "index_hash": made.index_hash,
        "p95_latency_seconds": made.p95_reported,
        "answered_rate": made.scalars["answered_rate"],
        "trials": made.trials,
        **({"provenance": made.hashes} if made.hashes else {}),
    }
    body = {"retrieval_at_10": 0.9, "selector_at_1": 0.8, "demo": demo}
    path.write_text(json.dumps(body))
    return str(path)


@pytest.fixture
def lab(
    protocol: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    monkeypatch.setattr(mc, "METRICS", tmp_path)
    monkeypatch.setattr(mc, "load_protocol", lambda head=None: protocol)
    now = {"scorer": "s1", "cohorts": {"c": "h"}, "protocol": "p1"}
    kept = {"collection": "k1"}  # the collection settings in force, at any head
    monkeypatch.setattr(mc, "hashes", lambda head=None: dict(now))
    monkeypatch.setattr(mc, "collection_at", lambda head=None: kept["collection"])
    monkeypatch.setattr(mc, "protocol_hash", lambda head=None: "p1")
    monkeypatch.setattr(mc, "_head", lambda: "f" * 40)
    monkeypatch.setattr(mc, "_same_code", lambda head: True)  # a real git diff is tested apart
    monkeypatch.setattr(mc, "_reachable", lambda commit, tip: True)
    monkeypatch.setattr(mc, "_built_on", lambda base, cand: True)
    return {"dir": tmp_path, "now": now, "kept": kept}


def register(lab: dict[str, Any], name: str, made: mc.Run, scorer: str = "s1") -> None:
    """A reference in the one-file shape the committed anchors A and A0 have."""
    path = write_run(lab["dir"] / f"{name}.json", made)
    refs = mc.load_refs()
    refs[name] = {
        "label": "test",
        "head": "a" * 40,
        "run": path,
        "run_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "hashes": {"scorer": scorer, "cohorts": {"c": "h"}, "protocol": "p1", "collection": "k1"},
    }
    (lab["dir"] / "references.json").write_text(json.dumps(refs))


def with_contract(made: mc.Run) -> mc.Run:
    for trial in made.trials:
        trial.update(dict.fromkeys(mc.CONTRACT_KEYS, True))
    return made


def contract_run(protocol: dict[str, Any], lost: list[str]) -> mc.Run:
    return with_contract(run(protocol, losing("long_tail", lost)))


def wrong_table_run(protocol: dict[str, Any], missed: list[str]) -> mc.Run:
    """A complete run whose `missed` long_tail questions return rows that do not answer them: the
    usual miss, which moves the answered rate and leaves the empty-answer rate alone."""
    made = contract_run(protocol, [])
    for trial in made.trials:
        if trial["tier"] == "long_tail" and trial["id"] in missed:
            trial["answered"] = False
    tail = [t for t in made.trials if t["tier"] == "long_tail"]
    made.scalars["answered_rate"] = sum(t["answered"] for t in tail) / len(tail)
    return made


def bridge_to(rescored: str, to_scorer: str = "s1", **changed: Any) -> dict[str, Any]:
    made = {
        "ref": "L",
        "from_scorer": "s0",
        "to_scorer": to_scorer,
        "from_cohorts": {"c": "h"},
        "to_cohorts": {"c": "h"},
        "rescored_run": rescored,
        "rescored_sha256": hashlib.sha256(Path(rescored).read_bytes()).hexdigest(),
        "note": "same trials, new scorer",
    }
    return {**made, **changed}


def test_a_scorer_change_is_not_a_code_gain_without_a_bridge(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    old = run(protocol, losing("long_tail", families_of(protocol, "long_tail", 12)))
    register(lab, "L", old, scorer="s0")  # scored by an older scorer
    better = write_run(lab["dir"] / "cand.json", run(protocol))
    checks = mc.compare(better, ["L"], {})
    assert status(checks, "scorer / cohort hashes") == "FAIL"


def test_a_bridge_compares_against_the_reference_rescored_by_the_new_scorer(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    ids = families_of(protocol, "long_tail", 12)
    register(lab, "L", run(protocol, losing("long_tail", ids)), scorer="s0")
    rescored = write_run(lab["dir"] / "rescored.json", run(protocol, losing("long_tail", ids[:6])))
    (lab["dir"] / "bridges.json").write_text(json.dumps([bridge_to(rescored)]))
    same_as_rescored = write_run(
        lab["dir"] / "cand.json", run(protocol, losing("long_tail", ids[:6]))
    )
    checks = mc.compare(same_as_rescored, ["L"], {})
    assert row(checks, "long_tail trial rate").worse == 0  # no credit for the 6 the scorer freed
    assert "bridged" in row(checks, "reference label").detail


def test_a_bridge_judges_against_the_rescored_run_not_the_original(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    ids = families_of(protocol, "long_tail", 12)
    register(lab, "L", run(protocol, losing("long_tail", ids)), scorer="s0")  # 12 failing
    rescored = write_run(lab["dir"] / "rescored.json", run(protocol, losing("long_tail", ids[:6])))
    (lab["dir"] / "bridges.json").write_text(json.dumps([bridge_to(rescored)]))
    # better than the original (9 failing against 12) but worse than the rescored run (6)
    cand = write_run(lab["dir"] / "cand.json", run(protocol, losing("long_tail", ids[:9])))
    assert status(mc.compare(cand, ["L"], {}), "long_tail trial rate") == "FAIL"


def test_a_bridge_whose_rescored_run_is_not_pinned_is_refused(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    ids = families_of(protocol, "long_tail", 12)
    register(lab, "L", run(protocol, losing("long_tail", ids)), scorer="s0")
    rescored = write_run(lab["dir"] / "rescored.json", run(protocol))
    tampered = bridge_to(rescored, rescored_sha256="0" * 64)
    (lab["dir"] / "bridges.json").write_text(json.dumps([tampered]))
    cand = write_run(lab["dir"] / "cand.json", run(protocol))
    assert status(mc.compare(cand, ["L"], {}), "bridge") == "FAIL"


def test_a_registered_reference_cannot_be_replaced(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "L", run(protocol))
    path = write_run(lab["dir"] / "other.json", run(protocol))
    assert mc.cmd_register("L", path, "b" * 40, "again") == 1


def test_a_reference_file_edited_after_registration_fails(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "L", run(protocol))
    Path(mc.load_refs()["L"]["run"]).write_text("{}")
    cand = write_run(lab["dir"] / "cand.json", run(protocol))
    assert status(mc.compare(cand, ["L"], {}), "reference file") == "FAIL"


def test_a_reference_registered_from_two_runs_is_judged_as_their_pool(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    ids = families_of(protocol, "long_tail", 40)
    past = beyond(protocol, "rate_drop_max", len(ids))
    whole = write_run(lab["dir"] / "m1.json", contract_run(protocol, []))
    lower = write_run(lab["dir"] / "m2.json", contract_run(protocol, ids[: 2 * past]))
    assert mc.cmd_register("L", [whole, lower], "f" * 40, "two runs of main") == 0
    entry = mc.load_refs()["L"]
    assert [item["run"] for item in entry["runs"]] == [whole, lower]
    assert entry["metrics"]["long_tail_trial_rate"] == round(1 - past / len(ids), 3)
    # as good as the pool's mean passes; as good as its worse run alone is past the tolerance
    mean = write_run(lab["dir"] / "c1.json", contract_run(protocol, ids[:past]))
    assert row(mc.compare(mean, ["L"], {}), "long_tail trial rate").worse == 0
    Path(lower).write_text("{}")  # either file changing unpins the reference
    assert status(mc.compare(mean, ["L"], {}), "reference file") == "FAIL"


def test_candidate_files_are_pooled_against_same_window_main_files(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    ids = families_of(protocol, "long_tail", 40)
    past = beyond(protocol, "rate_drop_max", len(ids))
    bad = write_run(lab["dir"] / "p1.json", wrong_table_run(protocol, ids[:past]))
    again = write_run(lab["dir"] / "p3.json", wrong_table_run(protocol, ids[:past]))
    good = write_run(lab["dir"] / "p2.json", contract_run(protocol, []))
    main = [write_run(lab["dir"] / f"b{n}.json", contract_run(protocol, [])) for n in (1, 2)]
    register(lab, "L", contract_run(protocol, []))
    assert status(mc.compare([bad, again], [], {}, main), "long_tail trial rate", "B") == "FAIL"
    pooled = mc.compare([bad, good], [], {}, main)
    assert status(pooled, "long_tail trial rate", "B") == "PASS"
    assert mc.verdict(pooled) == "PASS"
    assert "2 pooled same-window runs of main" in row(pooled, "reference label", "B").detail
    assert mc.verdict(mc.compare([bad, again], [], {}, main)) == "FAIL"


def test_the_planned_number_of_runs_per_side_is_required(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    files = [write_run(lab["dir"] / f"r{n}.json", contract_run(protocol, [])) for n in range(3)]
    assert mc.blocks(protocol) == (2, 2)
    for cands, main in ((files[:1], files[1:]), (files[:2], files[2:]), (files, files[:2])):
        checks = mc.compare(cands, [], {}, main)
        assert status(checks, "run count", "B") == "FAIL"  # none dropped, none added
        assert mc.verdict(checks) == "FAIL"


def test_base_runs_must_be_clean_runs_of_one_head_on_main(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    cands = [write_run(lab["dir"] / f"p{n}.json", contract_run(protocol, [])) for n in (1, 2)]

    def main_runs(*stamps: dict[str, Any]) -> list[str]:
        made = [with_contract(run(protocol, stamp=stamp)) for stamp in stamps]
        return [write_run(lab["dir"] / f"b{n}.json", item) for n, item in enumerate(made)]

    two_heads = main_runs(STAMP, {**STAMP, "head": "e" * 40})
    assert status(mc.compare(cands, [], {}, two_heads), "same-window main") == "FAIL"
    dirty = main_runs(STAMP, {**STAMP, "dirty": True})
    assert status(mc.compare(cands, [], {}, dirty), "same-window main") == "FAIL"
    unstamped = main_runs({}, {})
    assert status(mc.compare(cands, [], {}, unstamped), "same-window main") == "FAIL"
    asked: list[tuple[str, str]] = []
    monkeypatch.setattr(mc, "_reachable", lambda c, t: asked.append((c, t)) or False)
    off_main = main_runs(STAMP, STAMP)
    assert status(mc.compare(cands, [], {}, off_main), "same-window main") == "FAIL"
    assert asked == [("f" * 40, mc.MAIN)]


def test_base_runs_scored_by_another_scorer_are_not_a_baseline(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    older = "e" * 40
    heads = {older: {"scorer": "s0", "cohorts": {"c": "h"}, "protocol": "p1"}}
    monkeypatch.setattr(mc, "hashes", lambda head=None: dict(heads.get(head, lab["now"])))
    cands = [write_run(lab["dir"] / f"p{n}.json", contract_run(protocol, [])) for n in (1, 2)]
    stamp = {**STAMP, "head": older, "scorer": "s0"}
    main = [
        write_run(lab["dir"] / f"b{n}.json", with_contract(run(protocol, stamp=stamp)))
        for n in (1, 2)
    ]
    checks = mc.compare(cands, [], {}, main)
    assert status(checks, "scorer / cohort hashes", "B") == "FAIL"
    assert not any(c.name == "long_tail trial rate" for c in checks)


def test_the_compare_command_takes_pooled_files_and_judges_against_l_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[tuple[Any, ...]] = []
    monkeypatch.setattr(mc, "cmd_compare", lambda *args: seen.append(args) or 0)
    argv = ["metric_compare.py", "compare", "p1.json", "p2.json", "--base", "b1.json", "b2.json"]
    monkeypatch.setattr(sys, "argv", argv)
    assert mc.main() == 0
    monkeypatch.setattr(sys, "argv", [*argv[:3], "--refs", "A,A0,L", "--record"])
    assert mc.main() == 0
    assert seen == [
        (["p1.json", "p2.json"], ["L"], {}, False, ["b1.json", "b2.json"]),
        (["p1.json"], ["A", "A0", "L"], {}, True, []),
    ]


# --- A and A0 are reported and never block --------------------------------------------------


def test_a_missing_or_failing_a_or_a0_does_not_change_the_verdict(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    assert protocol["rule"]["report_only"] == ["A", "A0"]
    register(lab, "L", contract_run(protocol, []))
    cand = write_run(lab["dir"] / "cand.json", contract_run(protocol, []))
    alone = mc.compare(cand, ["L"], {})
    assert mc.verdict(alone) == "PASS"
    missing = mc.compare(cand, ["A", "A0", "L"], {})  # neither anchor is registered
    assert status(missing, "reference", "A") == "UNKNOWN" and mc.verdict(missing) == "PASS"
    register(lab, "A", contract_run(protocol, []), scorer="s0")  # unbridged: a FAIL row
    lost = families_of(protocol, "long_tail", 8)  # 80%: over the floor, far under the anchor
    cand = write_run(lab["dir"] / "cand.json", contract_run(protocol, lost))
    register(lab, "A0", contract_run(protocol, []))  # the candidate is far below it
    lab["dir"].joinpath("L.json").unlink()
    register(lab, "L", contract_run(protocol, lost))
    failing = mc.compare(cand, ["A", "A0", "L"], {})
    assert status(failing, "scorer / cohort hashes", "A") == "FAIL"
    assert status(failing, "long_tail trial rate", "A0") == "FAIL"
    assert not any(c.blocking for c in failing if c.ref in ("A", "A0"))
    assert all(c.blocking for c in failing if c.ref == "L" and c.name != "lost questions")
    assert mc.verdict(failing) == "PASS"


def test_a_failing_blocking_reference_still_fails_beside_a_passing_anchor(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    lost = families_of(protocol, "long_tail", 8)
    register(lab, "A", contract_run(protocol, lost))  # the candidate matches the old anchor
    register(lab, "L", contract_run(protocol, []))
    cand = write_run(lab["dir"] / "cand.json", contract_run(protocol, lost))
    checks = mc.compare(cand, ["A", "L"], {})
    assert status(checks, "long_tail trial rate", "A") == "PASS"
    assert status(checks, "long_tail trial rate", "L") == "FAIL"
    assert {c.ref for c in checks if c.blocking and c.status == "FAIL"} == {"L"}
    assert mc.verdict(checks) == "FAIL"


def test_l_is_judged_whatever_references_are_named(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "A", contract_run(protocol, []))
    cands = [write_run(lab["dir"] / f"p{n}.json", contract_run(protocol, [])) for n in (1, 2)]
    main = [write_run(lab["dir"] / f"b{n}.json", contract_run(protocol, [])) for n in (1, 2)]
    for names in ([], ["A"], ["A", "A0"]):  # L is not seeded: nothing may read as a pass
        checks = mc.compare(cands, names, {}, main)
        assert status(checks, "reference", "L") == "UNKNOWN" and mc.verdict(checks) == "UNKNOWN"
        assert mc.cmd_compare(cands, names, {}, True, main) == 1
    lines = (lab["dir"] / "ledger.jsonl").read_text().splitlines()
    assert [json.loads(line)["refs"][0] for line in lines] == ["L", "L", "L"]
    assert {json.loads(line)["verdict"] for line in lines} == {"UNKNOWN"}
    # seeded, and the candidate is as good as same-window main but far below the anchor
    lost = families_of(protocol, "long_tail", 8)
    lower = [write_run(lab["dir"] / f"q{n}.json", contract_run(protocol, lost)) for n in (1, 2)]
    low_main = [write_run(lab["dir"] / f"c{n}.json", contract_run(protocol, lost)) for n in (1, 2)]
    register(lab, "L", contract_run(protocol, []))
    checks = mc.compare(lower, ["A"], {}, low_main)  # naming A does not take L out
    assert status(checks, "long_tail trial rate", "B") == "PASS"
    assert status(checks, "long_tail trial rate", "L") == "FAIL"
    assert mc.verdict(checks) == "FAIL"


def test_report_only_rows_are_printed_in_parentheses(
    protocol: dict[str, Any], lab: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    register(lab, "L", contract_run(protocol, []))
    path = write_run(lab["dir"] / "cand.json", contract_run(protocol, []))
    assert mc.cmd_compare(path, ["A0", "L"], {}, record=False) == 0
    lines = capsys.readouterr().out.splitlines()
    anchor = next(line for line in lines if " A0 " in line)
    assert anchor.split()[0] == "(UNKNOWN)"
    assert next(line for line in lines if "long_tail trial rate" in line).split()[:2] == [
        "PASS",
        "rate",
    ]


# --- L: seeded once, moved only upward, and only the owner commits it ----------------------------


def test_promotion_needs_no_pass_against_a(protocol: dict[str, Any], lab: dict[str, Any]) -> None:
    register(lab, "L", contract_run(protocol, []))
    path = write_run(lab["dir"] / "next.json", contract_run(protocol, []))
    assert mc.cmd_promote(path) == 0  # A is not registered at all
    lab["dir"].joinpath("references.json").unlink()
    register(lab, "L", contract_run(protocol, []))
    register(lab, "A", contract_run(protocol, []), scorer="s0")  # and one it cannot be judged by
    assert mc.cmd_promote(path) == 0
    assert mc.load_refs()["L"]["head"] == "f" * 40
    assert mc.load_refs()["A"]["head"] == "a" * 40


def test_promotion_is_refused_until_l_is_seeded(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "A", contract_run(protocol, []))
    before = (lab["dir"] / "references.json").read_bytes()
    assert mc.cmd_promote(write_run(lab["dir"] / "next.json", contract_run(protocol, []))) == 1
    assert (lab["dir"] / "references.json").read_bytes() == before
    assert not (lab["dir"] / "ledger.jsonl").exists()


def test_a_run_of_small_losses_never_moves_l(protocol: dict[str, Any], lab: dict[str, Any]) -> None:
    register(lab, "L", contract_run(protocol, []))
    refs_before = (lab["dir"] / "references.json").read_text()
    ids = families_of(protocol, "long_tail", 3)
    assert len(ids) > beyond(protocol, "rate_drop_max", 40) - 1  # the last step is past it
    for lost in (ids[:1], ids[:2], ids[:3]):  # each step is a little worse than the last
        step = write_run(lab["dir"] / "step.json", contract_run(protocol, lost))
        assert mc.cmd_promote(step) == 1  # inside the tolerance or not, it is below L
    assert (lab["dir"] / "references.json").read_text() == refs_before


def test_a_candidate_inside_the_tolerance_passes_compare_and_still_cannot_lower_l(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "L", contract_run(protocol, []))
    below = write_run(
        lab["dir"] / "below.json", contract_run(protocol, families_of(protocol, "long_tail", 1))
    )
    assert mc.cmd_compare(below, ["L"], {}, record=False) == 0
    assert mc.cmd_promote(below) == 1


def test_a_candidate_that_fails_against_l_does_not_become_l(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    ids = families_of(protocol, "long_tail", 6)
    register(lab, "A", contract_run(protocol, ids))  # it would have passed the old anchor
    register(lab, "L", contract_run(protocol, []))
    before = (lab["dir"] / "references.json").read_bytes()
    cand = write_run(lab["dir"] / "cand.json", contract_run(protocol, ids[:3]))
    assert mc.cmd_promote(cand) == 1
    # as many answers as L and too slow: no rate is below L, so only the failed verdict stops it
    slow = 10.0 + protocol["rule"]["p95_rise_max_seconds"] + 1
    late = write_run(lab["dir"] / "late.json", with_contract(run(protocol, seconds=slow)))
    assert status(mc.compare(late, ["L"], {}), "p95 vs reference") == "FAIL"
    assert mc.cmd_promote(late) == 1
    assert (lab["dir"] / "references.json").read_bytes() == before


def test_promotion_writes_the_new_l_in_one_step_and_keeps_the_ledger_append_only(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    complete = contract_run(protocol, [])
    register(lab, "A", complete)
    register(lab, "L", complete)
    path = write_run(lab["dir"] / "next.json", complete)
    assert mc.cmd_promote(path) == 0
    refs = mc.load_refs()
    assert set(refs) == {"A", "L"} and refs["L"]["head"] == "f" * 40
    raw = (lab["dir"] / "references.json").read_bytes()
    assert b"\r\n" not in raw
    assert b"\r\n" not in (lab["dir"] / "ledger.jsonl").read_bytes()
    first = (lab["dir"] / "ledger.jsonl").read_bytes()
    assert mc.cmd_promote(path) == 0
    assert (lab["dir"] / "ledger.jsonl").read_bytes().startswith(first)


def test_promotion_is_a_single_write_of_the_references(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    complete = contract_run(protocol, [])
    register(lab, "A", complete)
    register(lab, "L", complete)
    writes: list[set[str]] = []
    original = mc.write_refs
    monkeypatch.setattr(mc, "write_refs", lambda refs: (writes.append(set(refs)), original(refs)))
    assert mc.cmd_promote(write_run(lab["dir"] / "next.json", complete)) == 0
    assert writes == [{"A", "L"}]  # never a state with no L


def test_a_pool_of_post_merge_runs_is_promoted_as_one_reference(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "L", contract_run(protocol, []))
    paths = [write_run(lab["dir"] / f"m{n}.json", contract_run(protocol, [])) for n in (1, 2)]
    assert mc.cmd_promote(paths) == 0
    assert [item["run"] for item in mc.load_refs()["L"]["runs"]] == paths
    other = with_contract(run(protocol, stamp={**STAMP, "head": "e" * 40}))
    mixed = [paths[0], write_run(lab["dir"] / "other.json", other)]
    assert mc.cmd_promote(mixed) == 1  # two heads are two codes, not one reference


def test_what_promote_writes_is_still_the_owners_to_commit(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    complete = contract_run(protocol, [])
    register(lab, "L", complete)
    refs_file = lab["dir"] / "references.json"
    before = refs_file.read_text()
    # promoted on one commit (f...) from a run produced on another (e...): the usual case
    produced = with_contract(run(protocol, stamp=stamped("e" * 40, "s1")))
    assert mc.cmd_promote(write_run(lab["dir"] / "next.json", produced)) == 0
    assert mc.load_refs()["L"]["head"] == "e" * 40

    repo = lab["dir"] / "repo"
    metrics = repo / "evidence" / "metrics"
    metrics.mkdir(parents=True)
    (metrics / "references.json").write_text(refs_file.read_text())
    (metrics / "ledger.jsonl").write_text((lab["dir"] / "ledger.jsonl").read_text())
    base = {"evidence/metrics/references.json": before, "evidence/metrics/ledger.jsonl": ""}
    monkeypatch.setattr(ci, "ROOT", repo)
    monkeypatch.setattr(ci, "_text_at", lambda ref, rel: base.get(rel))
    found = ci.check_metric_records_not_rewritten("origin/main")
    assert [v.where for v in found] == ["evidence/metrics/references.json"]  # a pass is not enough
    (metrics / "references.json").write_text(before)
    assert ci.check_metric_records_not_rewritten("origin/main") == []  # the record alone may land


# --- absolute checks ------------------------------------------------------------------------------


def test_a_p95_that_disagrees_with_its_trials_fails(protocol: dict[str, Any]) -> None:
    made = run(protocol, seconds=30.0)
    made.p95_reported = 5.0
    assert status(mc.absolute(made, protocol), "p95 matches trials") == "FAIL"
    assert status(mc.absolute([run(protocol), made], protocol), "p95 matches trials") == "FAIL"


def test_records_without_contract_fields_are_unknown_not_compliant(
    protocol: dict[str, Any],
) -> None:
    assert status(mc.absolute(run(protocol), protocol), "response contract") == "UNKNOWN"


def test_an_answer_missing_a_contract_field_fails(protocol: dict[str, Any]) -> None:
    trials = run(protocol).trials
    for trial in trials:
        trial.update(dict.fromkeys(mc.CONTRACT_KEYS, True))
    trials[0].update(has_moe=False)
    made = run(protocol, trials=trials)
    assert status(mc.absolute(made, protocol), "response contract") == "FAIL"
    pooled = mc.absolute([with_contract(run(protocol)), made], protocol)  # in either pooled run
    assert status(pooled, "response contract") == "FAIL"


def test_a_named_hard_failure_blocks_even_when_the_pooled_rate_rises(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "L", contract_run(protocol, families_of(protocol, "long_tail", 8)))
    better = contract_run(protocol, [])
    path = write_run(lab["dir"] / "better.json", better)
    assert mc.verdict(mc.compare(path, ["L"], {})) == "PASS"
    better.trials[0].update(has_moe=False)  # one answer of the better run carries no margins
    checks = mc.compare(write_run(lab["dir"] / "better.json", better), ["L"], {})
    assert row(checks, "long_tail trial rate").worse < 0  # the rate rose
    assert row(checks, "response contract").kind == "hard"
    assert status(checks, "response contract") == "FAIL"
    assert mc.verdict(checks) == "FAIL"


def test_floors_are_judged_on_the_pooled_candidate(
    protocol: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    budgets = {
        "quality": {"answered_rate_min": 0.7, "retrieval_at_10_min": 0.9, "selector_at_1_min": 0.7},
        "performance": {"p95_latency_seconds": 20.0},
    }
    monkeypatch.setattr(mc, "_budgets", lambda: budgets)
    scalars = {"retrieval_at_10": 0.9, "answered_rate": 1.0}
    high = run(protocol, scalars={**scalars, "selector_at_1": 0.9})
    low = run(protocol, scalars={**scalars, "selector_at_1": 0.6})
    assert status(mc.absolute(low, protocol), "selector_at_1 floor") == "FAIL"
    for pool in ([high, low], [low, high]):  # the mean, 0.75, whichever run comes first
        assert status(mc.absolute(pool, protocol), "selector_at_1 floor") == "PASS"
    slow = run(protocol, seconds=30.0)
    assert status(mc.absolute([run(protocol), slow], protocol), "p95 ceiling") == "FAIL"


# --- exceptions: a floor main already misses, recorded by the owner ----------------------------

BUDGETS = {
    "quality": {"answered_rate_min": 0.7, "retrieval_at_10_min": 0.9, "selector_at_1_min": 0.7},
    "performance": {"p95_latency_seconds": 20.0},
}


def exception(metric: str, baseline: float, **changed: Any) -> dict[str, Any]:
    made = {
        "metric": metric,
        "baseline": baseline,
        "approved": "2026-11-24 owner",
        "ticket": "CC-9",
    }
    return {**made, **changed}


def test_an_excepted_floor_does_not_block_while_no_worse_than_its_baseline(
    protocol: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    rule = protocol["rule"]
    monkeypatch.setattr(mc, "_budgets", lambda: dict(BUDGETS))
    slow = run(protocol, seconds=29.0)
    assert status(mc.absolute(slow, protocol), "p95 ceiling") == "FAIL"
    held = {**BUDGETS, "exception": [exception("p95_latency_seconds", 29.0)]}
    monkeypatch.setattr(mc, "_budgets", lambda: held)
    checks = mc.absolute(slow, protocol)
    assert status(checks, "p95 ceiling") == "EXCEPTED"
    assert "CC-9" in row(checks, "p95 ceiling").detail and "29" in row(checks, "p95 ceiling").detail
    assert mc.verdict([c for c in checks if c.name == "p95 ceiling"]) == "PASS"
    at_limit = run(protocol, seconds=29.0 + rule["p95_rise_max_seconds"])
    assert status(mc.absolute(at_limit, protocol), "p95 ceiling") == "EXCEPTED"
    worse = run(protocol, seconds=29.0 + rule["p95_rise_max_seconds"] + 0.01)
    assert status(mc.absolute(worse, protocol), "p95 ceiling") == "FAIL"  # worse, by the rule


@pytest.mark.parametrize(
    ("key", "limit", "tolerance"),
    [
        ("answered_rate", "answered_rate_min", "rate_drop_max"),
        ("selector_at_1", "selector_at_1_min", "selector_drop_max"),
        ("retrieval_at_10", "retrieval_at_10_min", "retrieval_drop_max"),
    ],
)
def test_each_quality_floor_is_excepted_by_its_own_rule_number(
    protocol: dict[str, Any], monkeypatch: pytest.MonkeyPatch, key: str, limit: str, tolerance: str
) -> None:
    baseline = 0.6
    held = {**BUDGETS, "exception": [exception(limit, baseline)]}
    monkeypatch.setattr(mc, "_budgets", lambda: held)
    scalars = {"retrieval_at_10": 0.95, "selector_at_1": 0.95, "answered_rate": 1.0}

    def scored(value: float) -> mc.Run:
        made = run(protocol, scalars={**scalars, key: value})
        if key == "answered_rate":  # keep what the run reports true to its trials
            made.scalars[key] = value
        return made

    step = protocol["rule"][tolerance]
    assert status(mc.absolute(scored(baseline - step), protocol), f"{key} floor") == "EXCEPTED"
    assert status(mc.absolute(scored(baseline - step - 0.01), protocol), f"{key} floor") == "FAIL"
    assert status(mc.absolute(scored(0.95), protocol), f"{key} floor") == "PASS"  # met: no need


@pytest.mark.parametrize(
    "entry",
    [
        exception("p95_latency_seconds", 29.0, ticket=""),
        exception("p95_latency_seconds", 29.0, approved=" "),
        exception("p95_latency_seconds", True),
        exception("p95_latency_seconds", "29"),
        exception("doc_lines", 1822),
        {"metric": "p95_latency_seconds", "baseline": 29.0},
        "p95_latency_seconds",
    ],
)
def test_a_malformed_exception_excuses_nothing(
    protocol: dict[str, Any], monkeypatch: pytest.MonkeyPatch, entry: Any
) -> None:
    held = {**BUDGETS, "exception": [exception("p95_latency_seconds", 29.0), entry]}
    assert mc.exception_problems(held)
    monkeypatch.setattr(mc, "_budgets", lambda: held)
    assert status(mc.absolute(run(protocol, seconds=29.0), protocol), "p95 ceiling") == "FAIL"


def test_an_exception_covers_only_its_own_metric(
    protocol: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # the baseline is one that would excuse a 29 s p95 if it were read as the p95's
    held = {**BUDGETS, "exception": [exception("answered_rate_min", 29.0)]}
    monkeypatch.setattr(mc, "_budgets", lambda: held)
    assert mc.exception_problems(held) == []
    assert status(mc.absolute(run(protocol, seconds=29.0), protocol), "p95 ceiling") == "FAIL"
    mine = {**BUDGETS, "exception": [exception("p95_latency_seconds", 29.0)]}
    monkeypatch.setattr(mc, "_budgets", lambda: mine)
    assert status(mc.absolute(run(protocol, seconds=29.0), protocol), "p95 ceiling") == "EXCEPTED"


# --- story targets --------------------------------------------------------------------------------


def test_a_target_already_met_is_preserved_with_no_gain_claimed(protocol: dict[str, Any]) -> None:
    base = run(protocol)
    checks = mc.target_check(base, base, protocol, "long_tail", 0.95)
    assert {c.status for c in checks} == {"PASS"}
    assert all("no gain claimed" in c.detail for c in checks)


def test_meeting_a_target_from_below_needs_a_proven_paired_gain(protocol: dict[str, Any]) -> None:
    ids = families_of(protocol, "long_tail", 40)
    candidate = run(protocol, losing("long_tail", ids[:1]))  # 97.5%, above the 95% target
    small = run(protocol, losing("long_tail", ids[:4]))  # 90%: three families gained
    large = run(protocol, losing("long_tail", ids[:12]))  # 70%: eleven families gained
    unproven = mc.target_check(candidate, small, protocol, "long_tail", 0.95)
    proven = mc.target_check(candidate, large, protocol, "long_tail", 0.95)
    assert status(unproven, "long_tail case") == "INCONCLUSIVE"
    assert status(proven, "long_tail case") == "PASS"


def test_a_zero_lower_bound_does_not_prove_a_gain(protocol: dict[str, Any]) -> None:
    ids = sorted(families_of(protocol, "long_tail", 40))[:6]
    reference = run(protocol, _long_tail_misses(ids, [1, 1, 1, 1, 1, 1]))
    candidate = run(protocol, _long_tail_misses(ids, [0, 0, 0, 0, 0, 2]))
    checks = mc.target_check(candidate, reference, protocol, "long_tail", 0.97)
    assert status(checks, "long_tail trial") == "INCONCLUSIVE"


def test_missing_the_target_fails_whatever_the_gain(protocol: dict[str, Any]) -> None:
    ids = families_of(protocol, "long_tail", 40)
    base = run(protocol, losing("long_tail", ids[:20]))
    candidate = run(protocol, losing("long_tail", ids[:8]))
    assert (
        status(mc.target_check(candidate, base, protocol, "long_tail", 0.95), "long_tail case")
        == "FAIL"
    )


def test_a_case_passes_only_if_every_repeat_answered(protocol: dict[str, Any]) -> None:
    ids = families_of(protocol, "long_tail", 40)
    partial = run(protocol, {("long_tail", ids[0], 3)})  # one repeat of three, in one question
    checks = mc.target_check(partial, run(protocol), protocol, "long_tail", 0.98)
    assert status(checks, "long_tail trial") == "PASS"  # 119 of 120 trials
    assert status(checks, "long_tail case") == "FAIL"  # 39 of 40 questions


def test_a_target_is_judged_against_the_reference_the_rows_were(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    ids = families_of(protocol, "long_tail", 40)
    register(lab, "L", contract_run(protocol, ids[:12]))
    cand = write_run(lab["dir"] / "cand.json", contract_run(protocol, []))
    checks = mc.compare(cand, ["L"], {"long_tail": 0.95})
    assert status(checks, "long_tail case", "target") == "PASS"
    assert "from 0.700" in row(checks, "long_tail case", "target").detail  # a gain over L's 70%
    # an anchor that is not registered has no runs to gain over: one set of target rows, not two
    both = mc.compare(cand, ["A0", "L"], {"long_tail": 0.95})
    assert [c.name for c in both if c.ref == "target"] == ["long_tail trial", "long_tail case"]


# --- findings of the cold review ---------------------------------------------------------------


def test_runs_with_no_index_hash_are_not_comparable(protocol: dict[str, Any]) -> None:
    base = run(protocol)
    base.index_hash = ""
    other = run(protocol)
    other.index_hash = ""
    assert status(mc.evaluate(other, base, "B", protocol), "index") == "FAIL"


def test_a_reported_answered_rate_that_the_trials_do_not_support_fails(
    protocol: dict[str, Any],
) -> None:
    made = run(protocol, losing("long_tail", families_of(protocol, "long_tail", 10)))
    made.scalars["answered_rate"] = 0.99
    assert status(mc.absolute(made, protocol), "answered_rate matches trials") == "FAIL"
    pooled = mc.absolute([run(protocol), made], protocol)  # one honest run does not cover another
    assert status(pooled, "answered_rate matches trials") == "FAIL"


def test_one_trial_without_contract_fields_is_unknown_not_a_crash(protocol: dict[str, Any]) -> None:
    trials = run(protocol).trials
    for trial in trials:
        trial.update(dict.fromkeys(mc.CONTRACT_KEYS, True))
    del trials[-1]["has_moe"]
    trials[-1]["tier"] = "long_tail"
    assert (
        status(mc.absolute(run(protocol, trials=trials), protocol), "response contract")
        == "UNKNOWN"
    )


def test_the_scorer_hash_sees_an_annotated_constant(
    protocol: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    protocol["scorer"]["symbols"] = ["LIMIT"]

    def hashed(source: str) -> str:
        monkeypatch.setattr(mc, "_source", lambda rel, head: source)
        return mc.scorer_hash(protocol)

    assert hashed("LIMIT: int = 1\n") != hashed("LIMIT: int = 2\n")


def test_a_family_outside_the_frozen_cohort_is_a_plan_error(protocol: dict[str, Any]) -> None:
    made = run(protocol)
    template = next(t for t in made.trials if t["tier"] == "long_tail")
    extra = [{**template, "id": "zz99", "repeat": n} for n in (1, 2, 3)]  # a complete family
    ids = [e["id"] for e in mc.cohort(protocol, "long_tail")]
    with pytest.raises(mc.PlanError):
        mc.families(run(protocol, trials=[*made.trials, *extra]), ids, "long_tail", 3)


def test_only_an_explicit_legacy_flag_skips_the_collection_check(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    complete = contract_run(protocol, [])
    path = write_run(lab["dir"] / "ref.json", complete)
    assert mc.cmd_register("S", path, "f" * 40, "strict", legacy=False) == 0
    assert mc.cmd_register("O", path, "a" * 40, "legacy-unfrozen-protocol", legacy=True) == 0
    # the flag decides, never the wording of the label
    assert mc.cmd_register("S2", path, "f" * 40, "legacy-looking label", legacy=False) == 0
    assert mc.cmd_register("O2", path, "a" * 40, "plain label", legacy=True) == 0
    refs = mc.load_refs()
    assert refs["S"]["hashes"]["protocol"] == "p1" and refs["S"]["hashes"]["collection"] == "k1"
    assert refs["S2"]["hashes"]["protocol"] == "p1"
    assert refs["O"]["hashes"]["protocol"] == "legacy"
    assert refs["O2"]["hashes"]["protocol"] == "legacy"
    lab["kept"]["collection"] = "k2"  # what a run collects changed after both were registered
    cand = write_run(lab["dir"] / "cand.json", contract_run(protocol, []))
    assert status(mc.compare(cand, ["S"], {}), "collection settings") == "FAIL"
    assert not any(c.name == "collection settings" for c in mc.compare(cand, ["O"], {}))


def test_the_register_command_passes_legacy_through_and_requires_a_label(
    lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[Any, bool]] = []
    monkeypatch.setattr(
        mc, "cmd_register", lambda *a, legacy=False: seen.append((a[1], legacy)) or 0
    )
    argv = ["metric_compare.py", "register", "L", "r.json", "--head", "a" * 40, "--label", "x"]
    monkeypatch.setattr(sys, "argv", argv)
    assert mc.main() == 0
    monkeypatch.setattr(sys, "argv", [*argv[:4], "r2.json", *argv[4:], "--legacy"])
    assert mc.main() == 0
    assert seen == [(["r.json"], False), (["r.json", "r2.json"], True)]
    monkeypatch.setattr(sys, "argv", argv[:-2])
    with pytest.raises(SystemExit):
        mc.main()


# --- findings of the third cold review --------------------------------------------------------


@pytest.mark.parametrize(
    "text", ["", "not json", "[]", '{"demo": {}}', '{"demo": {"repeat": "x"}}', '{"demo": null}']
)
def test_an_unusable_run_file_is_a_fail_row_not_a_bare_exception(
    protocol: dict[str, Any], lab: dict[str, Any], text: str
) -> None:
    bad = lab["dir"] / "bad.json"
    bad.write_text(text)
    assert status(mc.compare(str(bad), ["L"], {}), "candidate run file") == "FAIL"
    register(lab, "L", run(protocol))
    good = write_run(lab["dir"] / "good.json", run(protocol))
    more = write_run(lab["dir"] / "more.json", run(protocol))
    assert status(mc.compare([good, str(bad)], ["L"], {}), "candidate run file") == "FAIL"
    unusable = mc.compare([good, more], [], {}, [good, str(bad)])
    assert status(unusable, "reference run file") == "FAIL"
    refs = mc.load_refs()
    Path(refs["L"]["run"]).write_text(text)  # a reference whose file went bad...
    refs["L"]["run_sha256"] = hashlib.sha256(Path(refs["L"]["run"]).read_bytes()).hexdigest()
    (lab["dir"] / "references.json").write_text(json.dumps(refs))  # ...with its hash re-pinned
    checks = mc.compare(good, ["L"], {})
    assert status(checks, "reference run file") == "FAIL"


def test_a_regression_metric_the_reference_does_not_report_is_unknown_not_skipped(
    protocol: dict[str, Any],
) -> None:
    cand, ref = run(protocol), run(protocol)
    del ref.scalars["retrieval_at_10"]
    checks = mc.evaluate(cand, ref, "B", protocol)
    assert status(checks, "retrieval_at_10") == "UNKNOWN"
    assert mc.verdict(checks) == "UNKNOWN"


def test_the_ledger_row_names_every_run_file_by_hash(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    complete = contract_run(protocol, [])
    register(lab, "L", complete)
    paths = [write_run(lab["dir"] / f"p{n}.json", complete) for n in (1, 2)]
    main = [write_run(lab["dir"] / f"b{n}.json", complete) for n in (1, 2)]
    assert mc.cmd_compare(paths, ["L"], {}, True, main) == 0
    entry = json.loads((lab["dir"] / "ledger.jsonl").read_text().splitlines()[-1])
    for key, files in (("runs", paths), ("base", main)):
        assert [item["run"] for item in entry[key]] == files
        assert [item["run_sha256"] for item in entry[key]] == [
            hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in files
        ]
        assert {item["run_head"] for item in entry[key]} == {"f" * 40}
    assert entry["verdict"] == "PASS" and entry["hashes"]["collection"] == "k1"
    assert {c["kind"] for c in entry["checks"]} == {"rate", "hard"}


def test_an_interrupted_write_of_the_references_leaves_the_old_file_whole(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    register(lab, "L", run(protocol))
    before = (lab["dir"] / "references.json").read_bytes()

    def interrupted(src: object, dst: object) -> None:
        raise OSError("disk went away")

    monkeypatch.setattr(mc.os, "replace", interrupted)
    with pytest.raises(OSError):
        mc.write_refs({"L": {"head": "changed"}})
    assert (lab["dir"] / "references.json").read_bytes() == before


# --- findings of the Copilot review of the draft PR ---------------------------------------


@pytest.mark.parametrize("tier", ["core", "trap"])
def test_the_contract_is_checked_on_every_trial_that_returned_rows(
    protocol: dict[str, Any], tier: str
) -> None:
    made = with_contract(run(protocol))
    victim = next(t for t in made.trials if t["tier"] == tier)
    victim["has_geoid"] = False
    assert status(mc.absolute(made, protocol), "response contract") == "FAIL"


def test_an_unanswered_trial_that_still_returned_rows_must_meet_the_contract(
    protocol: dict[str, Any],
) -> None:
    made = with_contract(run(protocol))
    victim = next(t for t in made.trials if t["tier"] == "long_tail")
    victim.update(answered=False, rows=3, has_moe=False)  # scored a miss, yet it returned data
    assert status(mc.absolute(made, protocol), "response contract") == "FAIL"


def test_a_trial_that_returned_no_rows_owes_no_contract_field(protocol: dict[str, Any]) -> None:
    made = with_contract(run(protocol))
    victim = next(t for t in made.trials if t["tier"] == "trap")
    victim.update(rows=0, has_moe=False, has_universe=False)
    assert status(mc.absolute(made, protocol), "response contract") == "PASS"


def fast_extras(made: mc.Run, tier: str = "other") -> list[dict[str, Any]]:
    template = made.trials[0]
    return [{**template, "tier": tier, "id": f"x{n}", "latency_s": 0.1} for n in range(5000)]


def test_extra_fast_trials_in_another_tier_cannot_lower_the_p95(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    slow = with_contract(run(protocol, seconds=30.0))
    padded = run(protocol, trials=[*slow.trials, *fast_extras(slow)])
    assert mc.percentile([t["latency_s"] for t in padded.trials], 95) < 20  # the dodge works...
    path = write_run(lab["dir"] / "padded.json", padded)
    register(lab, "L", with_contract(run(protocol)))
    checks = mc.compare(path, ["L"], {})
    assert status(checks, "candidate run file") == "FAIL"  # ...unless the plan is enforced
    assert not any(c.name == "p95 ceiling" for c in checks)


def test_a_reference_padded_with_extra_trials_is_not_comparable(protocol: dict[str, Any]) -> None:
    base = with_contract(run(protocol))
    padded = run(protocol, trials=[*base.trials, *fast_extras(base)])
    checks = mc.evaluate(base, padded, "B", protocol)
    assert [c.name for c in checks] == ["planned trials"] and checks[0].status == "FAIL"


@pytest.mark.parametrize("damage", ["duplicate", "missing", "no repeat", "no id"])
def test_a_run_that_is_not_exactly_the_plan_is_a_plan_error(
    protocol: dict[str, Any], damage: str
) -> None:
    trials = run(protocol).trials
    if damage == "duplicate":
        trials.append(dict(trials[0]))
    elif damage == "missing":
        trials.pop()
    elif damage == "no repeat":
        del trials[0]["repeat"]
    else:
        del trials[0]["id"]
    with pytest.raises(mc.PlanError):
        mc.planned(run(protocol, trials=trials), protocol)
    mc.planned(run(protocol), protocol)  # the whole plan raises nothing


def stamped(head: str, scorer: str) -> dict[str, Any]:
    return {**STAMP, "head": head, "scorer": scorer}


def test_a_run_scored_by_an_older_scorer_is_judged_by_the_scorer_that_scored_it(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    old = "e" * 40
    heads = {old: {"scorer": "s0", "cohorts": {"c": "h"}, "protocol": "p1"}}
    monkeypatch.setattr(mc, "hashes", lambda head=None: dict(heads.get(head, lab["now"])))
    register(lab, "L", with_contract(run(protocol)))  # L was scored by s1, the scorer checked out
    stale = with_contract(run(protocol, stamp=stamped(old, "s0")))  # the candidate by s0
    checks = mc.compare(write_run(lab["dir"] / "stale.json", stale), ["L"], {})
    assert status(checks, "scorer / cohort hashes") == "FAIL"  # the checkout's s1 must not hide it


def test_hashes_a_run_records_must_be_those_of_its_head(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "L", with_contract(run(protocol)))
    lying = with_contract(run(protocol, stamp=stamped("e" * 40, "s9")))  # the checkout says s1
    checks = mc.compare(write_run(lab["dir"] / "lying.json", lying), ["L"], {})
    assert status(checks, "provenance") == "FAIL"


def test_a_head_that_cannot_be_checked_is_a_failure_not_a_crash(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def unknown_head(head: str | None = None) -> dict[str, Any]:
        if head:
            raise mc.subprocess.CalledProcessError(128, "git show")
        return dict(lab["now"])

    monkeypatch.setattr(mc, "hashes", unknown_head)
    register(lab, "L", with_contract(run(protocol)))
    cand = write_run(lab["dir"] / "cand.json", with_contract(run(protocol)))
    assert status(mc.compare(cand, ["L"], {}), "provenance") == "FAIL"
    more = write_run(lab["dir"] / "more.json", with_contract(run(protocol)))
    main = [write_run(lab["dir"] / f"b{n}.json", with_contract(run(protocol))) for n in (1, 2)]
    assert status(mc.compare([cand, more], [], {}, main), "same-window main") == "FAIL"


# --- a run is bound to what it collected, not to the rule that judges it ---------------------


def test_a_run_collected_under_other_collection_settings_is_refused(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    register(lab, "L", with_contract(run(protocol)))
    at = {"e" * 40: "k0"}  # the protocol at the run's head collected differently
    monkeypatch.setattr(mc, "collection_at", lambda head=None: at.get(head, "k1"))
    other = with_contract(run(protocol, stamp=stamped("e" * 40, "s1")))
    checks = mc.compare(write_run(lab["dir"] / "other.json", other), ["L"], {})
    assert status(checks, "provenance") == "FAIL"
    assert status(checks, "collection settings") == "FAIL"  # and it is not L's collection either


def test_a_run_collected_before_a_rule_change_is_judged_under_the_new_rule(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    ids = families_of(protocol, "long_tail", 40)
    register(lab, "L", contract_run(protocol, []))
    # stamped under another protocol file ("p0"): only its rule differed, so what it collected
    # (the collection hash at its head) is today's
    earlier = with_contract(
        run(protocol, losing("long_tail", ids[:2]), stamp={**STAMP, "protocol": "p0"})
    )
    path = write_run(lab["dir"] / "earlier.json", earlier)
    lab["now"]["protocol"] = "p2"  # and the file has changed again since
    checks = mc.compare(path, ["L"], {})
    assert not any(c.name in ("provenance", "collection settings") for c in checks)
    assert status(checks, "long_tail trial rate") == "PASS"  # 2 of 40: inside today's tolerance
    protocol["rule"]["rate_drop_max"] = 0.01  # the rule is tightened; the same stored run...
    assert status(mc.compare(path, ["L"], {}), "long_tail trial rate") == "FAIL"  # ...now fails


def test_the_collection_hash_ignores_the_rule_and_moves_with_what_a_run_collects(
    protocol: dict[str, Any],
) -> None:
    before = mc.collection_hash(protocol)
    judged = copy.deepcopy(protocol)
    judged["rule"]["rate_drop_max"] = 0.01
    judged["rule"]["report_only"] = []
    judged["sampling"].update(confidence=0.99, resamples=5, min_families=50, seed=1)
    judged["version"] = 2
    assert mc.collection_hash(judged) == before
    for section, key, value in (
        ("sampling", "repeat", 5),
        ("sampling", "blocks", "B,P"),
        ("sampling", "stopping", "optional"),
        ("sampling", "exclusions", ["q01"]),
        ("selection", "exclude_flags", []),
        ("scorer", "symbols", ["is_answered"]),
        ("scorer", "source", "scripts/other.py"),
        ("cohorts", "long_tail", {"source": "evals/golden_questions.toml", "tier": "core"}),
    ):
        collected = copy.deepcopy(protocol)
        collected[section][key] = value
        assert mc.collection_hash(collected) != before, (section, key)


def test_a_run_with_no_provenance_is_unknown_and_can_never_be_promoted(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "L", with_contract(run(protocol)))
    legacy = write_run(lab["dir"] / "legacy.json", with_contract(run(protocol, stamp={})))
    assert status(mc.compare(legacy, ["L"], {}), "provenance") == "UNKNOWN"
    stamped_run = write_run(lab["dir"] / "stamped.json", with_contract(run(protocol)))
    assert status(mc.compare([stamped_run, legacy], ["L"], {}), "provenance") == "UNKNOWN"
    before = (lab["dir"] / "references.json").read_bytes()
    assert mc.cmd_promote(legacy) == 1
    assert (lab["dir"] / "references.json").read_bytes() == before


def test_pooled_candidate_runs_must_have_measured_one_head(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "L", with_contract(run(protocol)))
    one = write_run(lab["dir"] / "one.json", with_contract(run(protocol)))
    other = with_contract(run(protocol, stamp=stamped("e" * 40, "s1")))
    two = write_run(lab["dir"] / "two.json", other)
    assert not any(c.name == "provenance" for c in mc.compare([one, one], ["L"], {}))
    assert status(mc.compare([one, two], ["L"], {}), "provenance") == "FAIL"


def test_a_partial_provenance_record_counts_as_none(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    path = write_run(lab["dir"] / "partial.json", with_contract(run(protocol)))
    body = json.loads(Path(path).read_text())
    del body["demo"]["provenance"]["scorer"]
    Path(path).write_text(json.dumps(body))
    assert mc.load_run(path).hashes == {}


def test_promotion_labels_the_run_with_the_head_that_produced_it(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    producing = "e" * 40
    register(lab, "L", with_contract(run(protocol)))
    mine = with_contract(run(protocol, stamp=stamped(producing, "s1")))
    assert mc.cmd_promote(write_run(lab["dir"] / "next.json", mine)) == 0
    assert mc.load_refs()["L"]["head"] == producing  # not the "f" * 40 that is checked out


# --- findings of the fourth cold review ---------------------------------------------------------


def test_a_run_whose_head_is_not_a_full_sha_has_no_usable_provenance(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    for bad in ("HEAD", "main", "--output=x", "abc1234", "E" * 40, 7):
        made = with_contract(run(protocol, stamp=stamped(bad, "s1")))  # type: ignore[arg-type]
        assert mc.load_run(write_run(lab["dir"] / "r.json", made)).hashes == {}, bad


def test_a_run_of_code_that_changed_since_its_head_is_refused(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    register(lab, "L", with_contract(run(protocol)))
    cand = write_run(lab["dir"] / "cand.json", with_contract(run(protocol)))
    assert not any(c.name == "provenance" for c in mc.compare(cand, ["L"], {}))
    monkeypatch.setattr(mc, "_same_code", lambda head: False)
    assert status(mc.compare(cand, ["L"], {}), "provenance") == "FAIL"


def test_same_code_and_reachability_are_asked_of_real_git() -> None:
    head = mc._head()
    assert mc._same_code(head) and mc._reachable(head, "HEAD")
    assert not mc._reachable("0" * 40, "HEAD")
    assert not mc._same_code("0" * 40)


def test_the_code_comparison_covers_the_measured_code(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(mc, "_git_status", lambda *args: seen.append(args) or 1)
    assert mc._same_code("a" * 40) is False
    assert "api/src" in seen[0] and "scripts/run_demo.py" in seen[0] and "a" * 40 in seen[0]


def test_promotion_needs_a_head_that_reached_main(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    register(lab, "L", with_contract(run(protocol)))
    before = (lab["dir"] / "references.json").read_bytes()
    path = write_run(lab["dir"] / "next.json", with_contract(run(protocol)))
    asked: list[tuple[str, str]] = []
    monkeypatch.setattr(mc, "_reachable", lambda c, t: asked.append((c, t)) or False)
    assert mc.cmd_promote(path) == 1
    assert asked == [("f" * 40, mc.MAIN)]
    assert (lab["dir"] / "references.json").read_bytes() == before
    assert not (lab["dir"] / "ledger.jsonl").exists()  # refused before any record is written


def test_the_cohorts_a_run_records_must_be_those_of_its_head_too(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "L", with_contract(run(protocol)))
    wrong = with_contract(run(protocol, stamp={**STAMP, "cohorts": {"c": "other"}}))
    checks = mc.compare(write_run(lab["dir"] / "wrong.json", wrong), ["L"], {})
    assert status(checks, "provenance") == "FAIL"


def test_a_head_whose_goldens_are_unreadable_is_a_failure_not_a_traceback(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreadable(head: str | None = None) -> dict[str, Any]:
        if head:
            raise KeyError("question")
        return dict(lab["now"])

    monkeypatch.setattr(mc, "hashes", unreadable)
    register(lab, "L", with_contract(run(protocol)))
    cand = write_run(lab["dir"] / "cand.json", with_contract(run(protocol)))
    assert status(mc.compare(cand, ["L"], {}), "provenance") == "FAIL"


def test_a_bridge_is_looked_up_by_the_scorer_that_scored_the_candidate(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    scored_by = "e" * 40
    heads = {scored_by: {"scorer": "s2", "cohorts": {"c": "h"}, "protocol": "p1"}}
    monkeypatch.setattr(mc, "hashes", lambda head=None: dict(heads.get(head, lab["now"])))
    ids = families_of(protocol, "long_tail", 6)
    register(lab, "L", with_contract(run(protocol, losing("long_tail", ids))), scorer="s0")
    rescored = write_run(lab["dir"] / "rescored.json", with_contract(run(protocol)))
    # to the candidate's scorer s2; the checkout has s1
    (lab["dir"] / "bridges.json").write_text(json.dumps([bridge_to(rescored, "s2")]))
    cand = with_contract(run(protocol, stamp=stamped(scored_by, "s2")))
    checks = mc.compare(write_run(lab["dir"] / "cand.json", cand), ["L"], {})
    assert "bridged" in row(checks, "reference label").detail


@pytest.mark.parametrize(
    "damage", [{"answered": None}, {"latency_s": None}, {"latency_s": float("nan")}]
)
def test_a_trial_the_metrics_cannot_read_is_a_bad_file_not_a_traceback(
    protocol: dict[str, Any], lab: dict[str, Any], damage: dict[str, Any]
) -> None:
    made = with_contract(run(protocol))
    victim = made.trials[0]
    for key, value in damage.items():
        if value is None:
            del victim[key]
        else:
            victim[key] = value
    cand = write_run(lab["dir"] / "cand.json", made)
    assert status(mc.compare(cand, ["L"], {}), "candidate run file") == "FAIL"


# --- the whole chain, with nothing stubbed but the directory ------------------------------------


def test_register_compare_promote_and_the_records_guard_agree_with_real_hashes_and_git(
    protocol: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mc, "METRICS", tmp_path)
    monkeypatch.setattr(mc, "load_protocol", lambda head=None: protocol)
    monkeypatch.setattr(mc, "MAIN", "HEAD")  # this checkout is a branch, not main
    head = mc._head()
    stamp = {
        "head": head,
        **mc.hashes(),
        "dirty": False,
    }  # real scorer, cohort and protocol hashes at real HEAD

    def produce(name: str) -> str:
        made = with_contract(run(protocol, stamp=stamp))
        return write_run(tmp_path / f"{name}.json", made)

    main = [produce("b1"), produce("b2")]
    assert mc.cmd_register("L", main, head, "anchor") == 0  # the seed: two runs of main
    candidate = [produce("p1"), produce("p2")]
    assert mc.cmd_compare(candidate, ["L"], {}, False, main) == 0  # PASS: nothing stubbed
    before = {
        "evidence/metrics/references.json": (tmp_path / "references.json").read_text(),
        "evidence/metrics/ledger.jsonl": "",
    }
    assert mc.cmd_promote(candidate) == 0
    refs = mc.load_refs()
    assert refs["L"]["head"] == head and refs["L"]["runs"][0]["run"].endswith("p1.json")

    repo = tmp_path / "repo"
    (repo / "evidence" / "metrics").mkdir(parents=True)
    (repo / "evidence" / "metrics" / "ledger.jsonl").write_text(
        (tmp_path / "ledger.jsonl").read_text()
    )
    monkeypatch.setattr(ci, "ROOT", repo)
    monkeypatch.setattr(ci, "_text_at", lambda ref, rel: before.get(rel))
    for landed in (tmp_path / "references.json").read_text(), "{}":  # moved, and removed
        (repo / "evidence" / "metrics" / "references.json").write_text(landed)
        assert ci.check_metric_records_not_rewritten("origin/main")  # L is the owner's to land
    (repo / "evidence" / "metrics" / "references.json").write_text(
        before["evidence/metrics/references.json"]
    )
    assert ci.check_metric_records_not_rewritten("origin/main") == []  # the appended record may


def test_a_worse_candidate_is_rejected_by_the_same_real_chain(
    protocol: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mc, "METRICS", tmp_path)
    monkeypatch.setattr(mc, "load_protocol", lambda head=None: protocol)
    monkeypatch.setattr(mc, "MAIN", "HEAD")
    head = mc._head()
    stamp = {"head": head, **mc.hashes(), "dirty": False}
    anchor = write_run(tmp_path / "a.json", with_contract(run(protocol, stamp=stamp)))
    assert mc.cmd_register("L", anchor, head, "anchor") == 0
    ids = families_of(protocol, "long_tail", beyond(protocol, "rate_drop_max", 40))
    worse = with_contract(run(protocol, losing("long_tail", ids), stamp=stamp))
    path = write_run(tmp_path / "p.json", worse)
    refs_before = (tmp_path / "references.json").read_bytes()
    assert status(mc.compare(path, ["L"], {}), "long_tail trial rate") == "FAIL"
    assert mc.cmd_promote(path) == 1
    assert (tmp_path / "references.json").read_bytes() == refs_before


# --- the committed files -------------------------------------------------------------------------


def test_editing_an_expectation_moves_the_cohort_hash_and_nothing_else(
    protocol: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    goldens = mc.goldens(protocol)
    before = mc.cohort_hashes(protocol)
    edited = [
        dict(e, expect_table="B00000") if e["id"] == mc.cohort(protocol, "trap")[0]["id"] else e
        for e in goldens
    ]
    monkeypatch.setattr(mc, "goldens", lambda proto, head=None: edited)
    after = mc.cohort_hashes(protocol)
    assert after["trap"] != before["trap"]
    assert after["long_tail"] == before["long_tail"] and after["core"] == before["core"]


def test_freeze_prints_the_hashes_and_every_rule_number(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert mc.cmd_freeze() == 0
    out = capsys.readouterr().out
    protocol = mc.load_protocol()
    assert mc.protocol_hash() in out and mc.scorer_hash(protocol) in out
    assert mc.collection_hash(protocol) in out
    for name, digest in mc.cohort_hashes(protocol).items():
        assert name in out and digest in out
    for key, value in protocol["rule"].items():
        assert key in out, key
        if not isinstance(value, bool | list):
            assert f"{key} = {value:g}" in out, key


def test_every_rate_row_is_judged_by_a_number_in_the_committed_rule() -> None:
    rule = mc.load_protocol()["rule"]
    numbers = {key for key, value in rule.items() if mc._number(value)}
    judged = set(mc.RATE_ROWS.values()) | {"small_group_lost_questions"}
    # the last two are the numbers of the hard rows "same-window main" and "lost questions"
    assert judged | {"window_hours", "lost_questions_min_runs"} == numbers


def test_every_row_compare_prints_is_a_rate_with_a_rule_or_a_named_hard_failure(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    def known(check: mc.Check) -> bool:
        if check.kind == "rate":
            return any(check.name.endswith(name) for name in mc.RATE_ROWS)
        return check.kind == "hard" and (check.name in mc.HARD_ROWS or check.ref == "target")

    ids = families_of(protocol, "long_tail", 40)
    register(lab, "L", contract_run(protocol, ids[:12]))
    register(lab, "A", contract_run(protocol, []), scorer="s0")
    good = write_run(lab["dir"] / "good.json", contract_run(protocol, []))
    more = write_run(lab["dir"] / "more.json", contract_run(protocol, []))
    main = [write_run(lab["dir"] / f"b{n}.json", contract_run(protocol, [])) for n in (1, 2)]
    bare = write_run(lab["dir"] / "bare.json", run(protocol, stamp={}))
    seen = [
        *mc.compare([good, more], ["A", "A0", "L"], {"long_tail": 0.95}, main),
        *mc.compare([good, good], ["L"], {}, main),
        *mc.compare(bare, ["L"], {}),
        *mc.compare(good, ["L"], {}, main),
        *mc.compare(str(lab["dir"] / "absent.json"), ["L"], {}),
    ]
    assert len({(c.kind, c.name) for c in seen}) > 15
    assert [c for c in seen if not known(c)] == []
    assert {c.kind for c in seen if c.name.endswith("trial rate")} == {"rate"}
    assert {c.kind for c in seen if c.ref == "floor"} == {"hard"}


def test_the_committed_anchors_are_registered_whole_and_unaltered() -> None:
    refs = mc.load_refs()
    assert {"A", "A0"} <= set(refs)
    for name in ("A", "A0"):
        entry = refs[name]
        assert mc._pinned(mc.entry_runs(entry)), name
        assert entry["hashes"]["protocol"] == "legacy" and entry["blockers"] is not None
    assert refs["A"]["head"].startswith("69d7364") and refs["A0"]["head"].startswith("4b24f77")


# --- findings of the /code-review pass -----------------------------------------------------------


def test_a_run_that_measured_uncommitted_code_is_refused(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "L", with_contract(run(protocol)))
    dirty = with_contract(run(protocol, stamp={**STAMP, "dirty": True}))
    checks = mc.compare(write_run(lab["dir"] / "dirty.json", dirty), ["L"], {})
    assert status(checks, "provenance") == "FAIL"
    clean = write_run(lab["dir"] / "clean.json", with_contract(run(protocol)))
    assert not any(c.name == "provenance" for c in mc.compare(clean, ["L"], {}))


def test_a_stamp_without_the_dirty_flag_counts_as_no_provenance(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    old = {k: v for k, v in STAMP.items() if k != "dirty"}
    made = with_contract(run(protocol, stamp=old))
    assert mc.load_run(write_run(lab["dir"] / "old.json", made)).hashes == {}


def test_the_code_comparison_covers_the_dependency_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(mc, "_git_status", lambda *args: seen.append(args) or 0)
    assert mc._same_code("a" * 40) is True
    assert {"pyproject.toml", "uv.lock", "api/src", "scripts/run_demo.py"} <= set(seen[0])


# --- the stored runs: two of unchanged main, two of the CC-104 branch ---------------------------

STORED = ("main-b1", "main-b2", "cc104-p1", "cc104-p2")
# each pair is one code measured twice; either run could have been the candidate
SAME_CODE = [
    ("main-b1", "main-b2"),
    ("main-b2", "main-b1"),
    ("cc104-p1", "cc104-p2"),
    ("cc104-p2", "cc104-p1"),
]
# Written before any number in [rule] was chosen (it is in git before evals/metric_protocol.toml
# has a [rule]): a defect that breaks this many of the 40 long_tail questions, 15 points, must fail
# the long_tail rate row whichever stored run it is seeded in.
BROKEN_LONG_TAIL = 6
RUNS = ROOT / "evidence" / "metrics" / "runs"
PLAN = json.loads((RUNS / "plan-29c0518.json").read_text(encoding="utf-8"))
ZCTA = "zip code tabulation area"


@functools.cache
def stored_run(name: str) -> mc.Run:
    """Shared between tests and never changed: `broken` copies."""
    return mc.load_run(f"evidence/metrics/runs/{name}.json")


@pytest.fixture
def stored(protocol: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """The protocol over the questions the stored runs asked (main 29c0518), so that a later
    golden edit does not turn every stored-run test into a plan error."""
    monkeypatch.setattr(mc, "goldens", lambda protocol, head=None: PLAN)
    return protocol


def working(made: mc.Run, tier: str, count: int) -> list[str]:
    """The first `count` questions of a tier, by id, that answered in every trial of the run."""
    by_id: dict[str, list[bool]] = {}
    for trial in made.trials:
        if trial["tier"] == tier:
            by_id.setdefault(trial["id"], []).append(bool(trial["answered"]))
    found = sorted(family for family, answers in by_id.items() if all(answers))[:count]
    assert len(found) == count  # fewer working questions than asked for would seed a smaller defect
    return found


def broken(made: mc.Run, ids: list[str]) -> mc.Run:
    """A copy of a run in which the named questions answer nothing, in every trial."""
    trials = [
        {**trial, "answered": False, "rows": 0} if trial["id"] in ids else dict(trial)
        for trial in made.trials
    ]
    tail = [t for t in trials if t["tier"] == "long_tail"]
    rate = round(sum(t["answered"] for t in tail) / len(tail), 3)
    return mc.Run(
        path=f"{made.path} with {len(ids)} broken",
        repeat=made.repeat,
        index_hash=made.index_hash,
        p95_reported=made.p95_reported,
        scalars={**made.scalars, "answered_rate": rate},
        trials=trials,
        hashes=dict(made.hashes),
    )


def test_the_four_stored_runs_are_two_codes_each_measured_twice(stored: dict[str, Any]) -> None:
    heads = {name: stored_run(name).hashes["head"] for name in STORED}
    assert heads["main-b1"] == heads["main-b2"] != heads["cc104-p1"] == heads["cc104-p2"]
    assert heads["main-b1"].startswith("29c0518") and heads["cc104-p1"].startswith("e86882d")
    for name in STORED:
        mc.planned(stored_run(name), stored)  # every planned trial, none extra
        assert stored_run(name).hashes["dirty"] is False
    assert len({stored_run(name).index_hash for name in STORED}) == 1


@pytest.mark.parametrize(("candidate", "reference"), SAME_CODE)
def test_both_stored_same_code_pairs_pass_either_way_round(
    candidate: str, reference: str, stored: dict[str, Any]
) -> None:
    checks = mc.evaluate(stored_run(candidate), stored_run(reference), "B", stored)
    assert [c.name for c in checks if c.blocking and c.status != "PASS"] == []
    assert mc.verdict(checks) == "PASS"


@pytest.mark.parametrize(("seeded_in", "partner"), SAME_CODE)
def test_a_stored_run_with_the_stated_number_of_long_tail_questions_broken_fails(
    seeded_in: str, partner: str, stored: dict[str, Any]
) -> None:
    healthy = stored_run(seeded_in)
    damaged = broken(healthy, working(healthy, "long_tail", BROKEN_LONG_TAIL))
    checks = mc.evaluate(damaged, stored_run(partner), "B", stored)
    assert status(checks, "long_tail trial rate") == "FAIL"
    assert mc.verdict(checks) == "FAIL"


def test_the_stored_candidate_runs_are_pooled_against_the_stored_main_runs(
    stored: dict[str, Any],
) -> None:
    main = [stored_run("main-b1"), stored_run("main-b2")]
    cands = [stored_run("cc104-p1"), stored_run("cc104-p2")]
    pooled = mc.sample(cands, stored)
    assert {len(t) for group in pooled.trials.values() for t in group.values()} == {6}
    checks = mc.evaluate(cands, main, "B", stored)
    each = [mc.evaluate(one, main, "B", stored) for one in cands]
    rate = row(checks, "long_tail trial rate").worse
    mean = sum(row(c, "long_tail trial rate").worse for c in each) / 2
    assert rate == pytest.approx(mean, abs=1e-5)
    assert {c.status for c in checks} <= {"PASS", "FAIL"}  # a verdict on every row, none open


@pytest.mark.parametrize(("seeded_in", "partner"), SAME_CODE)
def test_the_question_level_rule_names_every_question_of_a_broken_geography(
    seeded_in: str, partner: str, stored: dict[str, Any]
) -> None:
    seeded = sorted(q["id"] for q in PLAN if q["expect_geo_level"] == ZCTA)
    assert len(seeded) == 2  # too few questions for any rate row to be sure of
    damaged = mc.sample([broken(stored_run(seeded_in), seeded)], stored)
    lost = mc.lost_questions(damaged, mc.sample([stored_run(partner)], stored))
    assert set(seeded) <= set(lost)


def test_the_question_level_rule_fires_on_unchanged_main_at_one_run_per_side(
    stored: dict[str, Any],
) -> None:
    alarms = {
        pair: mc.lost_questions(
            mc.sample([stored_run(pair[0])], stored), mc.sample([stored_run(pair[1])], stored)
        )
        for pair in SAME_CODE
    }
    # unchanged main answered q20 in all three trials of one run and in none of the other
    assert alarms == {**dict.fromkeys(SAME_CODE, []), ("main-b2", "main-b1"): ["q20"]}
    # so at one run per side it is not adopted (AC10): it is reported there, and blocks from two
    assert mc.load_protocol()["rule"]["lost_questions_min_runs"] == 2
    checks = mc.evaluate(stored_run("main-b2"), stored_run("main-b1"), "B", stored)
    assert (
        status(checks, "lost questions") == "FAIL" and "q20" in row(checks, "lost questions").detail
    )
    assert not row(checks, "lost questions").blocking
    assert mc.verdict(checks) == "PASS"  # reported, and the unchanged code still passes


def test_the_question_level_rule_blocks_when_each_side_pools_two_runs(
    stored: dict[str, Any],
) -> None:
    main = [stored_run("main-b1"), stored_run("main-b2")]
    seeded = sorted(q["id"] for q in PLAN if q["expect_geo_level"] == ZCTA)
    damaged = [broken(stored_run(name), seeded) for name in ("cc104-p1", "cc104-p2")]
    checks = mc.evaluate(damaged, main, "B", stored)
    lost = row(checks, "lost questions")
    assert lost.blocking and lost.status == "FAIL" and all(q in lost.detail for q in seeded)
    assert mc.verdict(checks) == "FAIL"
    for cands, refs in ((damaged[:1], main), (damaged, main[:1]), (damaged[:1], main[:1])):
        one_sided = row(mc.evaluate(cands, refs, "B", stored), "lost questions")
        assert one_sided.status == "FAIL" and not one_sided.blocking  # one run on a side: reported
    # the question unchanged main lost between its two runs is not lost against their pool
    pooled, later = mc.sample(main, stored), mc.sample(main[1:], stored)
    assert "q20" not in mc.lost_questions(later, pooled)


def test_a_question_lost_in_both_pooled_runs_fails_a_verdict_the_rates_would_pass(
    protocol: dict[str, Any],
) -> None:
    one = families_of(protocol, "long_tail", 1)  # 2.5 points: inside every rate tolerance
    whole = [run(protocol), run(protocol)]
    lost = [wrong_table_run(protocol, one), wrong_table_run(protocol, one)]
    pooled = mc.evaluate(lost, whole, "B", protocol)
    assert [c.name for c in pooled if c.blocking and c.status != "PASS"] == ["lost questions"]
    assert mc.verdict(pooled) == "FAIL"
    single = mc.evaluate(lost[0], whole[0], "B", protocol)
    assert status(single, "lost questions") == "FAIL" and mc.verdict(single) == "PASS"
    protocol["rule"]["lost_questions_min_runs"] = 1  # the owner may tighten it to every size
    assert mc.verdict(mc.evaluate(lost[0], whole[0], "B", protocol)) == "FAIL"
    protocol["rule"]["lost_questions_min_runs"] = float("nan")  # not a number: it blocks anyway
    assert row(mc.evaluate(lost[0], whole[0], "B", protocol), "lost questions").blocking
    protocol["rule"]["lost_questions_min_runs"] = 3  # more runs than either side pools
    assert not row(mc.evaluate(lost, whole, "B", protocol), "lost questions").blocking


def test_the_selector_tolerance_is_divided_by_the_runs_pooled_on_the_smaller_side(
    protocol: dict[str, Any],
) -> None:
    limit = protocol["rule"]["selector_drop_max"]

    def scored(value: float) -> mc.Run:
        scalars = {"retrieval_at_10": 0.9, "selector_at_1": value, "answered_rate": 1.0}
        return run(protocol, scalars=scalars)

    def judged(cands: int, refs: int, drop: float) -> str:
        checks = mc.evaluate([scored(0.9 - drop)] * cands, [scored(0.9)] * refs, "B", protocol)
        return status(checks, "selector_at_1")

    assert judged(1, 1, limit) == "PASS" and judged(1, 1, limit + 0.01) == "FAIL"
    assert judged(2, 2, limit / 2) == "PASS" and judged(2, 2, limit / 2 + 0.01) == "FAIL"
    assert judged(4, 4, limit / 4) == "PASS" and judged(4, 4, limit / 4 + 0.01) == "FAIL"
    # one post-merge run against a pooled L, or two against one: the smaller side decides
    assert judged(1, 2, limit) == "PASS" and judged(1, 2, limit + 0.01) == "FAIL"
    assert judged(2, 1, limit) == "PASS" and judged(2, 1, limit + 0.01) == "FAIL"


def test_a_stored_run_collected_before_the_rule_existed_is_judged_under_todays_rule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # nothing stubbed but the code comparison: the real protocol file, at the run's real head
    made = stored_run("main-b1")
    assert made.hashes["protocol"] != mc.protocol_hash()  # the file it ran under had no [rule]
    assert mc.collection_at(made.hashes["head"]) == mc.collection_at()  # what it collected: same
    # main moves on after these runs; whether the code is still theirs is tested apart
    monkeypatch.setattr(mc, "_same_code", lambda head: True)
    judged, problems = mc.provenance_checks(made, mc.judged_by())
    assert problems == [] and judged["collection"] == mc.collection_at()


# --- noise: how often unchanged code fails, and what the rule can catch -----------------------


def group(*names: str) -> list[mc.Run]:
    return [stored_run(name) for name in names]


def test_unchanged_code_seldom_fails_its_own_simulated_reruns(stored: dict[str, Any]) -> None:
    for names in (("main-b1", "main-b2"), ("cc104-p1", "cc104-p2")):
        src = mc.stored(group(*names), stored)
        fails, rows, worse = mc.simulate(src, (2, 2), stored, random.Random(7), 200)
        assert fails <= 20, names  # under 10% at the size the gate runs at
        assert sum(rows.values()) >= fails
        assert set(worse) >= {"long_tail trial rate", "p95 vs reference", "selector_at_1"}
        assert all(len(values) == 200 for values in worse.values())


def test_a_seeded_regression_is_caught_more_often_the_larger_it_is(stored: dict[str, Any]) -> None:
    src = mc.stored(group("main-b1", "main-b2"), stored)
    rng = random.Random(7)
    none, _rows, _worse = mc.simulate(src, (2, 2), stored, rng, 120)
    small, _rows, _worse = mc.simulate(src, (2, 2), stored, rng, 120, broken=1)
    large, _rows, _worse = mc.simulate(src, (2, 2), stored, rng, 120, broken=8)
    assert none <= small < large
    assert large >= 0.95 * 120  # 20 points of the long tail cannot slip through


def test_a_broken_question_in_a_simulated_run_is_never_answered(stored: dict[str, Any]) -> None:
    src = mc.stored(group("main-b1", "main-b2"), stored)
    victim = working(stored_run("main-b1"), "long_tail", 1)[0]
    drawn = mc.draw(src, 2, 3, random.Random(1), frozenset({victim}))
    assert len(drawn.trials["long_tail"][victim]) == 6
    assert not any(answered for answered, _rows in drawn.trials["long_tail"][victim])
    assert any(rows for _answered, rows in drawn.trials["long_tail"][victim])  # a miss, not empty
    healthy = mc.draw(src, 2, 3, random.Random(1))
    assert all(answered for answered, _rows in healthy.trials["long_tail"][victim])
    assert len(drawn.seconds) == 2 * len(stored_run("main-b1").trials)


def test_a_simulated_run_takes_its_scalars_from_one_stored_run(stored: dict[str, Any]) -> None:
    src = mc.stored(group("main-b1", "main-b2"), stored)
    seen = {mc.draw(src, 1, 3, random.Random(n)).scalars["selector_at_1"] for n in range(30)}
    assert seen == {0.75, 0.425}  # never a blend: the swing between two runs is kept whole


def test_stored_same_code_comparisons_are_observed_each_way_at_a_size_they_can_fill(
    stored: dict[str, Any],
) -> None:
    main = group("main-b1", "main-b2")
    assert mc.observed(main, (1, 1), stored) == [[]]  # one pair: both ways round, both pass
    assert mc.observed(main, (2, 2), stored) == []  # four runs of one code are needed
    assert mc.observed(main, (1, 2), stored) == []
    assert len(mc.observed([*main, *main], (2, 2), stored)) == 1
    assert len(mc.observed([*main, *main[:1]], (1, 2), stored)) == 1
    damaged = broken(main[0], working(main[0], "long_tail", 8))
    assert "long_tail trial rate" in mc.observed([damaged, main[1]], (1, 1), stored)[0]
    # the damaged run fails only as the candidate; the pair still fails, whichever way it is given
    assert "long_tail trial rate" in mc.observed([main[1], damaged], (1, 1), stored)[0]


def test_the_noise_report_gives_each_rate_an_interval_and_says_what_cannot_be_observed(
    stored: dict[str, Any], capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mc, "load_protocol", lambda head=None: stored)
    paths = [f"evidence/metrics/runs/{name}.json" for name in ("main-b1", "main-b2")]
    assert mc.cmd_noise(paths, [(1, 1), (2, 2)], 40) == 0
    out = capsys.readouterr().out
    one, two = out.split("size 2x2")
    # two runs are one same-code pair, however many ways round it is judged
    assert "observed  unchanged code fails 0.000 [0.000, 0.793] of 1 set(s)" in one
    assert "needs 4 runs of one code" in two and "2 more run(s)" in two
    for part in (one, two):
        assert part.count("simulated 29c0518  unchanged code fails 0.") == 1
        assert part.count("smallest seeded regression caught 80% of the time: ") == 1
    assert mc.cmd_noise(paths[:1], [(1, 1)], 40) == 0
    assert "Too few stored runs" in capsys.readouterr().out
    assert mc.cmd_noise(["evidence/metrics/runs/absent.json"], [(1, 1)], 40) == 1


def test_the_wilson_interval_holds_the_rate_and_narrows_with_more_trials() -> None:
    assert mc.wilson(0, 0) == (0.0, 1.0)
    low, high = mc.wilson(0, 4)
    assert low == 0.0 and 0.45 < high < 0.55  # four passing pairs still allow one failure in two
    for hits, n in ((1, 10), (50, 100), (99, 100)):
        low, high = mc.wilson(hits, n)
        assert low < hits / n < high
    assert mc.wilson(5, 100)[1] - mc.wilson(5, 100)[0] < mc.wilson(1, 20)[1] - mc.wilson(1, 20)[0]


def test_the_noise_command_reads_its_sizes(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[Any, ...]] = []
    monkeypatch.setattr(mc, "cmd_noise", lambda *args: seen.append(args) or 0)
    monkeypatch.setattr(sys, "argv", ["metric_compare.py", "noise", "a.json", "b.json"])
    assert mc.main() == 0
    argv = ["metric_compare.py", "noise", "a.json", "--sizes", "1x2,4x4", "--sims", "50"]
    monkeypatch.setattr(sys, "argv", argv)
    assert mc.main() == 0
    assert seen == [
        (["a.json", "b.json"], [(1, 1), (2, 2)], 2000),
        (["a.json"], [(1, 2), (4, 4)], 50),
    ]


# --- findings of the cold review of c531028 -------------------------------------------------


def test_the_same_run_given_twice_is_not_two_runs(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "L", contract_run(protocol, []))
    p1, p2, b1, b2 = (
        write_run(lab["dir"] / f"{name}.json", contract_run(protocol, []))
        for name in ("p1", "p2", "b1", "b2")
    )
    assert mc.verdict(mc.compare([p1, p2], [], {}, [b1, b2])) == "PASS"  # four runs: judged
    copy = str(shutil.copy(p1, lab["dir"] / "copy-of-p1.json"))  # the same bytes, another name
    for cands, main in (
        ([p1, p1], [b1, b2]),  # one candidate run standing in for two
        ([p1, copy], [b1, b2]),
        ([p1, p2], [b1, b1]),  # one main run standing in for two
        ([p1, p2], [b1, p1]),  # a candidate run offered as its own baseline
        ([p1, p1], [p1, p1]),  # one measurement in all four places
    ):
        checks = mc.compare(cands, [], {}, main)
        assert status(checks, "run identity", "B") == "FAIL", (cands, main)
        assert not any(c.ref == "B" and c.kind == "rate" for c in checks)  # nothing was judged
        assert mc.verdict(checks) == "FAIL"
    alone = mc.compare([p1, copy], ["L"], {})  # and against L, with no base at all
    assert status(alone, "run identity", "run") == "FAIL" and mc.verdict(alone) == "FAIL"


def test_base_runs_must_measure_the_main_the_candidate_is_built_on(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    register(lab, "L", contract_run(protocol, []))
    older = {**STAMP, "head": "e" * 40}  # main as it was before a change the candidate contains
    cands = [write_run(lab["dir"] / f"p{n}.json", contract_run(protocol, [])) for n in (1, 2)]
    main = [
        write_run(lab["dir"] / f"b{n}.json", with_contract(run(protocol, stamp=older)))
        for n in (1, 2)
    ]
    asked: list[tuple[str, str]] = []
    monkeypatch.setattr(mc, "_built_on", lambda base, cand: asked.append((base, cand)) or False)
    checks = mc.compare(cands, [], {}, main)
    assert asked == [("e" * 40, "f" * 40)]  # the base runs' head against the candidate's
    assert status(checks, "same-window main", "B") == "FAIL"
    assert not any(c.ref == "B" and c.kind == "rate" for c in checks)
    monkeypatch.setattr(mc, "_built_on", lambda base, cand: True)
    assert status(mc.compare(cands, [], {}, main), "long_tail trial rate", "B") == "PASS"


def test_whether_a_candidate_is_built_on_a_base_is_asked_of_real_git(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mc, "MAIN", "HEAD")  # this checkout is a branch, not main
    head = mc._head()
    assert mc._built_on(head, head)
    assert not mc._built_on("0" * 40, head)  # a base that is not a commit
    assert not mc._built_on(head, "0" * 40)  # a candidate with no merge base
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(mc, "_git_status", lambda *args: seen.append(args) or 1)
    assert not mc._built_on(head, head)  # the product code differs: not the candidate's base
    assert set(mc.MEASURED) <= set(seen[0]) and seen[0][:2] == ("diff", "--quiet")


def test_runs_collected_outside_the_window_are_not_same_window(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "L", contract_run(protocol, []))
    window = protocol["rule"]["window_hours"]

    def judged(*hours: float | None) -> list[mc.Check]:
        files = [
            write_run(lab["dir"] / f"w{n}.json", contract_run(protocol, []), at)
            for n, at in enumerate(hours)
        ]
        return mc.compare(files[:2], [], {}, files[2:])

    assert mc.verdict(judged(0, 1, 2, window)) == "PASS"  # the last starts exactly at the limit
    late = judged(0, 1, 2, window + 0.1)  # a main run from another window
    assert status(late, "same-window main", "B") == "FAIL" and mc.verdict(late) == "FAIL"
    assert status(judged(window + 0.1, 1, 2, 0), "same-window main", "B") == "FAIL"
    undated = write_run(lab["dir"] / "undated.json", contract_run(protocol, []))
    body = json.loads(Path(undated).read_text())
    del body["demo"]["generated_at"]
    Path(undated).write_text(json.dumps(body))
    dated = [write_run(lab["dir"] / f"d{n}.json", contract_run(protocol, [])) for n in range(3)]
    checks = mc.compare(dated[:2], [], {}, [dated[2], undated])
    assert status(checks, "same-window main", "B") == "FAIL"


def test_a_reference_is_registered_only_from_clean_runs_of_the_head_it_names(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    good = write_run(lab["dir"] / "good.json", contract_run(protocol, []))
    more = write_run(lab["dir"] / "more.json", contract_run(protocol, []))
    other = with_contract(run(protocol, stamp={**STAMP, "head": "e" * 40}))
    dirty = with_contract(run(protocol, stamp={**STAMP, "dirty": True}))
    bare = with_contract(run(protocol, stamp={}))
    paths = {
        name: write_run(lab["dir"] / f"{name}.json", made)
        for name, made in (("other", other), ("dirty", dirty), ("bare", bare))
    }
    assert mc.cmd_register("L", [good, more], "e" * 40, "another head") == 1  # not the runs' head
    assert mc.cmd_register("L", [good, paths["other"]], "f" * 40, "two heads") == 1
    assert mc.cmd_register("L", [good, paths["dirty"]], "f" * 40, "uncommitted code") == 1
    assert mc.cmd_register("L", [good, paths["bare"]], "f" * 40, "no stamp") == 1
    assert mc.cmd_register("L", [good, good], "f" * 40, "one run twice") == 1
    assert mc.load_refs() == {}  # nothing was written by any refusal
    assert mc.cmd_register("L", [good, more], "f" * 40, "two clean runs of f") == 0


def test_a_legacy_run_is_registered_without_reading_the_protocol_at_its_head(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_protocol_then(head: str | None = None) -> str:
        if head:  # the file did not exist at a head from before the protocol
            raise mc.subprocess.CalledProcessError(128, "git show")
        return "k1"

    monkeypatch.setattr(mc, "collection_at", no_protocol_then)
    old = write_run(lab["dir"] / "old.json", with_contract(run(protocol, stamp={})))
    assert mc.cmd_register("A1", old, "a" * 40, "from before the protocol", legacy=True) == 0
    entry = mc.load_refs()["A1"]
    assert entry["hashes"]["protocol"] == "legacy" and "collection" not in entry["hashes"]
    cand = write_run(lab["dir"] / "cand.json", contract_run(protocol, []))
    assert status(mc.compare(cand, ["A1"], {}), "long_tail trial rate", "A1") == "PASS"


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_a_tolerance_that_is_not_a_finite_number_excuses_nothing(
    protocol: dict[str, Any], monkeypatch: pytest.MonkeyPatch, bad: float
) -> None:
    ids = families_of(protocol, "long_tail", 40)
    lower = run(protocol, losing("long_tail", ids[:12]))  # 30 points down
    protocol["rule"]["rate_drop_max"] = bad
    assert (
        status(mc.evaluate(lower, run(protocol), "B", protocol), "long_tail trial rate") == "FAIL"
    )
    protocol["rule"]["p95_rise_max_seconds"] = bad  # the tolerance an exception uses
    held = {**BUDGETS, "exception": [exception("p95_latency_seconds", 29.0)]}
    monkeypatch.setattr(mc, "_budgets", lambda: held)
    assert status(mc.absolute(run(protocol, seconds=29.0), protocol), "p95 ceiling") == "FAIL"
    # an exception whose own baseline is not finite: nothing to be "no worse than"
    protocol["rule"]["p95_rise_max_seconds"] = 2.5
    wild = {**BUDGETS, "exception": [exception("p95_latency_seconds", bad)]}
    assert mc.exception_problems(wild)
    monkeypatch.setattr(mc, "_budgets", lambda: wild)
    assert status(mc.absolute(run(protocol, seconds=29.0), protocol), "p95 ceiling") == "FAIL"


def test_the_comparator_honours_a_one_run_waiver_as_the_budget_check_does(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mc, "_budgets", lambda: dict(BUDGETS))
    slow = with_contract(run(protocol, seconds=25.472))
    path = write_run(lab["dir"] / "slow.json", slow, hours=5)
    at = (MIDNIGHT + timedelta(hours=5)).isoformat()
    log = "# --- budget change log ---\n"
    waiver = (
        f"# 2026-11-11  [waiver] p95_latency_seconds {at} 25.472 CC-114 owner waives this run\n"
    )
    monkeypatch.setattr(mc, "_budgets_text", lambda: log)
    assert status(mc.compare(path, ["L"], {}), "p95 ceiling") == "FAIL"  # no waiver on record
    monkeypatch.setattr(mc, "_budgets_text", lambda: log + waiver)
    checks = mc.compare(path, ["L"], {})
    assert status(checks, "p95 ceiling") == "EXCEPTED"
    assert "CC-114" in row(checks, "p95 ceiling").detail
    for wrong in (waiver.replace("25.472", "25.9"), waiver.replace(at, MIDNIGHT.isoformat())):
        monkeypatch.setattr(mc, "_budgets_text", lambda wrong=wrong: log + wrong)
        assert status(mc.compare(path, ["L"], {}), "p95 ceiling") == "FAIL"  # another run or value
    monkeypatch.setattr(mc, "_budgets_text", lambda: log + waiver)
    twin = write_run(lab["dir"] / "twin.json", with_contract(run(protocol, seconds=25.472)))
    assert status(mc.compare([path, twin], ["L"], {}), "p95 ceiling") == "FAIL"  # one run only


# --- findings of the /code-review of 2547155 -------------------------------------------------


def test_a_pool_whose_mean_sits_exactly_on_a_floor_meets_it(
    protocol: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mc, "_budgets", lambda: dict(BUDGETS))

    def scored(key: str, value: float) -> mc.Run:
        scalars = {"retrieval_at_10": 0.95, "selector_at_1": 0.95, "answered_rate": 1.0}
        return run(protocol, scalars={**scalars, key: value})

    assert (0.85 + 0.95) / 2 < 0.9  # what float arithmetic makes of 34/40 and 38/40
    pool = [scored("retrieval_at_10", 0.85), scored("retrieval_at_10", 0.95)]
    assert status(mc.absolute(pool, protocol), "retrieval_at_10 floor") == "PASS"
    thirds = [scored("selector_at_1", 0.7)] * 3  # three runs exactly on the 0.70 floor
    assert status(mc.absolute(thirds, protocol), "selector_at_1 floor") == "PASS"
    under = [scored("retrieval_at_10", 0.85), scored("retrieval_at_10", 0.94)]
    assert status(mc.absolute(under, protocol), "retrieval_at_10 floor") == "FAIL"


def test_promotion_never_lowers_l_on_any_rate_row(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "L", contract_run(protocol, []))
    before = (lab["dir"] / "references.json").read_bytes()
    slower = with_contract(run(protocol, seconds=10.5))  # half a second: far inside the tolerance
    path = write_run(lab["dir"] / "slower.json", slower)
    assert mc.cmd_compare(path, ["L"], {}, record=False) == 0  # it passes against L
    assert mc.cmd_promote(path) == 1  # and still may not become L: the anchor would get slower
    scalars = {"retrieval_at_10": 0.9, "selector_at_1": 0.8, "answered_rate": 1.0}
    made = with_contract(run(protocol, scalars=scalars))
    body_path = write_run(lab["dir"] / "selector.json", made)
    body = json.loads(Path(body_path).read_text())
    body["selector_at_1"] = 0.75  # five points under L's: inside the tolerance too
    Path(body_path).write_text(json.dumps(body))
    assert mc.cmd_compare(body_path, ["L"], {}, record=False) == 0
    assert mc.cmd_promote(body_path) == 1
    assert (lab["dir"] / "references.json").read_bytes() == before
    faster = write_run(lab["dir"] / "faster.json", with_contract(run(protocol, seconds=9.0)))
    assert mc.cmd_promote(faster) == 0  # no row worse than L: it may move
