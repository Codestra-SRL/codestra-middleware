#!/usr/bin/env python3
"""Classify legacy-table governance gaps without changing a database."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

REQUIRED = (
    "tenant_id", "workspace_id", "created_at", "updated_at", "created_by",
    "updated_by", "deleted_at", "version", "audit_id",
)


def wave_for(table: str) -> tuple[str, str]:
    if table.startswith("iam_") or table == "credential_grant":
        return "WAVE_1_IDENTITY_TENANT_WORKSPACE", "IDENTITY_OWNER"
    if table.startswith(("enterprise_event", "integration_", "n8n_")) or table in {
        "broad_event_delivery", "event_inbox", "idempotency_record", "orchestration_request",
        "outbox_event", "policy_decision", "publisher_acknowledgement", "publisher_nonce",
        "reconciliation_checkpoint", "webhook_delivery",
    }:
        return "WAVE_2_COMMAND_EVENT_WORKFLOW_AUDIT", "INTEGRATION_PLATFORM_OWNER"
    if table.startswith(("lead_automation", "campaign_")) or table in {
        "lead_sync_request", "odoo_result_delivery", "sync_job",
    }:
        return "WAVE_3_ODOO_INTEGRATION_AND_BUSINESS_RECORDS", "ODOO_BUSINESS_OWNER"
    if table.startswith(("telephony_", "vicidial_", "recording", "notification_")) or table == "transfer_policy_decision":
        return "WAVE_4_COMMUNICATIONS_AND_TELEPHONY", "COMMUNICATIONS_OWNER"
    if table.startswith(("ai_", "memory_", "knowledge_", "tool_")):
        return "WAVE_5_AI_MEMORY_KNOWLEDGE_AND_TOOLS", "AI_PLATFORM_OWNER"
    if table.startswith(("commercial_", "usage_", "billing_", "subscription_", "invoice_")):
        return "WAVE_6_COMMERCIAL_USAGE_AND_BILLING", "COMMERCIAL_OWNER"
    return "WAVE_7_REPORTING_SECURITY_AND_LEGACY_MISCELLANEOUS", "SECURITY_DATA_OWNER"


def immutable(table: str) -> bool:
    return any(token in table for token in ("audit", "event", "attempt", "transition", "rejection"))


def classify(table: str, column: str, present: set[str]) -> tuple[str, str]:
    if column in present:
        return "REQUIRED_NOW", "already present; validate type, nullability, constraint, and index"
    if table == "iam_tenant" and column in {"tenant_id", "workspace_id"}:
        return "NOT_APPLICABLE", "root-scope table; self-referential scope is prohibited"
    if column == "deleted_at" and immutable(table):
        return "NOT_APPLICABLE", "append-only history; deletion must remain prohibited"
    if column in {"tenant_id", "workspace_id", "created_by", "updated_by"}:
        return "REQUIRES_DOMAIN_OWNER", "authoritative scope/actor source must be approved"
    if column in {"created_at", "updated_at", "version", "audit_id"}:
        return "REQUIRES_BACKFILL", "deterministic source and rollback proof required before NOT NULL"
    return "REQUIRED_NOW", "reviewed schema addition required"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("inventory", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    rows = list(csv.DictReader(args.inventory.open()))
    details: list[dict[str, object]] = []
    waves: dict[str, dict[str, object]] = {}
    compliant = 0
    root_exceptions = 0
    for row in rows:
        table = row["table_name"]
        present = set(filter(None, row["present_governance_columns"].split("|")))
        wave, owner = wave_for(table)
        columns = []
        for column in REQUIRED:
            status, reason = classify(table, column, present)
            columns.append({"column": column, "classification": status, "reason": reason})
        is_compliant = all(item["classification"] in {"REQUIRED_NOW", "NOT_APPLICABLE"} for item in columns)
        if row["fully_compliant"] == "t":
            compliant += 1
        if table == "iam_tenant":
            root_exceptions += 1
        item = {
            "table": table, "wave": wave, "authority": owner,
            "estimated_rows": int(row["estimated_rows"]),
            "fully_compliant": row["fully_compliant"] == "t",
            "review_ready": is_compliant,
            "columns": columns,
        }
        details.append(item)
        bucket = waves.setdefault(wave, {"authority": owner, "tables": []})
        wave_tables = bucket["tables"]
        if not isinstance(wave_tables, list):
            raise TypeError("wave tables must be a list")
        wave_tables.append(table)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({"schema_version": "1.0", "tables": details}, indent=2) + "\n")
    summary = {
        "database_table_count_excluding_alembic": len(rows),
        "fully_compliant": compliant,
        "root_scope_exceptions": root_exceptions,
        "migration_candidates": len(rows) - compliant - root_exceptions,
        "waves": waves,
    }
    args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
