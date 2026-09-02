from pathlib import Path


def test_external_webhook_tmpfs_is_one_quoted_mount_specification() -> None:
    compose = (
        Path(__file__).parents[1]
        / "deploy"
        / "external-webhook"
        / "compose.production.yaml"
    ).read_text(encoding="utf-8")

    assert (
        'tmpfs: ["/tmp:rw,noexec,nosuid,size=32m,uid=10001,gid=10001"]'
        in compose
    )
