#!/usr/bin/env python3
"""Build the Phase 7.3 promotion risk ledger from current evidence."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from phase73_risk_semantics import CLOSED_STATES, semantic_counts, validate_inventory_records


def build_ledger(
    inventory: Mapping[str, object],
    host_manifest: Mapping[str, object],
    scanner_inventory: Mapping[str, object],
    real_cycle: Mapping[str, object],
) -> dict[str, object]:
    """Build one entry for every High/Medium and every environment limitation."""

    branches = _records(inventory.get("branches"), "inventory branches")
    validate_inventory_records(branches)
    counts = semantic_counts(branches)
    entries: list[dict[str, object]] = []
    for branch in branches:
        risk_level = str(branch["risk_level"])
        if risk_level not in {"high", "medium"}:
            continue
        closure = str(branch["closure_status"])
        closed = closure in CLOSED_STATES
        evidence = list(branch["existing_evidence"])
        if branch["materiality"] == "MATERIAL_BUT_ALREADY_COVERED_BY_PRIOR_CONTRACT_EVIDENCE":
            evidence.append("material-medium-proof.json")
        entries.append(
            {
                "risk_id": branch["branch_id"],
                "kind": "BRANCH",
                "risk_level": risk_level,
                "category": branch["category"],
                "materiality": branch["materiality"],
                "closure_status": closure,
                "status": "CLOSED" if closed else "OPEN",
                "promotion_impact": "NO_BLOCK" if closed else "BLOCK",
                "evidence": sorted(set(evidence)),
            }
        )

    entries.append(_host_entry(host_manifest, real_cycle))
    entries.extend(_scanner_entries(scanner_inventory))
    if any(item["promotion_impact"] == "BLOCK" for item in entries):
        raise ValueError("promotion ledger contains an open blocking entry")
    return {
        "schema_version": "P7.3-PROMOTION-RISK-LEDGER-1",
        "phase": "PHASE7.3",
        "semantic_counts": counts,
        "promotion_gate": {
            "open_actionable_high": counts["open_actionable_high"],
            "promotion_blocking_high": counts["promotion_blocking_high"],
            "open_actionable_medium": counts["open_actionable_medium"],
            "promotion_blocking_medium": counts["promotion_blocking_medium"],
        },
        "entries": sorted(entries, key=lambda item: str(item["risk_id"])),
        "status": "CLOSED_WITH_LIMITATIONS",
    }


def generate_ledger(
    inventory_path: Path,
    host_path: Path,
    scanner_path: Path,
    cycle_path: Path,
    output_path: Path,
) -> dict[str, object]:
    """Read evidence inputs and write one deterministic ledger."""

    inventory = _load(inventory_path)
    host = _load(host_path)
    scanners = _load(scanner_path)
    cycle = _load(cycle_path)
    ledger = build_ledger(inventory, host, scanners, cycle)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return ledger


def _host_entry(manifest: Mapping[str, object], cycle: Mapping[str, object]) -> dict[str, object]:
    cycle_status = cycle.get("status")
    if cycle_status != "PASS_WITH_LIMITATIONS":
        raise ValueError(f"real cycle is not promotable: {cycle_status!r}")
    preflight = manifest.get("preflight")
    if (
        not isinstance(preflight, Mapping)
        or preflight.get("status") != "RESOLVED_READ_ONLY_VERSION_PROBE"
    ):
        raise ValueError("host bootstrap preflight is not resolved")
    return {
        "risk_id": "ENV-HOST-REAL-CYCLE",
        "kind": "ENVIRONMENT",
        "status": "CLOSED_WITH_LIMITATIONS",
        "promotion_impact": "LIMITATION",
        "evidence": [
            "host-bootstrap-manifest.json",
            "real-cycle-report.md",
        ],
        "detail": "Absolute host pins resolved and the bounded real cycle passed.",
    }


def _scanner_entries(payload: Mapping[str, object]) -> list[dict[str, object]]:
    scanners = payload.get("scanners")
    if not isinstance(scanners, Mapping):
        raise ValueError("scanner inventory has no scanners object")
    entries: list[dict[str, object]] = []
    for name, value in sorted(scanners.items()):
        if not isinstance(name, str) or not isinstance(value, Mapping):
            raise ValueError("scanner inventory entries are invalid")
        status = value.get("status")
        if status == "AVAILABLE":
            entry_status = "CLOSED_WITH_RESULT"
            detail = "Scanner availability was captured; execution is recorded separately."
        elif status == "UNAVAILABLE":
            entry_status = "CLOSED_BY_FORMAL_WAIVER"
            detail = "Optional scanner unavailable; no PASS claim was made."
        else:
            raise ValueError(f"scanner {name} has unsupported status: {status!r}")
        entries.append(
            {
                "risk_id": f"ENV-SCANNER-{name.upper().replace('-', '_')}",
                "kind": "SECURITY_SCANNER",
                "scanner": name,
                "status": entry_status,
                "promotion_impact": "LIMITATION",
                "evidence": [
                    "security-scanner-inventory.json",
                    "security-scanner-report.md",
                    "waivers/WAIVER-SECURITY-SCANNERS.md",
                ],
                "detail": detail,
            }
        )
    return entries


def _records(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise ValueError(f"{label} must be a list of objects")
    return value


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--host-manifest", type=Path, required=True)
    parser.add_argument("--scanner-inventory", type=Path, required=True)
    parser.add_argument("--real-cycle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    ledger = generate_ledger(
        args.inventory,
        args.host_manifest,
        args.scanner_inventory,
        args.real_cycle,
        args.output,
    )
    print(json.dumps({"status": ledger["status"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
