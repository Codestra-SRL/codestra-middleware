"""Fail-closed marketplace manifest and plugin lifecycle contracts."""
import hashlib
import json
from dataclasses import dataclass

PLUGIN_STATES = frozenset({"DRAFT", "VALIDATING", "SECURITY_REVIEW", "BUSINESS_REVIEW", "APPROVED", "PUBLISHED_STAGING", "AVAILABLE", "INSTALLING", "INSTALLED", "CONFIGURING", "ACTIVE", "DEGRADED", "SUSPENDED", "UPGRADE_AVAILABLE", "UPGRADING", "ROLLING_BACK", "FAILED", "UNINSTALLING", "UNINSTALLED", "REVOKED"})
CAPABILITIES = frozenset({"middleware.api.read", "middleware.api.write.approved", "middleware.events.publish", "middleware.jobs.create", "ai.inference.request", "ai.prompt.use", "ai.knowledge.search", "scraper.results.read", "vicidial.calls.read", "vicidial.lead.create.staging", "portal.navigation.extend", "portal.dashboard.extend", "bi.dashboard.extend"})


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class PluginManifest:
    plugin_code: str
    publisher_id: str
    plugin_type: str
    version: str
    requested_capabilities: tuple[str, ...]
    package_digest: str
    signature: str


def validate_manifest(raw: dict) -> PluginManifest:
    required = ("plugin_code", "publisher_id", "plugin_type", "version", "requested_capabilities", "package_digest", "signature")
    if any(not raw.get(key) for key in required) or not isinstance(raw.get("requested_capabilities"), list):
        raise ManifestError("required signed manifest fields missing")
    capabilities = tuple(raw["requested_capabilities"])
    if "*" in capabilities or any(capability not in CAPABILITIES for capability in capabilities):
        raise ManifestError("undeclared capability requested")
    if not str(raw["package_digest"]).startswith("sha256:") or len(str(raw["signature"])) < 16:
        raise ManifestError("invalid package digest or signature")
    return PluginManifest(raw["plugin_code"], raw["publisher_id"], raw["plugin_type"], raw["version"], capabilities, raw["package_digest"], raw["signature"])


def manifest_digest(raw: dict) -> str:
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def transition(current: str, target: str) -> str:
    allowed = {"DRAFT": {"VALIDATING"}, "VALIDATING": {"SECURITY_REVIEW", "FAILED"}, "SECURITY_REVIEW": {"BUSINESS_REVIEW", "FAILED"}, "BUSINESS_REVIEW": {"APPROVED", "FAILED"}, "APPROVED": {"PUBLISHED_STAGING"}, "PUBLISHED_STAGING": {"AVAILABLE"}, "AVAILABLE": {"INSTALLING"}, "INSTALLING": {"INSTALLED", "FAILED"}, "INSTALLED": {"CONFIGURING", "ACTIVE", "UPGRADE_AVAILABLE", "UNINSTALLING"}, "ACTIVE": {"DEGRADED", "SUSPENDED", "UPGRADING", "ROLLING_BACK", "UNINSTALLING"}, "UPGRADING": {"ACTIVE", "ROLLING_BACK", "FAILED"}, "ROLLING_BACK": {"ACTIVE", "FAILED"}, "UNINSTALLING": {"UNINSTALLED", "FAILED"}}
    if target not in PLUGIN_STATES or target not in allowed.get(current, set()):
        raise ManifestError(f"invalid plugin transition: {current} -> {target}")
    return target
