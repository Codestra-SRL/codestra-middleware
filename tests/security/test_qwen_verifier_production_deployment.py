from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "qwen-auth-verifier"
IMAGE = (
    "ghcr.io/codestra-srl/qwen-auth-verifier@sha256:"
    "a0423439705ee7f3466666e5d999b318067159335cbbd88dc9a1b5a4c2ffeaef"
)


def load_text(name: str) -> str:
    return (DEPLOY / name).read_text()


def test_production_image_is_exact_and_runtime_is_hardened():
    text = load_text("compose.production.yaml")
    assert f"image: {IMAGE}" in text
    assert 'user: "10001:10001"' in text
    assert "restart: unless-stopped" in text
    assert "read_only: true" in text
    assert "cap_drop: [ALL]" in text
    assert "no-new-privileges:true" in text
    assert "ports:" not in text


def test_only_dedicated_proxy_network_is_trusted():
    verifier = load_text("compose.production.yaml")
    overlay = load_text("compose.reverse-proxy-network.overlay.yaml")
    assert "QWEN_TRUSTED_PROXY_CIDR: 10.250.241.2/32" in verifier
    assert "ipv4_address: 10.250.241.3" in verifier
    assert "ipv4_address: 10.250.241.2" in overlay
    for text in (verifier, overlay):
        assert "external: true" in text
        assert "name: codestra_qwen_auth_private" in text


def test_secret_is_file_mounted_and_never_in_environment():
    text = load_text("compose.production.yaml")
    assert "QWEN_HMAC_SECRET_FILE: /run/secrets/qwen-hmac" in text
    assert "QWEN_HMAC_SECRET:" not in text
    assert "qwen-ai-01-hmac-20260804-01:/run/secrets/qwen-hmac:ro" in text


def test_caddy_route_is_exact_private_and_overwrites_identity_header():
    text = (DEPLOY / "Caddyfile.production.snippet").read_text()
    assert "remote_ip 10.40.0.4" in text
    assert "method POST" in text
    assert "path /internal/api/v1/ai/auth/verify" in text
    assert "reverse_proxy qwen-auth-verifier:8095" in text
    assert "header_up -X-Codestra-Client-Certificate" in text
    assert "header_up X-Codestra-Client-Certificate" in text


def test_runbook_requires_rollback_and_preserves_vicidial():
    text = (DEPLOY / "PRODUCTION_DEPLOYMENT.md").read_text()
    assert "automatic rollback" in text
    assert "Do not modify the" in text
    assert "VICIdial matcher" in text
    assert "Remove only the two UID 10001 ACL entries" in text
