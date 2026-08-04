import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/publish-sign-qwen-auth-verifier.yml"
TEXT = WORKFLOW.read_text()

IMAGE_DIGEST = "sha256:a0423439705ee7f3466666e5d999b318067159335cbbd88dc9a1b5a4c2ffeaef"
VEX_SHA256 = "ba6ec01d89e3140a8538d9e5669be8b05f1e31ac3c475cf65a8d6907302dc1ff"
SBOM_SHA256 = "380c366db3c70f743a675285cff7665d2ea86523f5967b76d53293a61b1f09ec"
GOVERNANCE_HEAD = "7c918e328f6336761f0c65540a65fae8b84e9117"


def test_dispatch_only_and_separate_concurrency_group():
    assert "on:\n  workflow_dispatch:\n" in TEXT
    for forbidden_trigger in ("pull_request:", "push:", "schedule:"):
        assert forbidden_trigger not in TEXT
    assert "group: publish-sign-qwen-auth-verifier-a0423439705ee7f" in TEXT
    assert "cancel-in-progress: false" in TEXT


def test_exact_subject_and_evidence_are_hard_bound_without_inputs():
    expected_lines = (
        "IMAGE_REPOSITORY: ghcr.io/codestra-srl/qwen-auth-verifier",
        f"IMAGE_DIGEST: {IMAGE_DIGEST}",
        "OCI_ARCHIVE_PATH: /opt/codestra-jit-input/qwen-auth-verifier-a0423439705ee7f.oci.tar",
        "SKOPEO_VERSION: 1.24.0",
        f"VEX_SHA256: {VEX_SHA256}",
        f"SBOM_SHA256: {SBOM_SHA256}",
        f"GOVERNANCE_HEAD: {GOVERNANCE_HEAD}",
        "CANDIDATE_COMMIT: bbd22cf7a9ff1dd7d6ef12504d21031bc1f5ab75",
    )
    for line in expected_lines:
        assert line in TEXT


def test_protected_environment_runner_and_permissions():
    assert "permissions: {}" in TEXT
    assert "environment: security-owner-signing" in TEXT
    assert "runs-on:\n      group: qwen-artifact-publishers" in TEXT
    assert "labels: codestra-qwen-artifact-publisher" in TEXT
    assert "contents: read\n      packages: write\n      id-token: write\n      attestations: write" in TEXT
    assert "contents: read\n      packages: read" in TEXT


def test_all_third_party_actions_are_immutable_sha_pinned():
    uses = re.findall(r"^\s+uses:\s+(\S+)\s*$", TEXT, flags=re.MULTILINE)
    assert uses
    for action in uses:
        assert "@" in action
        revision = action.rsplit("@", 1)[1]
        assert len(revision) == 40
        assert set(revision) <= set("0123456789abcdef")


def test_workflow_publishes_existing_artifact_without_build_or_deployment():
    forbidden = (
        "docker ",
        "docker.",
        "build-push-action",
        "/var/run/docker.sock",
        "/run/containerd/containerd.sock",
        "containerd.sock",
        "kubectl",
        "systemctl",
        "docker compose",
        "deployment_performed",
    )
    lowered = TEXT.lower()
    for token in forbidden:
        assert token not in lowered
    assert "skopeo copy" in TEXT
    assert '"oci-archive:${OCI_ARCHIVE_PATH}"' in TEXT
    assert '"docker://${target}"' in TEXT


def test_skopeo_copy_preserves_all_manifests_and_digests():
    copy_block = TEXT.split("skopeo copy", 1)[1].split("registry_digest=", 1)[0]
    assert "--all" in copy_block
    assert "--preserve-digests" in copy_block
    assert "--digestfile published-digest.txt" in copy_block
    assert 'test "${registry_digest}" = "${IMAGE_DIGEST}"' in TEXT
    assert 'test "sha256:${remote_digest}" = "${IMAGE_DIGEST}"' in TEXT


def test_registry_auth_is_password_stdin_only_and_always_removed():
    assert "skopeo login" in TEXT
    assert "--password-stdin ghcr.io" in TEXT
    assert "--password " not in TEXT
    assert "--password=${GH_TOKEN}" not in TEXT
    assert 'echo "${GH_TOKEN}"' not in TEXT
    assert TEXT.count('printf \'%s\' "${GH_TOKEN}"') == 2
    assert "if: ${{ always() }}" in TEXT
    assert TEXT.count('rm -- "${REGISTRY_AUTH_FILE}"') == 2
    assert TEXT.count('test ! -e "${REGISTRY_AUTH_FILE}"') == 2


def test_exact_daemonless_destination_and_archive_are_enforced():
    assert "target=\"${IMAGE_REPOSITORY}:${PUBLISH_TAG}\"" in TEXT
    assert "IMAGE_REPOSITORY: ghcr.io/codestra-srl/qwen-auth-verifier" in TEXT
    assert "OCI_ARCHIVE_PATH: /opt/codestra-jit-input/" in TEXT
    assert "command -v skopeo" in TEXT
    assert 'test ! -w "${OCI_ARCHIVE_PATH}"' in TEXT


def test_signature_attestations_and_independent_verification_are_exact():
    assert "cosign sign --yes" in TEXT
    for predicate_type in ("cyclonedx", "slsaprovenance", "openvex"):
        assert f"--type {predicate_type}" in TEXT or '--type "${type}"' in TEXT
    assert "independently-verify:\n    needs: publish-sign\n    runs-on: ubuntu-latest" in TEXT
    assert "--certificate-identity \"${EXPECTED_IDENTITY}\"" in TEXT
    assert "--certificate-oidc-issuer \"${EXPECTED_ISSUER}\"" in TEXT
    assert (
        "EXPECTED_IDENTITY: https://github.com/Codestra-SRL/codestra-middleware/"
        ".github/workflows/publish-sign-qwen-auth-verifier.yml@refs/heads/main"
        in TEXT
    )
    assert "EXPECTED_ISSUER: https://token.actions.githubusercontent.com" in TEXT


def test_existing_middleware_signing_workflow_is_not_referenced_or_modified():
    assert "sign-middleware-release.yml" not in TEXT
    assert "ghcr.io/codestra-srl/codestra-middleware" not in TEXT
