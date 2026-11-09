"""The comparator turns frozen cohorts and run files into a verdict that a better-looking number
cannot buy: a lost trial, a changed scorer, a smaller denominator or a faster failure all fail."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import metric_compare as mc  # noqa: E402

Failing = set[tuple[str, str, int]]  # (tier, family, repeat) trials that were not answered


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
) -> mc.Run:
    made = trials if trials is not None else _trials(protocol, failing or set(), rows, seconds)
    return mc.Run(
        path="synthetic",
        repeat=3,
        index_hash="index",
        p95_reported=mc.percentile([t["latency_s"] for t in made], 95),
        scalars=scalars or {"retrieval_at_10": 0.9, "selector_at_1": 0.8, "answered_rate": 0.8},
        trials=made,
    )


def families_of(protocol: dict[str, Any], tier_name: str, count: int) -> list[str]:
    return [e["id"] for e in mc.cohort(protocol, tier_name)][:count]


def losing(tier: str, ids: list[str]) -> Failing:
    return {(tier, family, repeat) for family in ids for repeat in (1, 2, 3)}


def status(checks: list[mc.Check], name: str) -> str:
    return next(c.status for c in checks if c.name == name)


def test_a_run_compared_with_itself_has_no_failure(protocol: dict[str, Any]) -> None:
    same = run(protocol, losing("long_tail", families_of(protocol, "long_tail", 10)))
    checks = mc.evaluate(same, same, "A", protocol)
    assert mc.verdict(checks) != "FAIL"
    assert status(checks, "long_tail trial rate") == "PASS"
    assert status(checks, "long_tail case rate") == "PASS"


def test_a_candidate_better_in_one_cohort_and_worse_in_another_is_rejected(
    protocol: dict[str, Any],
) -> None:
    lost = families_of(protocol, "long_tail", 8)
    ref = run(protocol, losing("long_tail", lost))
    candidate = run(protocol, losing("trap", families_of(protocol, "trap", 1)))
    checks = mc.evaluate(candidate, ref, "B", protocol)
    assert status(checks, "long_tail trial rate") == "PASS"
    assert status(checks, "trap trial rate") == "FAIL"
    assert mc.verdict(checks) == "FAIL"


def test_a_gain_inside_the_noise_is_inconclusive_not_a_pass(protocol: dict[str, Any]) -> None:
    ids = families_of(protocol, "long_tail", 40)
    ref = run(protocol, losing("long_tail", ids[:5]))
    candidate = run(protocol, losing("long_tail", [*ids[5:8]]))  # 5 families fixed, 3 broken
    checks = mc.evaluate(candidate, ref, "A", protocol)
    assert status(checks, "long_tail case rate") == "INCONCLUSIVE"


def test_fewer_families_than_the_minimum_is_inconclusive(protocol: dict[str, Any]) -> None:
    same = run(protocol)
    checks = mc.evaluate(same, same, "A", protocol)
    assert (
        status(checks, "core trial rate") == "INCONCLUSIVE"
    )  # four families cannot bound 2 points


def test_extra_repeats_of_one_family_are_not_extra_observations(protocol: dict[str, Any]) -> None:
    base = run(protocol)
    padded = [*base.trials, {**base.trials[0], "repeat": 4}, {**base.trials[0], "repeat": 5}]
    checks = mc.evaluate(run(protocol, trials=padded), base, "A", protocol)
    assert status(checks, "planned trials") == "FAIL"


def test_a_dropped_trial_fails_instead_of_scoring_the_rest(protocol: dict[str, Any]) -> None:
    base = run(protocol)
    candidate = run(protocol, trials=base.trials[1:])
    assert status(mc.evaluate(candidate, base, "A", protocol), "planned trials") == "FAIL"


def test_dropping_the_failed_questions_cannot_lift_the_rate(protocol: dict[str, Any]) -> None:
    ids = families_of(protocol, "long_tail", 6)
    ref = run(protocol, losing("long_tail", ids))
    kept = [t for t in ref.trials if not (t["tier"] == "long_tail" and t["id"] in ids)]
    checks = mc.evaluate(run(protocol, trials=kept), ref, "A", protocol)
    assert mc.verdict(checks) == "FAIL"


def test_faster_failures_are_not_a_speed_gain(protocol: dict[str, Any]) -> None:
    ref = run(protocol, seconds=20.0)
    candidate = run(
        protocol, losing("long_tail", families_of(protocol, "long_tail", 6)), seconds=2.0
    )
    checks = mc.evaluate(candidate, ref, "A", protocol)
    assert status(checks, "long_tail trial rate") == "FAIL"
    assert mc.verdict(checks) == "FAIL"


def test_returning_fewer_rows_for_the_same_questions_fails(protocol: dict[str, Any]) -> None:
    ref = run(protocol, rows=lambda tier, family: 5)
    candidate = run(protocol, rows=lambda tier, family: 1 if family == "q05" else 5)
    assert status(mc.evaluate(candidate, ref, "A", protocol), "rows per family") == "FAIL"


def test_more_empty_answers_than_the_reference_fails(protocol: dict[str, Any]) -> None:
    ref = run(protocol)
    trials = [dict(t) for t in ref.trials]
    for trial in trials:
        if trial["tier"] == "long_tail" and trial["id"] == "q05":
            trial["rows"] = 0  # still marked answered: a refusal that the scorer let through
    checks = mc.evaluate(run(protocol, trials=trials), ref, "A", protocol)
    assert status(checks, "empty answers (long_tail)") == "FAIL"


def test_a_different_index_is_not_comparable(protocol: dict[str, Any]) -> None:
    base = run(protocol)
    other = run(protocol)
    other.index_hash = "another"
    assert status(mc.evaluate(other, base, "A", protocol), "index") == "FAIL"


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


def test_an_edited_expectation_makes_the_owners_review_stale(
    protocol: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = mc.cohort(protocol, "long_tail")[0]
    review = tmp_path / "review.toml"
    stamp = mc.oracle_digest(entry)
    review.write_text(f'[accepted.{entry["id"]}]\nreviewer = "owner"\noracle = "{stamp}"\n')
    monkeypatch.setattr(mc, "REVIEW", review)
    assert entry["id"] in mc.oracle_state(protocol)["long_tail"]["accepted"]
    review.write_text(f'[accepted.{entry["id"]}]\nreviewer = "owner"\noracle = "{stamp}x"\n')
    assert entry["id"] in mc.oracle_state(protocol)["long_tail"]["stale"]


def test_a_review_without_a_reviewer_does_not_count(
    protocol: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = mc.cohort(protocol, "long_tail")[0]
    review = tmp_path / "review.toml"
    review.write_text(f'[accepted.{entry["id"]}]\noracle = "{mc.oracle_digest(entry)}"\n')
    monkeypatch.setattr(mc, "REVIEW", review)
    assert entry["id"] in mc.oracle_state(protocol)["long_tail"]["pending"]


# --- references: A is fixed, L moves only on a pass, a changed scorer needs a bridge ------------


def write_run(path: Path, made: mc.Run) -> str:
    demo = {
        "repeat": 3,
        "index_hash": made.index_hash,
        "p95_latency_seconds": made.p95_reported,
        "answered_rate": made.scalars["answered_rate"],
        "trials": made.trials,
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
    monkeypatch.setattr(mc, "hashes", lambda head=None: dict(now))
    monkeypatch.setattr(
        mc,
        "oracle_state",
        lambda proto: {
            n: {"accepted": ["x"], "pending": [], "stale": []} for n in proto["cohorts"]
        },
    )
    monkeypatch.setattr(mc, "_head", lambda: "f" * 40)
    protocol["sampling"]["min_families"] = 4  # every cohort is judged, so a pass is reachable
    return {"dir": tmp_path, "now": now}


def register(lab: dict[str, Any], name: str, made: mc.Run, scorer: str = "s1") -> None:
    path = write_run(lab["dir"] / f"{name}.json", made)
    refs = mc.load_refs()
    import hashlib

    refs[name] = {
        "label": "test",
        "head": "a" * 40,
        "run": path,
        "run_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(),
        "hashes": {"scorer": scorer, "cohorts": {"c": "h"}, "protocol": "p1"},
    }
    (lab["dir"] / "references.json").write_text(json.dumps(refs))


def test_a_scorer_change_is_not_a_code_gain_without_a_bridge(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    old = run(protocol, losing("long_tail", families_of(protocol, "long_tail", 12)))
    register(lab, "A", old, scorer="s0")  # scored by an older scorer
    better = write_run(lab["dir"] / "cand.json", run(protocol))
    checks = mc.compare(better, ["A"], {})
    assert status(checks, "scorer / cohort hashes") == "FAIL"


def test_a_bridge_compares_against_the_reference_rescored_by_the_new_scorer(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    ids = families_of(protocol, "long_tail", 12)
    register(lab, "A", run(protocol, losing("long_tail", ids)), scorer="s0")
    rescored = write_run(lab["dir"] / "rescored.json", run(protocol, losing("long_tail", ids[:6])))
    bridge = {
        "ref": "A",
        "from_scorer": "s0",
        "to_scorer": "s1",
        "from_cohorts": {"c": "h"},
        "to_cohorts": {"c": "h"},
        "rescored_run": rescored,
        "note": "same trials, new scorer",
    }
    (lab["dir"] / "bridges.json").write_text(json.dumps([bridge]))
    same_as_rescored = write_run(
        lab["dir"] / "cand.json", run(protocol, losing("long_tail", ids[:6]))
    )
    checks = mc.compare(same_as_rescored, ["A"], {})
    assert status(checks, "long_tail trial rate") == "PASS"  # no credit for the 6 the scorer freed
    assert "bridged" in next(c.detail for c in checks if c.name == "reference label")


def test_a_registered_reference_cannot_be_replaced(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "A", run(protocol))
    path = write_run(lab["dir"] / "other.json", run(protocol))
    assert mc.cmd_register("A", path, "b" * 40, "again") == 1


def test_a_reference_file_edited_after_registration_fails(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "A", run(protocol))
    Path(mc.load_refs()["A"]["run"]).write_text("{}")
    cand = write_run(lab["dir"] / "cand.json", run(protocol))
    assert status(mc.compare(cand, ["A"], {}), "reference file") == "FAIL"


def test_a_run_of_small_losses_never_moves_l_or_resets_a(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "A", run(protocol))
    register(lab, "L", run(protocol))
    refs_before = (lab["dir"] / "references.json").read_text()
    ids = families_of(protocol, "long_tail", 3)
    for lost in (ids[:1], ids[:2], ids[:3]):  # each step is a little worse than the last
        step = write_run(lab["dir"] / "step.json", run(protocol, losing("long_tail", lost)))
        assert mc.cmd_promote(step) == 1
    assert (lab["dir"] / "references.json").read_text() == refs_before


def test_a_candidate_that_passes_against_a_and_l_becomes_the_new_l(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    complete = run(protocol)
    for trial in complete.trials:
        trial.update(dict.fromkeys(mc.CONTRACT_KEYS, True))  # the contract is measured and met
    register(lab, "A", complete)
    better = write_run(lab["dir"] / "better.json", complete)
    assert mc.cmd_promote(better) == 0
    assert mc.load_refs()["L"]["head"] == "f" * 40
    assert mc.load_refs()["A"]["head"] == "a" * 40


# --- absolute checks ------------------------------------------------------------------------------


def test_a_p95_that_disagrees_with_its_trials_fails(protocol: dict[str, Any]) -> None:
    made = run(protocol, seconds=30.0)
    made.p95_reported = 5.0
    assert status(mc.absolute(made, protocol), "p95 matches trials") == "FAIL"


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


def test_missing_the_target_fails_whatever_the_gain(protocol: dict[str, Any]) -> None:
    ids = families_of(protocol, "long_tail", 40)
    base = run(protocol, losing("long_tail", ids[:20]))
    candidate = run(protocol, losing("long_tail", ids[:8]))
    assert (
        status(mc.target_check(candidate, base, protocol, "long_tail", 0.95), "long_tail case")
        == "FAIL"
    )
