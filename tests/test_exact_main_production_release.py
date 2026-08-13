from pathlib import Path


WORKFLOW = Path(".github/workflows/exact-main-production-release.yml")


def source() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_exact_main_identity_and_independent_approval_are_required() -> None:
    value = source()
    assert 'test "$(jq -r .merge_commit_sha pr.json)" = "${SOURCE_SHA}"' in value
    assert '.merge_base_commit.sha == $source' in value
    assert '.state == "APPROVED" and .commit_id == $head' in value
    assert '.context == "codestra/required-ci" and .state == "success"' in value


def test_production_authority_is_signed_and_explicit() -> None:
    value = source()
    assert "security-owner-authority.sigstore.json" in value
    assert 'index("server_a_production_release")' in value
    assert 'index("production_deployment")' in value
    assert 'index("external_delivery_synthetic_only")' in value
    assert ".communications.calls == false" in value


def test_image_is_non_root_scanned_signed_and_pulled_by_digest() -> None:
    value = source()
    assert "USER 10001:10001" in Path("Dockerfile").read_text(encoding="utf-8")
    assert "Run Trivy without suppression" in value
    assert "Run raw Grype without suppression" in value
    assert "Run VEX-applied Grype" in value
    assert "verify-blob" in value
    assert "docker image rm" in value
    assert "docker pull \"${subject}\"" in value
    assert "cosign\" verify-attestation" in value


def test_release_is_separate_from_staging_candidate_workflow() -> None:
    value = source()
    assert "staging-candidate-build-sign.yml" not in value
    assert "exact-main-middleware-production" in value
