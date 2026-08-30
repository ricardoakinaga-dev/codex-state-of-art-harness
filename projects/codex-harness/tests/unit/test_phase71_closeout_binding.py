from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_phase7_real_repair import (  # noqa: E402
    _evidence_label as repair_evidence_label,
)
from scripts.run_phase7_real_verifier import (  # noqa: E402
    _evidence_label as verifier_evidence_label,
)


def test_real_receipt_labels_bind_to_the_current_project_namespace() -> None:
    project = Path.cwd()
    builder = project / "evidence" / "phase-7.1" / "real-rerun" / "builder-receipt.json"
    artifact = project / "evidence" / "phase-7.1" / "real-rerun" / "PHASE7.1-REPAIR" / "artifact-v3"

    assert repair_evidence_label(builder) == "evidence/phase-7.1/real-rerun/builder-receipt.json"
    assert verifier_evidence_label(artifact) == (
        "evidence/phase-7.1/real-rerun/PHASE7.1-REPAIR/artifact-v3"
    )
