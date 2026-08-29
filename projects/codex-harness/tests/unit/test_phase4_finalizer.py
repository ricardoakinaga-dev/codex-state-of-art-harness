from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPT_ROOT = Path(__file__).parents[2] / "scripts"
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from finalize_phase4_evidence import _parse_review_summary  # noqa: E402


def test_finalizer_requires_machine_readable_review_counts() -> None:
    summary = _parse_review_summary(
        "\n".join(
            (
                "Review verdict: PASS_WITH_LIMITATIONS",
                "Critical findings: 0",
                "High findings: 0",
                "Medium findings: 1",
                "Low findings: 2",
            )
        )
    )

    assert summary == {
        "verdict": "PASS_WITH_LIMITATIONS",
        "critical": 0,
        "high": 0,
        "medium": 1,
        "low": 2,
    }


def test_finalizer_rejects_missing_or_duplicate_review_summary() -> None:
    with pytest.raises(RuntimeError, match="exactly one critical"):
        _parse_review_summary("Review verdict: PASS_WITH_LIMITATIONS\n")

    text = "\n".join(
        (
            "Review verdict: PASS_WITH_LIMITATIONS",
            "Critical findings: 0",
            "Critical findings: 0",
            "High findings: 0",
            "Medium findings: 0",
            "Low findings: 0",
        )
    )
    with pytest.raises(RuntimeError, match="exactly one critical"):
        _parse_review_summary(text)
