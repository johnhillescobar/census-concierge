"""E2E latency chart: histogram bins and SVG markers from demo.trials."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import plot_e2e_latency as plot  # noqa: E402


def _payload(latencies: list[float], *, p95: float, answered: float) -> dict[str, Any]:
    return {
        "demo": {
            "repeat": 3,
            "n": len(latencies),
            "answered_rate": answered,
            "p95_latency_seconds": p95,
            "trials": [{"id": f"q{i:02d}", "latency_s": x} for i, x in enumerate(latencies)],
        }
    }


def test_bin_counts_split_on_bin_width() -> None:
    assert plot.bin_counts([0.5, 1.5, 1.9], bin_w=1.0, xmax=3) == [1, 2, 0]


def test_percentile_matches_run_demo_rank_rule() -> None:
    xs = [10.0, 11.0, 12.0, 20.0]
    assert plot.percentile(xs, 50) == 11.0
    assert plot.percentile(xs, 95) == 20.0


def test_svg_marks_both_p95_and_the_budget_ceiling(tmp_path: Path) -> None:
    pre = plot.series_from_latest(_payload([5.0] * 9 + [19.0], p95=19.0, answered=0.842), "pre")
    post = plot.series_from_latest(_payload([6.0] * 9 + [22.0], p95=22.0, answered=0.808), "post")
    svg = plot.render_svg(pre, post, ceiling=20.0, title="E2E latency — pre vs post merge")
    out = tmp_path / "chart.svg"
    out.write_text(svg, encoding="utf-8")
    text = out.read_text(encoding="utf-8")
    assert "pre p95 19.000s  answered 0.842" in text
    assert "post p95 22.000s  answered 0.808" in text
    assert "ceiling 20s" in text
    assert "pre p95 19.00s" in text
    assert "post p95 22.00s" in text


def test_load_latest_from_file(tmp_path: Path) -> None:
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(_payload([8.0, 9.0], p95=9.0, answered=1.0)), encoding="utf-8")
    series = plot.series_from_latest(plot.load_latest(str(path)), "file")
    assert series.n == 2
    assert series.latencies == [8.0, 9.0]


def test_svg_escapes_title_and_labels() -> None:
    pre = plot.series_from_latest(_payload([5.0], p95=5.0, answered=1.0), "pre & <a>")
    post = plot.series_from_latest(_payload([6.0], p95=6.0, answered=1.0), 'post "b"')
    svg = plot.render_svg(pre, post, ceiling=20.0, title="<script>alert(1)</script>")
    assert "<script>" not in svg
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in svg
    assert "pre &amp; &lt;a&gt;" in svg
    assert "post &quot;b&quot;" in svg


def test_ecdf_is_a_step_function() -> None:
    assert plot.ecdf_steps([5.0, 10.0], xmin=0.0, xmax=20.0) == [
        (0.0, 0.0),
        (5.0, 0.0),
        (5.0, 0.5),
        (10.0, 0.5),
        (10.0, 1.0),
        (20.0, 1.0),
    ]


def test_resolve_out_stays_inside_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    out = plot.resolve_out(Path("charts/a.svg"), root=root)
    assert out == (root / "charts" / "a.svg").resolve()


def test_resolve_out_rejects_outside_root(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    with pytest.raises(SystemExit, match="outside the repo"):
        plot.resolve_out(tmp_path / "nope.svg", root=root)
