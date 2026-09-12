"""Committed sweep results must say which corpus they were scored on.

A result file with no corpus_hash can be ranked beside one scored on a
different table list, and nothing warns. Missing and mixed hashes are fatal;
a live corpus that does not match the recorded one is a warning — the
published Axes A–C numbers describe the pre-fold 756-document corpus.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# experiments/ is throwaway and not an installed package; pytest's path is api/.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.harness import RESULTS, result_corpus_status  # noqa: E402

PRE_FOLD = {"corpus_n": 756, "corpus_hash": "abc111"}
POST_FOLD = {"corpus_n": 636, "corpus_hash": "def222"}
LIVE_POST_FOLD = {"corpus_n": 636, "corpus_hash": "def222"}


def test_a_result_without_a_corpus_hash_is_fatal() -> None:
    fatal, warnings = result_corpus_status([{"arm": "gemini-001"}], live=LIVE_POST_FOLD)
    assert fatal
    assert "gemini-001" in fatal[0]
    assert not warnings


def test_comparable_results_on_two_corpora_are_fatal() -> None:
    fatal, _warnings = result_corpus_status(
        [
            {"arm": "gemini-001", **PRE_FOLD},
            {"arm": "voyage-4-large", **POST_FOLD},
        ],
        live=LIVE_POST_FOLD,
    )
    assert any("mixed" in line for line in fatal)


def test_a_live_corpus_mismatch_is_a_warning_not_fatal() -> None:
    fatal, warnings = result_corpus_status(
        [{"arm": "gemini-001", **PRE_FOLD}],
        live=LIVE_POST_FOLD,
    )
    assert not fatal
    assert warnings
    assert PRE_FOLD["corpus_hash"] in warnings[0]
    assert LIVE_POST_FOLD["corpus_hash"] in warnings[0]


def test_matching_live_corpus_is_silent() -> None:
    fatal, warnings = result_corpus_status(
        [{"arm": "gemini-001", **POST_FOLD}],
        live=LIVE_POST_FOLD,
    )
    assert not fatal
    assert not warnings


def _load_results() -> list[tuple[Path, dict]]:
    out = []
    for path in sorted(RESULTS.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "error" not in payload:
            out.append((path, payload))
    return out


def test_every_committed_result_records_the_corpus_it_was_scored_on() -> None:
    files = _load_results()
    assert files, "experiments/results/ has no committed JSON"
    for path, payload in files:
        assert payload.get("corpus_n") in (636, 756), path.name
        assert payload.get("corpus_hash"), path.name


def test_full_arms_share_the_pre_fold_corpus_and_the_screening_run_does_not() -> None:
    files = _load_results()
    full = [p for path, p in files if "sampled" not in path.name]
    sampled = [p for path, p in files if "sampled" in path.name]
    hashes = {p["corpus_hash"] for p in full}
    assert len(hashes) == 1
    assert full[0]["corpus_n"] == 756
    assert sampled
    assert {p["corpus_n"] for p in sampled} == {636}
    assert sampled[0]["corpus_hash"] not in hashes
