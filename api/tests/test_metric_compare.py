"""The comparator turns frozen cohorts and run files into a verdict that a better-looking number
cannot buy: a lost trial, a changed scorer, a smaller denominator or a faster failure all fail."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import check_invariants as ci  # noqa: E402
import metric_compare as mc  # noqa: E402

Failing = set[tuple[str, str, int]]  # (tier, family, repeat) trials that were not answered
STAMP = {"head": "f" * 40, "scorer": "s1", "cohorts": {"c": "h"}, "protocol": "p1"}


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
    monkeypatch.setattr(mc, "hashes", lambda head=None: dict(now))
    monkeypatch.setattr(mc, "protocol_hash", lambda head=None: "p1")
    monkeypatch.setattr(
        mc,
        "oracle_state",
        lambda proto: {
            n: {"accepted": ["x"], "pending": [], "stale": []} for n in proto["cohorts"]
        },
    )
    monkeypatch.setattr(mc, "_head", lambda: "f" * 40)
    monkeypatch.setattr(mc, "_same_code", lambda head: True)  # a real git diff is tested apart
    monkeypatch.setattr(mc, "_reachable", lambda commit, tip: True)
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
        "rescored_sha256": hashlib.sha256(Path(rescored).read_bytes()).hexdigest(),
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


# --- findings of the cold review ---------------------------------------------------------------


def test_a_bridge_whose_rescored_run_is_not_pinned_is_refused(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    ids = families_of(protocol, "long_tail", 12)
    register(lab, "A", run(protocol, losing("long_tail", ids)), scorer="s0")
    rescored = write_run(lab["dir"] / "rescored.json", run(protocol))
    bridge = {
        "ref": "A", "from_scorer": "s0", "to_scorer": "s1", "from_cohorts": {"c": "h"},
        "to_cohorts": {"c": "h"}, "rescored_run": rescored, "rescored_sha256": "0" * 64,
        "note": "tampered",
    }  # fmt: skip
    (lab["dir"] / "bridges.json").write_text(json.dumps([bridge]))
    cand = write_run(lab["dir"] / "cand.json", run(protocol))
    assert status(mc.compare(cand, ["A"], {}), "bridge") == "FAIL"


def test_runs_with_no_index_hash_are_not_comparable(protocol: dict[str, Any]) -> None:
    base = run(protocol)
    base.index_hash = ""
    other = run(protocol)
    other.index_hash = ""
    assert status(mc.evaluate(other, base, "A", protocol), "index") == "FAIL"


def test_a_reported_answered_rate_that_the_trials_do_not_support_fails(
    protocol: dict[str, Any],
) -> None:
    made = run(protocol, losing("long_tail", families_of(protocol, "long_tail", 10)))
    made.scalars["answered_rate"] = 0.99
    assert status(mc.absolute(made, protocol), "answered_rate matches trials") == "FAIL"


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


def test_promotion_writes_the_new_l_in_one_step_and_keeps_the_ledger_append_only(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    complete = run(protocol)
    for trial in complete.trials:
        trial.update(dict.fromkeys(mc.CONTRACT_KEYS, True))
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


# --- gaps found by the mutation check ------------------------------------------------------------


def contract_run(protocol: dict[str, Any], lost: list[str]) -> mc.Run:
    made = run(protocol, losing("long_tail", lost))
    for trial in made.trials:
        trial.update(dict.fromkeys(mc.CONTRACT_KEYS, True))
    return made


def test_a_bridge_judges_against_the_rescored_run_not_the_original(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    ids = families_of(protocol, "long_tail", 12)
    register(lab, "A", run(protocol, losing("long_tail", ids)), scorer="s0")  # 12 failing
    rescored = write_run(lab["dir"] / "rescored.json", run(protocol, losing("long_tail", ids[:6])))
    bridge = {
        "ref": "A",
        "from_scorer": "s0",
        "to_scorer": "s1",
        "from_cohorts": {"c": "h"},
        "to_cohorts": {"c": "h"},
        "rescored_run": rescored,
        "rescored_sha256": hashlib.sha256(Path(rescored).read_bytes()).hexdigest(),
        "note": "same trials, new scorer",
    }
    (lab["dir"] / "bridges.json").write_text(json.dumps([bridge]))
    # better than the original (9 failing against 12) but worse than the rescored run (6)
    cand = write_run(lab["dir"] / "cand.json", run(protocol, losing("long_tail", ids[:9])))
    assert status(mc.compare(cand, ["A"], {}), "long_tail trial rate") == "FAIL"


def test_a_candidate_that_passes_a_but_loses_to_l_does_not_become_l(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    ids = families_of(protocol, "long_tail", 6)
    register(lab, "A", contract_run(protocol, ids))
    register(lab, "L", contract_run(protocol, []))
    before = (lab["dir"] / "references.json").read_bytes()
    cand = write_run(lab["dir"] / "cand.json", contract_run(protocol, ids[:3]))
    assert mc.cmd_promote(cand) == 1
    assert (lab["dir"] / "references.json").read_bytes() == before


def test_a_case_passes_only_if_every_repeat_answered(protocol: dict[str, Any]) -> None:
    ids = families_of(protocol, "long_tail", 40)
    partial = {("long_tail", ids[0], 3)}  # one repeat of three
    tier = protocol["cohorts"]["long_tail"]["tier"]
    grouped = mc.families(run(protocol, partial), ids, tier, 3)
    rates = mc.family_rates(grouped)[ids[0]]
    assert rates["case"] == 0.0
    assert round(rates["trial"], 3) == 0.667


def test_a_family_outside_the_frozen_cohort_is_a_plan_error(protocol: dict[str, Any]) -> None:
    made = run(protocol)
    template = next(t for t in made.trials if t["tier"] == "long_tail")
    extra = [{**template, "id": "zz99", "repeat": n} for n in (1, 2, 3)]  # a complete family
    ids = [e["id"] for e in mc.cohort(protocol, "long_tail")]
    with pytest.raises(mc.PlanError):
        mc.families(run(protocol, trials=[*made.trials, *extra]), ids, "long_tail", 3)


def test_promotion_is_a_single_write_of_the_references(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    complete = contract_run(protocol, [])
    register(lab, "A", complete)
    writes: list[set[str]] = []
    original = mc.write_refs
    monkeypatch.setattr(mc, "write_refs", lambda refs: (writes.append(set(refs)), original(refs)))
    assert mc.cmd_promote(write_run(lab["dir"] / "next.json", complete)) == 0
    assert writes == [{"A", "L"}]  # never a state with no L


def test_only_an_explicit_legacy_flag_skips_the_protocol_hash_check(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    complete = contract_run(protocol, [])
    path = write_run(lab["dir"] / "ref.json", complete)
    assert mc.cmd_register("S", path, "a" * 40, "strict", legacy=False) == 0
    assert mc.cmd_register("O", path, "a" * 40, "legacy-unfrozen-protocol", legacy=True) == 0
    # the flag decides, never the wording of the label
    assert mc.cmd_register("S2", path, "a" * 40, "legacy-looking label", legacy=False) == 0
    assert mc.cmd_register("O2", path, "a" * 40, "plain label", legacy=True) == 0
    refs = mc.load_refs()
    assert refs["S"]["hashes"]["protocol"] == "p1"
    assert refs["S2"]["hashes"]["protocol"] == "p1"
    assert refs["O"]["hashes"]["protocol"] == "legacy"
    assert refs["O2"]["hashes"]["protocol"] == "legacy"
    lab["now"]["protocol"] = "p2"  # the frozen protocol changed after both were registered
    later = with_contract(run(protocol, stamp={**STAMP, "protocol": "p2"}))  # collected under p2
    cand = write_run(lab["dir"] / "cand.json", later)
    assert status(mc.compare(cand, ["S"], {}), "protocol hash") == "FAIL"
    assert not any(c.name == "protocol hash" for c in mc.compare(cand, ["O"], {}))


def test_the_register_command_passes_legacy_through_and_requires_a_label(
    lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[bool] = []
    monkeypatch.setattr(mc, "cmd_register", lambda *a, legacy=False: seen.append(legacy) or 0)
    argv = ["metric_compare.py", "register", "A", "r.json", "--head", "a" * 40, "--label", "x"]
    monkeypatch.setattr(sys, "argv", argv)
    assert mc.main() == 0
    monkeypatch.setattr(sys, "argv", [*argv, "--legacy"])
    assert mc.main() == 0
    assert seen == [False, True]
    monkeypatch.setattr(sys, "argv", argv[:-2])
    with pytest.raises(SystemExit):
        mc.main()


def test_what_promote_writes_satisfies_the_records_guard_and_a_hand_edit_does_not(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    complete = contract_run(protocol, [])
    register(lab, "A", complete)
    register(lab, "L", complete)
    refs_file, ledger_file = lab["dir"] / "references.json", lab["dir"] / "ledger.jsonl"
    before = refs_file.read_text()
    # promoted on one commit (f...) from a run produced on another (e...): the usual case
    produced = with_contract(run(protocol, stamp=stamped("e" * 40, "s1")))
    assert mc.cmd_promote(write_run(lab["dir"] / "next.json", produced)) == 0
    assert mc.load_refs()["L"]["head"] == "e" * 40
    after, ledger = refs_file.read_text(), ledger_file.read_text()

    repo = lab["dir"] / "repo"
    metrics = repo / "evidence" / "metrics"
    metrics.mkdir(parents=True)
    (metrics / "references.json").write_text(after)
    (metrics / "ledger.jsonl").write_text(ledger)
    base = {"evidence/metrics/references.json": before, "evidence/metrics/ledger.jsonl": ""}
    monkeypatch.setattr(ci, "ROOT", repo)
    monkeypatch.setattr(ci, "_text_at", lambda ref, rel: base.get(rel))
    assert ci.check_metric_records_not_rewritten("origin/main") == []
    (metrics / "ledger.jsonl").write_text("")  # the same reference file with the proof removed
    assert ci.check_metric_records_not_rewritten("origin/main")


# --- findings of the third cold review --------------------------------------------------------


def test_judging_no_families_is_inconclusive_not_a_crash(protocol: dict[str, Any]) -> None:
    assert mc.judge([], protocol)[0] == "INCONCLUSIVE"


@pytest.mark.parametrize(
    "text", ["", "not json", "[]", '{"demo": {}}', '{"demo": {"repeat": "x"}}', '{"demo": null}']
)
def test_an_unusable_run_file_is_a_fail_row_not_a_bare_exception(
    protocol: dict[str, Any], lab: dict[str, Any], text: str
) -> None:
    bad = lab["dir"] / "bad.json"
    bad.write_text(text)
    assert status(mc.compare(str(bad), ["A"], {}), "candidate run file") == "FAIL"
    register(lab, "A", run(protocol))
    good = write_run(lab["dir"] / "good.json", run(protocol))
    refs = mc.load_refs()
    Path(refs["A"]["run"]).write_text(text)  # a reference whose file went bad...
    refs["A"]["run_sha256"] = hashlib.sha256(Path(refs["A"]["run"]).read_bytes()).hexdigest()
    (lab["dir"] / "references.json").write_text(json.dumps(refs))  # ...with its hash re-pinned
    checks = mc.compare(good, ["A"], {})
    assert status(checks, "reference run file") == "FAIL"


def test_a_regression_metric_the_reference_does_not_report_is_unknown_not_skipped(
    protocol: dict[str, Any],
) -> None:
    cand, ref = run(protocol), run(protocol)
    del ref.scalars["retrieval_at_10"]
    assert status(mc.evaluate(cand, ref, "A", protocol), "retrieval_at_10") == "UNKNOWN"


def test_compare_without_a_reference_is_refused_and_writes_no_record(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    path = write_run(lab["dir"] / "cand.json", contract_run(protocol, []))
    assert mc.cmd_compare(path, [], {}, record=True) == 2
    assert not (lab["dir"] / "ledger.jsonl").exists()


def test_the_ledger_row_names_the_run_file_by_hash(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    complete = contract_run(protocol, [])
    register(lab, "A", complete)
    path = write_run(lab["dir"] / "cand.json", complete)
    mc.cmd_compare(path, ["A"], {}, record=True)
    row = json.loads((lab["dir"] / "ledger.jsonl").read_text().splitlines()[-1])
    assert row["run_sha256"] == hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_an_interrupted_write_of_the_references_leaves_the_old_file_whole(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    register(lab, "A", run(protocol))
    before = (lab["dir"] / "references.json").read_bytes()

    def interrupted(src: object, dst: object) -> None:
        raise OSError("disk went away")

    monkeypatch.setattr(mc.os, "replace", interrupted)
    with pytest.raises(OSError):
        mc.write_refs({"A": {"head": "changed"}})
    assert (lab["dir"] / "references.json").read_bytes() == before


# --- findings of the Copilot review of the draft PR ---------------------------------------


def with_contract(made: mc.Run) -> mc.Run:
    for trial in made.trials:
        trial.update(dict.fromkeys(mc.CONTRACT_KEYS, True))
    return made


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
    register(lab, "A", with_contract(run(protocol)))
    checks = mc.compare(path, ["A"], {})
    assert status(checks, "candidate run file") == "FAIL"  # ...unless the plan is enforced
    assert not any(c.name == "p95 ceiling" for c in checks)


def test_a_reference_padded_with_extra_trials_is_not_comparable(protocol: dict[str, Any]) -> None:
    base = with_contract(run(protocol))
    padded = run(protocol, trials=[*base.trials, *fast_extras(base)])
    checks = mc.evaluate(base, padded, "A", protocol)
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
    register(
        lab, "A", with_contract(run(protocol))
    )  # A was scored by s1, the scorer now checked out
    stale = with_contract(run(protocol, stamp=stamped(old, "s0")))  # the candidate by s0
    checks = mc.compare(write_run(lab["dir"] / "stale.json", stale), ["A"], {})
    assert status(checks, "scorer / cohort hashes") == "FAIL"  # the checkout's s1 must not hide it


def test_hashes_a_run_records_must_be_those_of_its_head(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "A", with_contract(run(protocol)))
    lying = with_contract(run(protocol, stamp=stamped("e" * 40, "s9")))  # the checkout says s1
    checks = mc.compare(write_run(lab["dir"] / "lying.json", lying), ["A"], {})
    assert status(checks, "provenance") == "FAIL"


def test_a_head_that_cannot_be_checked_is_a_failure_not_a_crash(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def unknown_head(head: str | None = None) -> dict[str, Any]:
        if head:
            raise mc.subprocess.CalledProcessError(128, "git show")
        return dict(lab["now"])

    monkeypatch.setattr(mc, "hashes", unknown_head)
    register(lab, "A", with_contract(run(protocol)))
    cand = write_run(lab["dir"] / "cand.json", with_contract(run(protocol)))
    assert status(mc.compare(cand, ["A"], {}), "provenance") == "FAIL"


def test_a_run_collected_under_another_protocol_is_refused(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "A", with_contract(run(protocol)))
    other = with_contract(run(protocol, stamp={**STAMP, "protocol": "p0"}))
    checks = mc.compare(write_run(lab["dir"] / "other.json", other), ["A"], {})
    assert status(checks, "provenance") == "FAIL"


def test_a_run_with_no_provenance_is_unknown_and_can_never_be_promoted(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    register(lab, "A", with_contract(run(protocol)))
    legacy = write_run(lab["dir"] / "legacy.json", with_contract(run(protocol, stamp={})))
    assert status(mc.compare(legacy, ["A"], {}), "provenance") == "UNKNOWN"
    before = (lab["dir"] / "references.json").read_bytes()
    assert mc.cmd_promote(legacy) == 1
    assert (lab["dir"] / "references.json").read_bytes() == before


def test_a_partial_provenance_record_counts_as_none(
    protocol: dict[str, Any], lab: dict[str, Any]
) -> None:
    path = write_run(lab["dir"] / "partial.json", with_contract(run(protocol)))
    body = json.loads(Path(path).read_text())
    del body["demo"]["provenance"]["scorer"]
    Path(path).write_text(json.dumps(body))
    assert mc.load_run(path).hashes == {}


def test_promotion_labels_the_run_with_the_head_that_produced_it(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    producing = "e" * 40
    monkeypatch.setattr(
        mc, "hashes", lambda head=None: {"scorer": "s1", "cohorts": {"c": "h"}, "protocol": "p1"}
    )
    register(lab, "A", with_contract(run(protocol)))
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
    register(lab, "A", with_contract(run(protocol)))
    cand = write_run(lab["dir"] / "cand.json", with_contract(run(protocol)))
    assert not any(c.name == "provenance" for c in mc.compare(cand, ["A"], {}))
    monkeypatch.setattr(mc, "_same_code", lambda head: False)
    assert status(mc.compare(cand, ["A"], {}), "provenance") == "FAIL"


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
    register(lab, "A", with_contract(run(protocol)))
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
    register(lab, "A", with_contract(run(protocol)))
    wrong = with_contract(run(protocol, stamp={**STAMP, "cohorts": {"c": "other"}}))
    checks = mc.compare(write_run(lab["dir"] / "wrong.json", wrong), ["A"], {})
    assert status(checks, "provenance") == "FAIL"


def test_a_head_whose_goldens_are_unreadable_is_a_failure_not_a_traceback(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(head: str | None = None) -> dict[str, Any]:
        if head:
            raise KeyError("question")
        return dict(lab["now"])

    monkeypatch.setattr(mc, "hashes", broken)
    register(lab, "A", with_contract(run(protocol)))
    cand = write_run(lab["dir"] / "cand.json", with_contract(run(protocol)))
    assert status(mc.compare(cand, ["A"], {}), "provenance") == "FAIL"


def test_oracle_rows_do_not_describe_a_run_scored_under_other_cohorts(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    old = "e" * 40
    heads = {old: {"scorer": "s0", "cohorts": {"c": "h"}, "protocol": "p1"}}
    monkeypatch.setattr(mc, "hashes", lambda head=None: dict(heads.get(head, lab["now"])))
    register(lab, "A", with_contract(run(protocol)), scorer="s0")
    stale = with_contract(run(protocol, stamp=stamped(old, "s0")))
    checks = mc.compare(write_run(lab["dir"] / "stale.json", stale), ["A"], {})
    assert status(checks, "applies") == "UNKNOWN"
    fresh = write_run(lab["dir"] / "fresh.json", with_contract(run(protocol)))
    assert "applies" not in [c.name for c in mc.compare(fresh, ["A"], {})]


def test_a_bridge_is_looked_up_by_the_scorer_that_scored_the_candidate(
    protocol: dict[str, Any], lab: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    scored_by = "e" * 40
    heads = {scored_by: {"scorer": "s2", "cohorts": {"c": "h"}, "protocol": "p1"}}
    monkeypatch.setattr(mc, "hashes", lambda head=None: dict(heads.get(head, lab["now"])))
    ids = families_of(protocol, "long_tail", 6)
    register(lab, "A", with_contract(run(protocol, losing("long_tail", ids))), scorer="s0")
    rescored = write_run(lab["dir"] / "rescored.json", with_contract(run(protocol)))
    bridge = {
        "ref": "A",
        "from_scorer": "s0",
        "to_scorer": "s2",  # the candidate's scorer; the checkout has s1
        "from_cohorts": {"c": "h"},
        "to_cohorts": {"c": "h"},
        "rescored_run": rescored,
        "rescored_sha256": hashlib.sha256(Path(rescored).read_bytes()).hexdigest(),
        "note": "same trials, s2",
    }
    (lab["dir"] / "bridges.json").write_text(json.dumps([bridge]))
    cand = with_contract(run(protocol, stamp=stamped(scored_by, "s2")))
    checks = mc.compare(write_run(lab["dir"] / "cand.json", cand), ["A"], {})
    assert "bridged" in next(c.detail for c in checks if c.name == "reference label")


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
    assert status(mc.compare(cand, ["A"], {}), "candidate run file") == "FAIL"
