import base64
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

VICIDIAL_PRIVATE_HOSTS = frozenset(
    {
        "authorization.internal.codestra.agency",
        "edge.internal.codestra.agency",
    }
)
VICIDIAL_PRIVATE_PORT = 8443
VICIDIAL_ENDPOINT_ADAPTER_PORT = 8444
VICIDIAL_SECRET_ROOT = Path("/run/secrets/vicidial-mtls")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")
    database_url: str = "postgresql+asyncpg://localhost/codestra_middleware"
    database_url_file: str = ""
    redis_url: str = "redis://localhost:6379/2"
    redis_url_file: str = ""
    registry_snapshot_signing_key_file: str = ""
    registry_l1_ttl_seconds: int = 15
    registry_l2_ttl_seconds: int = 60
    registry_stale_grace_seconds: int = 300
    registry_service_issuer: str = ""
    registry_service_audience: str = "codestra-middleware"
    registry_service_jwks_url: str = ""
    registry_service_client_id: str = "codestra-registry-client"
    ingestion_hmac_secret: str = ""
    ingestion_token: str = ""
    middleware_secret: str = ""
    middleware_secret_file: str = ""
    webhook_shared_secret: str = ""
    webhook_shared_secret_file: str = ""
    vicidial_callback_hmac_secret_file: str = ""
    signature_ttl_seconds: int = 300
    request_max_bytes: int = 262144
    database_pool_size: int = 8
    database_max_overflow: int = 4
    database_pool_timeout_seconds: int = 5
    enabled_event_types: str = (
        "vicidial.call.started,vicidial.call.connected,vicidial.call.ended"
    )
    allowed_client_instances: str = "vicidial-server-b"
    live_writes_enabled: bool = False
    allow_non_test_campaigns: bool = False
    odoo_delivery_enabled: bool = False
    n8n_delivery_enabled: bool = False
    n8n_event_delivery_enabled: bool = False
    n8n_production_workflows_enabled: bool = False
    automation_actions_enabled: bool = False
    odoo_automation_writes_enabled: bool = False
    vicidial_read_enabled: bool = False
    vicidial_write_enabled: bool = False
    transfer_control_enabled: bool = False
    vicidial_authorization_url: str = ""
    vicidial_edge_url: str = ""
    vicidial_ca_file: str = ""
    vicidial_client_cert_file: str = ""
    vicidial_client_key_file: str = ""
    vicidial_crl_file: str = ""
    callback_dispatch_enabled: bool = False
    messaging_enabled: bool = False
    send_events: bool = False
    broad_event_delivery_enabled: bool = False
    production_n8n_enabled: bool = False
    enable_external_delivery: bool = False
    controlled_broad_event_activation: bool = False
    broad_event_business_unit_allowlist: str = ""
    broad_event_campaign_allowlist: str = ""
    broad_event_workflow_allowlist: str = ""
    broad_event_type_allowlist: str = ""
    broad_event_activation_high_water_mark: str = ""
    broad_event_submission_limit: int = 0
    n8n_production_target_url: str = ""
    n8n_production_target_identity: str = ""
    n8n_production_image_digest: str = ""
    n8n_production_instance_id: str = ""
    n8n_production_version: str = ""
    n8n_runtime_health_url: str = ""
    webphone_origin_scheme: str = "https"
    webphone_origin_host: str = "phone.codestra.agency"
    webphone_expected_user: str = "preprod"
    webphone_staging_campaign: str = "TRANSFER_TEST"
    webphone_staging_endpoint: str = "6197"
    n8n_workflow_package_sha256: str = ""
    n8n_target_ca_file: str = ""
    n8n_service_issuer: str = ""
    n8n_service_audience: str = "codestra-middleware"
    n8n_service_jwks_url: str = ""
    n8n_service_client_id: str = "codestra-n8n-production"
    middleware_n8n_token_url: str = ""
    middleware_n8n_client_id: str = "codestra-middleware-production"
    middleware_n8n_client_secret_file: str = ""
    middleware_n8n_audience: str = "codestra-n8n-production"
    middleware_n8n_scope: str = "n8n.events.submit"
    odoo_results_client_id: str = "codestra-middleware-odoo-results"
    odoo_service_credential_reference: str = ""
    odoo_service_private_key_file: str = ""
    odoo_result_delivery_enabled: bool = False
    email_dispatch_enabled: bool = False
    sms_dispatch_enabled: bool = False
    allow_live_email: bool = False
    allow_live_sms: bool = False
    ai_enrichment_enabled: bool = False
    report_delivery_enabled: bool = False
    outbox_worker_enabled: bool = False
    outbox_max_attempts: int = 5
    outbox_base_delay_seconds: int = 5
    outbox_max_delay_seconds: int = 300
    outbox_lease_seconds: int = 60
    odoo_concurrency: int = 4
    n8n_concurrency: int = 8
    recording_concurrency: int = 2
    reconciliation_concurrency: int = 1
    keycloak_issuer: str = ""
    keycloak_audience: str = ""
    keycloak_jwks_url: str = ""
    keycloak_authorized_parties: str = ""
    keycloak_userinfo_url: str = ""
    provisioning_service_url: str = ""
    provisioning_service_token_url: str = ""
    provisioning_service_client_id: str = ""
    provisioning_service_client_secret_file: str = ""
    provisioning_service_ca_file: str = ""
    odoo_identity_lookup_url: str = ""
    odoo_identity_lookup_hmac_file: str = ""
    maintenance_interval_seconds: int = 30
    automation_allowed_campaigns: str = "TEST_SYN"
    automation_environment: str = "test"
    automation_hmac_secret: str = ""
    environment: str = "preproduction"
    publisher_hmac_keys_file: str = ""
    publisher_canary_enabled: bool = False
    quarantine_encryption_key_file: str = ""
    quarantine_encryption_key_version: str = "v1"
    quarantine_fingerprint_secret_file: str = ""
    quarantine_reviewer_secret_file: str = ""
    quarantine_retention_days: int = 90
    quarantine_retention_policy_version: str = "2026-07-26.1"
    quarantine_store_authenticated_raw: bool = True
    quarantine_rate_limit_per_minute: int = 30
    webphone_staging_provisioning_enabled: bool = False
    webphone_keycloak_enabled: bool = False
    webphone_endpoint_adapter_url: str = ""
    extension_allocator_enabled: bool = False
    telephony_provisioning_enabled: bool = False
    telephony_command_worker_enabled: bool = False
    telephony_service_client_id: str = "codestra-middleware-telephony"
    telephony_credential_directory: str = ""
    vicidial_provisioning_enabled: bool = False
    pjsip_provisioning_enabled: bool = False
    webphone_session_issuer_enabled: bool = False
    telephony_reconciliation_enabled: bool = False
    telephony_notifications_enabled: bool = False
    telephony_evidence_enabled: bool = False

    def validate_safety(self) -> None:
        broad_event_switches = (
            self.send_events,
            self.broad_event_delivery_enabled,
            self.production_n8n_enabled,
            self.n8n_production_workflows_enabled,
        )
        production_switches = (
            self.live_writes_enabled,
            self.allow_non_test_campaigns,
            self.vicidial_write_enabled,
            self.messaging_enabled,
            self.enable_external_delivery,
            self.email_dispatch_enabled,
            self.sms_dispatch_enabled,
            self.allow_live_email,
            self.allow_live_sms,
            self.outbox_worker_enabled,
            self.telephony_provisioning_enabled,
            self.telephony_command_worker_enabled,
            self.vicidial_provisioning_enabled,
            self.pjsip_provisioning_enabled,
        )
        if any(production_switches):
            raise ValueError("live writes and non-TEST_SYN campaigns are disabled")
        if any(broad_event_switches):
            if not all(broad_event_switches):
                raise ValueError("broad-event activation requires every canonical gate")
            required_scope = (
                self.broad_event_business_unit_allowlist,
                self.broad_event_campaign_allowlist,
                self.broad_event_workflow_allowlist,
                self.broad_event_type_allowlist,
                self.broad_event_activation_high_water_mark,
            )
            if (
                not self.controlled_broad_event_activation
                or not all(value.strip() for value in required_scope)
                or self.broad_event_submission_limit not in range(1, 26)
            ):
                raise ValueError(
                    "broad-event activation requires bounded explicit scope"
                )

    @property
    def broad_event_pipeline_enabled(self) -> bool:
        """Require every internal broad-event gate; external delivery is separate."""
        return all(
            (
                self.send_events,
                self.broad_event_delivery_enabled,
                self.production_n8n_enabled,
                self.n8n_production_workflows_enabled,
            )
        )

    def load_secret_files(self) -> None:
        """Load runtime secrets without placing their values in environment metadata."""
        mappings = (
            ("database_url", self.database_url_file),
            ("redis_url", self.redis_url_file),
            ("middleware_secret", self.middleware_secret_file),
            # Ingestion deliberately has no legacy shared-secret fallback.
            ("ingestion_hmac_secret", self.vicidial_callback_hmac_secret_file),
        )
        for attribute, filename in mappings:
            if filename:
                path = Path(filename)
                if not path.is_absolute() or not path.is_file():
                    raise ValueError(f"required {attribute} secret file is unavailable")
                value = path.read_text().strip()
                if not value:
                    raise ValueError(f"required {attribute} secret file is empty")
                setattr(self, attribute, value)

    def load_registry_snapshot_key(self) -> bytes:
        path = Path(self.registry_snapshot_signing_key_file)
        if not path.is_absolute() or not path.is_file():
            raise ValueError("registry snapshot signing key file is unavailable")
        value = path.read_bytes().strip()
        if len(value) < 32:
            raise ValueError("registry snapshot signing key is too short")
        return value

    @field_validator("vicidial_authorization_url", "vicidial_edge_url")
    @classmethod
    def validate_vicidial_private_url(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in VICIDIAL_PRIVATE_HOSTS
            or parsed.port != VICIDIAL_PRIVATE_PORT
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("VICIdial URL must use an approved private HTTPS endpoint")
        return value.rstrip("/")

    @field_validator("n8n_production_target_url")
    @classmethod
    def validate_n8n_production_target_url(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "n8n.internal.codestra.agency"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != "/webhook/codestra/v1/events"
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("n8n target must be the approved internal webhook")
        return value

    @field_validator("n8n_workflow_package_sha256")
    @classmethod
    def validate_workflow_package_sha256(cls, value: str) -> str:
        if value and not re.fullmatch(r"[0-9a-f]{64}", value):
            raise ValueError("workflow package identity must be an exact SHA-256")
        return value

    @field_validator("n8n_production_image_digest")
    @classmethod
    def validate_n8n_production_image_digest(cls, value: str) -> str:
        if value and not re.fullmatch(r"sha256:[0-9a-f]{64}", value):
            raise ValueError("n8n image identity must be an exact sha256 digest")
        return value

    @field_validator("webphone_endpoint_adapter_url")
    @classmethod
    def validate_webphone_endpoint_adapter_url(cls, value: str) -> str:
        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "authorization.internal.codestra.agency"
            or parsed.port != VICIDIAL_ENDPOINT_ADAPTER_PORT
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("webphone endpoint adapter must use private HTTPS")
        return value.rstrip("/")

    @field_validator(
        "vicidial_ca_file",
        "vicidial_client_cert_file",
        "vicidial_client_key_file",
        "vicidial_crl_file",
    )
    @classmethod
    def validate_vicidial_secret_path(cls, value: str) -> str:
        if not value:
            return value
        path = Path(value)
        if not path.is_absolute() or path.parent != VICIDIAL_SECRET_ROOT:
            raise ValueError(
                "VICIdial mTLS files must be direct children of the secret mount"
            )
        return value

    @property
    def vicidial_mtls_configured(self) -> bool:
        return all(
            (
                self.vicidial_authorization_url,
                self.vicidial_edge_url,
                self.vicidial_ca_file,
                self.vicidial_client_cert_file,
                self.vicidial_client_key_file,
            )
        )

    @property
    def allowed_campaigns(self) -> frozenset[str]:
        return frozenset(
            value.strip()
            for value in self.automation_allowed_campaigns.split(",")
            if value.strip()
        )

    @property
    def auth_ready(self) -> bool:
        return bool(self.middleware_secret and self.ingestion_hmac_secret)

    @property
    def webphone_identity_ready(self) -> bool:
        return all(
            (
                self.webphone_staging_provisioning_enabled,
                self.keycloak_issuer,
                self.keycloak_audience,
                self.keycloak_jwks_url,
                self.keycloak_authorized_parties,
                self.keycloak_userinfo_url,
                self.provisioning_service_url,
                self.provisioning_service_token_url,
                self.provisioning_service_client_id,
                self.provisioning_service_client_secret_file,
                self.provisioning_service_ca_file,
            )
        )

    @property
    def publisher_hmac_keys(self) -> dict[str, bytes]:
        if not self.publisher_hmac_keys_file:
            return {}
        path = Path(self.publisher_hmac_keys_file)
        if not path.is_absolute() or not path.is_file():
            raise ValueError("publisher key file unavailable")
        values = json.loads(path.read_text())
        if not isinstance(values, dict) or not values:
            raise ValueError("publisher key file invalid")
        return {
            key_id: base64.urlsafe_b64decode(value + "===")
            for key_id, value in values.items()
        }

    @staticmethod
    def _load_binary_secret(filename: str, label: str) -> bytes:
        path = Path(filename)
        if not filename or not path.is_absolute() or not path.is_file():
            raise ValueError(f"{label} file unavailable")
        try:
            value = base64.urlsafe_b64decode(path.read_text().strip() + "===")
        except (ValueError, TypeError) as exc:
            raise ValueError(f"{label} file invalid") from exc
        if len(value) < 32:
            raise ValueError(f"{label} must contain at least 256 bits")
        return value

    @property
    def quarantine_encryption_key(self) -> bytes:
        value = self._load_binary_secret(
            self.quarantine_encryption_key_file, "quarantine encryption key"
        )
        if len(value) != 32:
            raise ValueError("quarantine encryption key must be 256 bits")
        return value

    @property
    def quarantine_fingerprint_secret(self) -> bytes:
        return self._load_binary_secret(
            self.quarantine_fingerprint_secret_file,
            "quarantine fingerprint secret",
        )

    @property
    def quarantine_reviewer_secret(self) -> bytes:
        return self._load_binary_secret(
            self.quarantine_reviewer_secret_file,
            "quarantine reviewer authorization secret",
        )

    @property
    def enabled_events(self) -> frozenset[str]:
        return frozenset(
            x.strip() for x in self.enabled_event_types.split(",") if x.strip()
        )

    @property
    def ingestion_clients(self) -> frozenset[str]:
        return frozenset(
            x.strip() for x in self.allowed_client_instances.split(",") if x.strip()
        )


settings = Settings()
settings.load_secret_files()
if settings.database_url.startswith("postgresql://"):
    settings.database_url = settings.database_url.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
settings.validate_safety()
