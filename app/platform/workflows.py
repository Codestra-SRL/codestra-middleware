from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class WorkflowArtifact:
    name: str
    version: str
    sha256: str
    document: dict[str, Any]


def canonical_workflow(path: Path) -> WorkflowArtifact:
    document = json.loads(path.read_text())
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    manifest = document["codestraManifest"]
    return WorkflowArtifact(
        document["name"],
        manifest["workflow_version"],
        hashlib.sha256(canonical).hexdigest(),
        document,
    )


def detect_drift(expected: WorkflowArtifact, observed: dict[str, Any]) -> bool:
    canonical = json.dumps(observed, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest() != expected.sha256


def deployment_record(
    *,
    artifact: WorkflowArtifact,
    git_sha: str,
    environment: str,
    deployer: str,
    previous_version: str | None,
) -> dict[str, Any]:
    if environment not in {"development", "staging", "production"}:
        raise ValueError("WORKFLOW_ENVIRONMENT_INVALID")
    if len(git_sha) != 40:
        raise ValueError("WORKFLOW_GIT_SHA_INVALID")
    return {
        "workflow": artifact.name,
        "version": artifact.version,
        "git_sha": git_sha,
        "environment": environment,
        "deployer": deployer,
        "previous_version": previous_version,
        "rollback_pointer": f"git:{git_sha}:{artifact.name}:{previous_version or 'none'}",
    }


HIGH_RISK_NODE_TYPES = frozenset(
    {
        "n8n-nodes-base.executeCommand",
        "n8n-nodes-base.ssh",
        "n8n-nodes-base.code",
        "n8n-nodes-base.readWriteFile",
    }
)


def security_findings(document: dict[str, Any]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for node in document.get("nodes", []):
        node_type = str(node.get("type", ""))
        if node_type in HIGH_RISK_NODE_TYPES:
            findings.append(
                {
                    "severity": "HIGH",
                    "code": "N8N_NODE_PROHIBITED",
                    "node": str(node.get("name", "unknown")),
                }
            )
        if node_type.startswith("n8n-nodes-") and not node_type.startswith(
            "n8n-nodes-base."
        ):
            findings.append(
                {
                    "severity": "MEDIUM",
                    "code": "N8N_COMMUNITY_NODE_UNREVIEWED",
                    "node": str(node.get("name", "unknown")),
                }
            )
    return findings
