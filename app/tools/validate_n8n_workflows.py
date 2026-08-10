from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ALLOWED_NODE_PREFIXES = ("n8n-nodes-base.", "@codestra/n8n-nodes-codestra.")
PROHIBITED_NODE_TYPES = frozenset(
    {
        "n8n-nodes-base.executeCommand",
        "n8n-nodes-base.ssh",
        "n8n-nodes-base.readWriteFile",
        "n8n-nodes-base.code",
    }
)
PROHIBITED_TEXT = (
    "postiz",
    "postly",
    "hootsuite",
    "/web/dataset/call_kw",
    "odoo/write",
    "Authorization: Bearer",
)
REQUIRED_MANIFEST_FIELDS = frozenset(
    {
        "workflow_name",
        "workflow_version",
        "owner",
        "input_schema",
        "output_schema",
        "required_credentials",
        "required_nodes",
        "risk_class",
        "production_allowed",
        "rollback_version",
        "enabled_event_types",
    }
)


class WorkflowValidationError(ValueError):
    pass


def validate_workflow(document: dict[str, Any], source: Path) -> list[str]:
    errors: list[str] = []
    manifest = document.get("codestraManifest")
    if not isinstance(manifest, dict) or REQUIRED_MANIFEST_FIELDS - manifest.keys():
        errors.append("missing or incomplete codestraManifest")
    nodes = document.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return errors + ["workflow graph is empty"]
    names = {str(node.get("name", "")) for node in nodes if isinstance(node, dict)}
    if "" in names or len(names) != len(nodes):
        errors.append("node names must be present and unique")
    for node in nodes:
        node_type = str(node.get("type", ""))
        if node_type in PROHIBITED_NODE_TYPES or not node_type.startswith(
            ALLOWED_NODE_PREFIXES
        ):
            errors.append(f"unapproved node type: {node_type}")
    connections = document.get("connections")
    if not isinstance(connections, dict) or not connections:
        errors.append("workflow graph has no connections")
    else:
        referenced = set(connections)
        for branches in connections.values():
            for outputs in branches.values():
                for output in outputs:
                    referenced.add(output.get("node"))
        dangling = names - referenced
        if dangling:
            errors.append(f"dangling nodes: {sorted(dangling)}")
    lowered = json.dumps(document, sort_keys=True).casefold()
    for prohibited in PROHIBITED_TEXT:
        if prohibited.casefold() in lowered:
            errors.append(f"prohibited direct integration reference: {prohibited}")
    node_types = {str(node.get("type", "")) for node in nodes}
    if "@codestra/n8n-nodes-codestra.CodestraAudit" not in node_types:
        errors.append("missing audit/result callback node")
    if "@codestra/n8n-nodes-codestra.CodestraDeadLetter" not in node_types:
        errors.append("missing dead-letter path")
    return [f"{source}: {error}" for error in errors]


def validate_tree(root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(root.rglob("*.json")):
        try:
            document = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: invalid JSON: {exc}")
            continue
        errors.extend(validate_workflow(document, path))
    if not list(root.rglob("*.json")):
        errors.append(f"{root}: no workflow documents")
    return errors


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else "integrations/n8n/workflows")
    errors = validate_tree(root)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"validated {len(list(root.rglob('*.json')))} Codestra workflows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
