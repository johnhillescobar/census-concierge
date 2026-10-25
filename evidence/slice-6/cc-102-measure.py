"""CC-102 evidence: wall time and peak process memory of comparison_rows by row shape.

    uv run python evidence/slice-6/cc-102-measure.py ROWS COLUMNS

Synthetic rows only, no network. Prints one JSON line. Each shape runs in its own
process so the peak is that shape's alone.
"""

import ctypes
import json
import sys
import time
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "api"))

from src.compare import comparison_rows  # noqa: E402


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def peak_mb() -> float:
    counters = _Counters()
    counters.cb = ctypes.sizeof(counters)
    handle = ctypes.windll.kernel32.GetCurrentProcess()
    ctypes.windll.psapi.GetProcessMemoryInfo(
        ctypes.c_void_p(handle), ctypes.byref(counters), counters.cb
    )
    return counters.PeakWorkingSetSize / 2**20


def main() -> None:
    n_rows, n_cols = int(sys.argv[1]), int(sys.argv[2])
    rows = [
        {
            "GEO_ID": f"1400000US48{i:09d}",
            **{f"B17001_{c:03d}E": str(100 + i + c) for c in range(1, n_cols + 1)},
            **{f"B17001_{c:03d}M": str(10 + c) for c in range(1, n_cols + 1)},
        }
        for i in range(n_rows)
    ]
    record = SimpleNamespace(question="Is the poverty rate higher in one tract than another?")
    baseline = peak_mb()
    started = time.perf_counter()
    out = comparison_rows(record, rows)
    elapsed = time.perf_counter() - started
    pairs = n_rows * (n_rows - 1) // 2
    print(
        json.dumps(
            {
                "rows": n_rows,
                "estimate_columns": n_cols,
                "pairs": pairs,
                "work": pairs * n_cols,
                "comparisons": len(out),
                "seconds": round(elapsed, 3),
                "peak_mb": round(peak_mb(), 1),
                "baseline_mb": round(baseline, 1),
            }
        )
    )


main()
