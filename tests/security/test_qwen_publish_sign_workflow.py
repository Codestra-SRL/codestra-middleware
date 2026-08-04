from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/publish-sign-qwen-auth-verifier.yml"
TEXT = WORKFLOW.read_text()
DOC = yaml.safe_load(TEXT)

IMAGE_DIGEST = "sha256:a0423439705ee7f3466666e5d999b318067159335cbbd88dc9a1b5a4c2ffeaef"
VEX_SHA256 = "ba6ec01d89e3140a8538d9e5669be8b05f1e31ac3c475cf65a8d6907302dc1ff"
SBOM_SHA256 = "380c366db3c70f743a675285cff7665d2ea86523f5967b76d53293a61b1f09ec"
GOVERNANCE_HEAD = "7c918e328f6336761f0c65540a65fae8b84e9117"


def test_dispatch_only_and_separate_concurrency_group():
    trigger = DOC.get("on", DOC.get(True))
    assert set(trigger) == {"workflow_dispatch"}
    assert trigger["workflow_dispatch"] is None
    assert DOC["concurrency"] == {
        "group": "publish-sign-qwen-auth-verifier-a0423439705ee7f",
        "cancel-in-progress": False,
    }


def test_exact_subject_and_evidence_are_hard_bound_without_inputs():
    assert DOC["env"]["IMAGE_REPOSITORY"] == "ghcr.io/codestra-srl/qwen-auth-verifier"
    assert DOC["env"]["IMAGE_DIGEST"] == IMAGE_DIGEST
    assert DOC["env"]["LOCAL_IMAGE_ID"] == IMAGE_DIGEST
    assert DOC["env"]["VEX_SHA256"] == VEX_SHA256
    assert DOC["env"]["SBOM_SHA256"] == SBOM_SHA256
    assert DOC["env"]["GOVERNANCE_HEAD"] == GOVERNANCE_HEAD
    assert DOC["env"]["CANDIDATE_COMMIT"] == "bbd22cf7a9ff1dd7d6ef12504d21031bc1f5ab75"


def test_protected_environment_runner_and_permissions():
    publish = DOC["jobs"]["publish-sign"]
    assert publish["environment"] == "security-owner-signing"
    assert publish["runs-on"] == [
        "self-hosted",
        "linux",
        "x64",
        "codestra-qwen-artifact-publisher",
    ]
    assert DOC["permissions"] == {}
    assert publish["permissions"] == {
        "contents": "read",
        "packages": "write",
        "id-token": "write",
        "attestations": "write",
    }
    assert DOC["jobs"]["independently-verify"]["permissions"] == {
        "contents": "read",
        "packages": "read",
    }


def test_all_third_party_actions_are_immutable_sha_pinned():
    uses = []
    for job in DOC["jobs"].values():
        uses.extend(step["uses"] for step in job["steps"] if "uses" in step)
    assert uses
    for action in uses:
        assert "@" in action
        revision = action.rsplit("@", 1)[1]
        assert len(revision) == 40
        assert set(revision) <= set("0123456789abcdef")


def test_workflow_publishes_existing_artifact_without_build_or_deployment():
    forbidden = (
        "docker build ",
        "docker buildx build",
        "build-push-action",
        "kubectl",
        "systemctl",
        "docker compose",
        "deployment_performed",
    )
    lowered = TEXT.lower()
    for token in forbidden:
        assert token not in lowered
    assert 'docker image inspect "${LOCAL_IMAGE_ID}"' in TEXT
    assert 'docker image push "${target}"' in TEXT
    assert 'registry_digest}" != "${IMAGE_DIGEST}' in TEXT
    assert "cleanup_mismatched_tag" in TEXT


def test_signature_attestations_and_independent_verification_are_exact():
    assert "cosign sign --yes" in TEXT
    for predicate_type in ("cyclonedx", "slsaprovenance", "openvex"):
        assert f"--type {predicate_type}" in TEXT or f'--type "${{type}}"' in TEXT
    assert DOC["jobs"]["independently-verify"]["needs"] == "publish-sign"
    assert DOC["jobs"]["independently-verify"]["runs-on"] == "ubuntu-latest"
    assert "--certificate-identity \"${EXPECTED_IDENTITY}\"" in TEXT
    assert "--certificate-oidc-issuer \"${EXPECTED_ISSUER}\"" in TEXT
    assert "@refs/heads/main" in DOC["env"]["EXPECTED_IDENTITY"]
    assert DOC["env"]["EXPECTED_ISSUER"] == "https://token.actions.githubusercontent.com"


def test_existing_middleware_signing_workflow_is_not_referenced_or_modified():
    assert "sign-middleware-release.yml" not in TEXT
    assert "ghcr.io/codestra-srl/codestra-middleware" not in TEXT
