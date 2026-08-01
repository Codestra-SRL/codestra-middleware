from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/candidate-image-evidence.yml"


def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_workflow_is_manual_protected_main_and_explicitly_bound() -> None:
    text = workflow_text()
    parsed = yaml.safe_load(text)
    assert "workflow_dispatch" in parsed[True]
    assert "pull_request" not in parsed[True]
    for value in ("target_repository", "pr_number", "source_sha"):
        assert value in parsed[True]["workflow_dispatch"]["inputs"]
    assert "github.ref == 'refs/heads/main'" in text
    assert "gh api" in text and ".head.sha" in text
    assert 'test "$(git rev-parse HEAD)" = "${SOURCE_SHA}"' in text


def test_permissions_and_environment_are_narrow() -> None:
    text = workflow_text()
    assert "environment: security-owner-signing" in text
    assert "packages: write" in text
    assert "pull-requests: read" in text
    assert "contents: read" in text
    assert "id-token: write" not in text
    for permission in ("deployments: write", "actions: write", "contents: write"):
        assert permission not in text


def test_trust_and_target_identities_are_distinct() -> None:
    text = workflow_text()
    assert '"trusted_workflow_sha":"${{ github.sha }}"' in text
    assert '"target_source_sha":"${{ inputs.source_sha }}"' in text
    assert '"candidate_image_digest":"${{ steps.identity.outputs.image_digest }}"' in text
    assert "ref: ${{ github.sha }}" in text
    assert "ref: ${{ inputs.source_sha }}" in text


def test_never_approves_or_authorizes_execution() -> None:
    text = workflow_text()
    assert 'security_owner_acceptance_present":false' in text
    assert 'deployment_allowed":false' in text
    assert 'activation_allowed":false' in text
    for forbidden in ("approved_for_staging", "kubectl", "docker compose up", "n8n import"):
        assert forbidden not in text


def test_all_actions_are_commit_pinned() -> None:
    for line in workflow_text().splitlines():
        if "uses:" in line:
            reference = line.split("@", 1)[1]
            assert len(reference) == 40
            int(reference, 16)
