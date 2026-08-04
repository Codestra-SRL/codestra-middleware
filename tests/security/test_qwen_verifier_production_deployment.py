from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy" / "qwen-auth-verifier"
IMAGE = (
    "ghcr.io/codestra-srl/qwen-auth-verifier@sha256:"
    "a0423439705ee7f3466666e5d999b318067159335cbbd88dc9a1b5a4c2ffeaef"
)


def load(name: str) -> dict:
    return yaml.safe_load((DEPLOY / name).read_text())


def test_production_image_is_exact_and_runtime_is_hardened():
    service = load("compose.production.yaml")["services"]["qwen-auth-verifier"]
    assert service["image"] == IMAGE
    assert service["user"] == "10001:10001"
    assert service["restart"] == "unless-stopped"
    assert service["read_only"] is True
    assert service["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in service["security_opt"]
    assert "ports" not in service


def test_only_dedicated_proxy_network_is_trusted():
    service = load("compose.production.yaml")["services"]["qwen-auth-verifier"]
    assert service["environment"]["QWEN_TRUSTED_PROXY_CIDR"] == "10.250.241.2/32"
    assert service["networks"]["qwen_auth_private"]["ipv4_address"] == "10.250.241.3"
    overlay = load("compose.reverse-proxy-network.overlay.yaml")
    proxy = overlay["services"]["reverse-proxy"]
    assert proxy["networks"]["qwen_auth_private"]["ipv4_address"] == "10.250.241.2"
    for document in (load("compose.production.yaml"), overlay):
        network = document["networks"]["qwen_auth_private"]
        assert network == {"external": True, "name": "codestra_qwen_auth_private"}


def test_secret_is_file_mounted_and_never_in_environment():
    service = load("compose.production.yaml")["services"]["qwen-auth-verifier"]
    environment = service["environment"]
    assert environment["QWEN_HMAC_SECRET_FILE"] == "/run/secrets/qwen-hmac"
    assert not any("SECRET=" in str(item) for item in environment.items())
    assert any("qwen-ai-01-hmac-20260804-01:/run/secrets/qwen-hmac:ro" in item for item in service["volumes"])


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
