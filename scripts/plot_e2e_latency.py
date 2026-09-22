#!/usr/bin/env python3
"""Compare pre vs post `make demo` latency distributions.

Reads `demo.trials[].latency_s` from two `evidence/latest.json` snapshots
(git refs or files). Does not Read E2E transcripts. Writes an SVG histogram
plus ECDF so a p95 ceiling miss is visible as tail, not as a slower median.

    uv run python scripts/plot_e2e_latency.py --pre 36e2248 --post origin/main
    uv run python scripts/plot_e2e_latency.py --pre 36e2248 --post origin/main \\
        --out .claude/cc-98-e2e-latency-distribution.svg
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON = "evidence/latest.json"
DEFAULT_OUT = ROOT / ".claude" / "e2e-latency-distribution.svg"


@dataclass(frozen=True)
class Series:
    label: str
    latencies: list[float]
    p95: float
    answered_rate: float
    n: int


def percentile(values: list[float], p: float) -> float:
    """Same rank rule as `scripts/run_demo.py`."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = math.ceil(p / 100 * len(ordered)) - 1
    return ordered[max(0, min(rank, len(ordered) - 1))]


def bin_counts(xs: list[float], *, bin_w: float, xmax: float) -> list[int]:
    n_bins = max(1, int(math.ceil(xmax / bin_w)))
    counts = [0] * n_bins
    for x in xs:
        i = min(int(x // bin_w), n_bins - 1)
        counts[i] += 1
    return counts


def p95_ceiling() -> float:
    path = ROOT / "budgets.toml"
    with path.open("rb") as handle:
        budgets = tomllib.load(handle)
    return float(budgets["performance"]["p95_latency_seconds"])


def _git_show(ref: str, rel: str) -> str:
    hit = subprocess.run(
        ["git", "show", f"{ref}:{rel}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if hit.returncode != 0:
        print(hit.stderr.strip() or f"git show {ref}:{rel} failed", file=sys.stderr)
        sys.exit(hit.returncode or 1)
    return hit.stdout


def load_latest(spec: str) -> dict[str, Any]:
    """Load a latest.json. `spec` is a file path or a git ref."""
    as_path = Path(spec)
    if not as_path.is_absolute():
        as_path = ROOT / spec
    if as_path.is_file():
        return json.loads(as_path.read_text(encoding="utf-8"))
    return json.loads(_git_show(spec, DEFAULT_JSON))


def series_from_latest(payload: dict[str, Any], label: str) -> Series:
    demo = payload.get("demo")
    if not isinstance(demo, dict):
        raise SystemExit(f"{label}: latest.json has no demo object")
    trials = demo.get("trials")
    if not isinstance(trials, list) or not trials:
        raise SystemExit(f"{label}: demo.trials is empty — not the transcript")
    xs = [float(trial["latency_s"]) for trial in trials]
    xs.sort()
    p95 = float(demo.get("p95_latency_seconds", percentile(xs, 95)))
    answered = float(demo.get("answered_rate", 0.0))
    return Series(label=label, latencies=xs, p95=p95, answered_rate=answered, n=len(xs))


def summarize(series: Series) -> str:
    xs = series.latencies
    mean = sum(xs) / len(xs)
    return (
        f"{series.label:<6} n={series.n}  median={percentile(xs, 50):.3f}  "
        f"mean={mean:.3f}  p95={series.p95:.3f}  max={xs[-1]:.3f}  "
        f"answered={series.answered_rate:.3f}"
    )


def render_svg(
    pre: Series,
    post: Series,
    *,
    ceiling: float,
    title: str,
) -> str:
    width, height = 960, 820
    ml, mr, mt, mb = 70, 28, 78, 56
    gap = 46
    plot_w = width - ml - mr
    plot_h = (height - mt - mb - gap) / 2
    top_y0 = mt
    bot_y0 = mt + plot_h + gap
    bin_w = 1.0
    xmax = max(25.0, math.ceil(max(pre.latencies[-1], post.latencies[-1], ceiling) / 5) * 5)
    xmin = 0.0
    pre_c = bin_counts(pre.latencies, bin_w=bin_w, xmax=xmax)
    post_c = bin_counts(post.latencies, bin_w=bin_w, xmax=xmax)
    ymax = max(max(pre_c), max(post_c), 1)
    ymax = math.ceil(ymax / 5) * 5 + 5

    def xmap(x: float) -> float:
        return ml + (x - xmin) / (xmax - xmin) * plot_w

    def ymap_top(count: float) -> float:
        return top_y0 + plot_h - (count / ymax) * plot_h

    def ymap_bot(frac: float) -> float:
        return bot_y0 + plot_h - frac * plot_h

    pre_color, post_color, ceil_color = "#1f6feb", "#cf222e", "#57606a"
    ink, muted, grid = "#1f2328", "#656d76", "#d0d7de"
    font = "Segoe UI, Helvetica, Arial, sans-serif"
    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{title}">',
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>',
        f'<text x="{ml}" y="28" font-family="{font}" font-size="20" '
        f'font-weight="600" fill="{ink}">{title}</text>',
        f'<text x="{ml}" y="50" font-family="{font}" font-size="12" fill="{muted}">'
        f"make demo latencies, n={pre.n} vs {post.n}. Seconds to return an answer "
        f"(all trials). Ceiling {ceiling:g}s is the budget, not a histogram bin.</text>",
    ]
    lx = ml + 430
    parts += [
        f'<rect x="{lx}" y="16" width="12" height="12" fill="{pre_color}" '
        f'fill-opacity="0.75" stroke="{pre_color}"/>',
        f'<text x="{lx + 18}" y="26" font-family="{font}" font-size="12" fill="{ink}">'
        f"{pre.label}  p95 {pre.p95:.3f}s  answered {pre.answered_rate:.3f}</text>",
        f'<rect x="{lx}" y="34" width="12" height="12" fill="{post_color}" '
        f'fill-opacity="0.75" stroke="{post_color}"/>',
        f'<text x="{lx + 18}" y="44" font-family="{font}" font-size="12" fill="{ink}">'
        f"{post.label} p95 {post.p95:.3f}s  answered {post.answered_rate:.3f}</text>",
    ]

    def frame(y0: float, ylabel: str, ticks: list[tuple[float, str]], ymap: Any) -> None:
        parts.append(
            f'<rect x="{ml}" y="{y0}" width="{plot_w}" height="{plot_h}" '
            f'fill="#f6f8fa" stroke="{grid}"/>'
        )
        step = 5 if xmax <= 50 else 10
        xv = 0
        while xv <= xmax + 1e-9:
            x = xmap(xv)
            parts.append(
                f'<line x1="{x:.1f}" y1="{y0}" x2="{x:.1f}" y2="{y0 + plot_h}" stroke="{grid}"/>'
            )
            parts.append(
                f'<text x="{x:.1f}" y="{y0 + plot_h + 16}" text-anchor="middle" '
                f'font-family="{font}" font-size="11" fill="{muted}">{int(xv)}</text>'
            )
            xv += step
        for yv, label in ticks:
            y = ymap(yv)
            parts.append(
                f'<line x1="{ml}" y1="{y:.1f}" x2="{ml + plot_w}" y2="{y:.1f}" stroke="{grid}"/>'
            )
            parts.append(
                f'<text x="{ml - 8}" y="{y + 4:.1f}" text-anchor="end" '
                f'font-family="{font}" font-size="11" fill="{muted}">{label}</text>'
            )
        cx, cy = ml - 48, y0 + plot_h / 2
        parts.append(
            f'<text x="{cx}" y="{cy}" text-anchor="middle" font-family="{font}" '
            f'font-size="12" fill="{ink}" transform="rotate(-90 {cx} {cy})">'
            f"{ylabel}</text>"
        )

    y_step = 10 if ymax > 20 else 5
    frame(
        top_y0,
        "Trials / 1s bin",
        [(v, str(v)) for v in range(0, int(ymax) + 1, y_step)],
        ymap_top,
    )
    frame(
        bot_y0,
        "ECDF",
        [(0, "0"), (0.25, "0.25"), (0.5, "0.50"), (0.75, "0.75"), (0.95, "0.95"), (1, "1")],
        ymap_bot,
    )

    bar = (plot_w / (xmax - xmin)) * 0.42
    for i, (pre_n, post_n) in enumerate(zip(pre_c, post_c, strict=True)):
        x0 = xmap(i * bin_w)
        if pre_n:
            y = ymap_top(pre_n)
            parts.append(
                f'<rect x="{x0 + 1:.1f}" y="{y:.1f}" width="{bar:.1f}" '
                f'height="{top_y0 + plot_h - y:.1f}" fill="{pre_color}" fill-opacity="0.75"/>'
            )
        if post_n:
            y = ymap_top(post_n)
            parts.append(
                f'<rect x="{x0 + 1 + bar:.1f}" y="{y:.1f}" width="{bar:.1f}" '
                f'height="{top_y0 + plot_h - y:.1f}" fill="{post_color}" fill-opacity="0.75"/>'
            )

    def ecdf_pts(xs: list[float]) -> str:
        pts = [(xmap(0), ymap_bot(0))]
        for i, x in enumerate(xs):
            pts.append((xmap(min(x, xmax)), ymap_bot((i + 1) / len(xs))))
        pts.append((xmap(xmax), ymap_bot(1)))
        return " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)

    parts.append(
        f'<polyline fill="none" stroke="{pre_color}" stroke-width="2.2" '
        f'points="{ecdf_pts(pre.latencies)}"/>'
    )
    parts.append(
        f'<polyline fill="none" stroke="{post_color}" stroke-width="2.2" '
        f'points="{ecdf_pts(post.latencies)}"/>'
    )

    def vline(
        x: float,
        y0: float,
        color: str,
        dash: str,
        label: str | None,
        label_y: float | None,
    ) -> None:
        xp = xmap(min(max(x, xmin), xmax))
        parts.append(
            f'<line x1="{xp:.1f}" y1="{y0}" x2="{xp:.1f}" y2="{y0 + plot_h}" '
            f'stroke="{color}" stroke-width="1.4" stroke-dasharray="{dash}"/>'
        )
        if label and label_y is not None:
            parts.append(
                f'<text x="{xp + 4:.1f}" y="{label_y:.1f}" font-family="{font}" '
                f'font-size="10" fill="{color}">{label}</text>'
            )

    vline(ceiling, top_y0, ceil_color, "5 4", f"ceiling {ceiling:g}s", top_y0 + 14)
    vline(pre.p95, top_y0, pre_color, "2 3", None, None)
    vline(post.p95, top_y0, post_color, "2 3", None, None)
    vline(ceiling, bot_y0, ceil_color, "5 4", f"ceiling {ceiling:g}s", bot_y0 + 14)
    vline(pre.p95, bot_y0, pre_color, "2 3", f"{pre.label} p95 {pre.p95:.2f}s", bot_y0 + 28)
    vline(post.p95, bot_y0, post_color, "2 3", f"{post.label} p95 {post.p95:.2f}s", bot_y0 + 42)
    parts += [
        f'<text x="{ml + plot_w / 2}" y="{height - 22}" text-anchor="middle" '
        f'font-family="{font}" font-size="12" fill="{ink}">Latency (seconds)</text>',
        f'<text x="{ml}" y="{height - 8}" font-family="{font}" font-size="10" fill="{muted}">'
        f"Sources: {DEFAULT_JSON} demo.trials latency_s at each snapshot. "
        "Not the transcript body.</text>",
        "</svg>",
    ]
    return "\n".join(parts) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pre",
        required=True,
        help="git ref or path to latest.json from the earlier run",
    )
    parser.add_argument(
        "--post",
        required=True,
        help="git ref or path to latest.json from the later run",
    )
    parser.add_argument("--pre-label", default="pre")
    parser.add_argument("--post-label", default="post")
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"SVG path (default {DEFAULT_OUT.relative_to(ROOT)})",
    )
    parser.add_argument("--title", default="E2E latency — pre vs post merge")
    args = parser.parse_args()
    pre = series_from_latest(load_latest(args.pre), args.pre_label)
    post = series_from_latest(load_latest(args.post), args.post_label)
    ceiling = p95_ceiling()
    svg = render_svg(pre, post, ceiling=ceiling, title=args.title)
    out = args.out if args.out.is_absolute() else ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(svg, encoding="utf-8", newline="\n")
    print(summarize(pre))
    print(summarize(post))
    print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
