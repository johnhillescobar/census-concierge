"""Mann-Whitney AUC must not depend on the order of tied scores.

`auc()` is a rank-sum. A value that sits in both the positive and the negative
group is a tie; those two observations must share the average rank. Assigning
distinct ordinal ranks (1..n by argsort position) makes the reported separation
depend on input order, not on whether the groups actually separate.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

# experiments/ is throwaway and not an installed package; pytest's path is api/.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.run_margin import auc  # noqa: E402

# 0.2 is in both groups. Mid-ranks give 0.750 either way. Ordinal ranks flip
# 0.833 <-> 0.667 when the same values are presented in reverse.
POSITIVE = np.array([0.1, 0.2, 0.3])
NEGATIVE = np.array([0.2, 0.05])


def test_auc_with_a_cross_group_tie_does_not_depend_on_input_order() -> None:
    forward = auc(POSITIVE, NEGATIVE)
    reversed_inputs = auc(POSITIVE[::-1], NEGATIVE[::-1])

    assert forward == reversed_inputs
    assert forward == 0.75
