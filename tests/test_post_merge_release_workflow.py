from pathlib import Path


WORKFLOW = Path(".github/workflows/staging-candidate-build-sign.yml")


def test_post_merge_mode_preserves_signed_authority_gate() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "options: [reviewed_pr_head, protected_main_merge]" in source
    assert "Download and verify exact signed Security Owner authority" in source
    assert "cosign-authority\" verify-blob" in source
    assert "security-owner-authority-sign.yml@refs/heads/main" in source


def test_post_merge_mode_is_restricted_to_protected_main_history() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert 'test "$(jq -r .merge_commit_sha pr.json)" = "${SOURCE_SHA}"' in source
    assert '.merge_base_commit.sha == $source' in source
    assert '(.status == "ahead" or .status == "identical")' in source
    assert '.context == "codestra/required-ci" and .state == "success"' in source
    assert '.state == "APPROVED" and .commit_id == $head' in source


def test_candidate_still_builds_exact_source_non_root() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert "ref: ${{ inputs.source_sha }}" in source
    assert 'test "$(git rev-parse HEAD)" = "${SOURCE_SHA}"' in source
    dockerfile = Path("Dockerfile").read_text(encoding="utf-8")
    assert "USER 10001:10001" in dockerfile
