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
VICIDIAL_SECRET_ROOT = Path("/run/secrets/vicidial-mtls")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")
    database_url: str = "postgresql+asyncpg://localhost/codestra_middleware"
    redis_url: str = "redis://localhost:6379/2"
    ingestion_hmac_secret: str = ""
    ingestion_token: str = ""
    middleware_secret: str = ""
    webhook_shared_secret: str = ""
    signature_ttl_seconds: int = 300
    request_max_bytes: int = 262144
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
    ai_enrichment_enabled: bool = False
    report_delivery_enabled: bool = False
    outbox_worker_enabled: bool = False
    outbox_max_attempts: int = 5
    outbox_base_delay_seconds: int = 5
    outbox_max_delay_seconds: int = 300
    outbox_lease_seconds: int = 60
    maintenance_interval_seconds: int = 30
    automation_allowed_campaigns: str = "TEST_SYN"
    automation_environment: str = "test"
    automation_hmac_secret: str = ""
    environment: str = "preproduction"

    def validate_safety(self) -> None:
        production_switches = (
            self.live_writes_enabled,
            self.allow_non_test_campaigns,
            self.n8n_production_workflows_enabled,
            self.vicidial_write_enabled,
            self.messaging_enabled,
            self.outbox_worker_enabled,
        )
        if any(production_switches):
            raise ValueError("live writes and non-TEST_SYN campaigns are disabled")

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
            raise ValueError("VICIdial mTLS files must be direct children of the secret mount")
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
        return bool(self.middleware_secret and self.webhook_shared_secret)


settings = Settings()
if settings.database_url.startswith("postgresql://"):
    settings.database_url = settings.database_url.replace(
        "postgresql://", "postgresql+asyncpg://", 1
    )
settings.validate_safety()
