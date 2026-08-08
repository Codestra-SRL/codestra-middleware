from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

import phonenumbers
from pydantic import BaseModel, ConfigDict, Field, field_validator

CANDIDATE_SCHEMA = "codestra.sales.lead-candidate.v1"
RESOLUTION_SCHEMA = "codestra.sales.lead-resolution.v1"
POLICY_VERSION = "sales-lead-v1.0"
ROLE_EMAILS = frozenset({"info", "sales", "support", "admin", "office", "contact"})
EXECUTABLE_SUFFIXES = (
    ".exe",
    ".msi",
    ".dmg",
    ".pkg",
    ".sh",
    ".bat",
    ".cmd",
    ".ps1",
    ".apk",
)
LEGAL_SUFFIXES = re.compile(
    r"\b(incorporated|inc|llc|ltd|limited|corp|corporation|gmbh|srl|sa)\b", re.I
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError("timestamp must be ISO-8601 UTC")
    return value


def safe_public_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use http or https")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("credentials in URL are prohibited")
    if parsed.path.lower().endswith(EXECUTABLE_SUFFIXES):
        raise ValueError("executable-download URL is prohibited")
    try:
        address = ipaddress.ip_address(parsed.hostname.strip("[]"))
    except ValueError:
        address = None
    if address and not address.is_global:
        raise ValueError("non-public URL destination is prohibited")
    if parsed.hostname.lower() == "localhost" or parsed.hostname.lower().endswith(
        (".local", ".internal")
    ):
        raise ValueError("internal URL destination is prohibited")
    return value


class Source(StrictModel):
    provider: str = Field(min_length=1, max_length=64)
    job_id: str = Field(min_length=1, max_length=128)
    request_id: str = Field(min_length=1, max_length=128)
    collected_at: datetime
    _utc = field_validator("collected_at")(utc_timestamp)


class Address(StrictModel):
    line1: str | None = Field(None, max_length=256)
    line2: str | None = Field(None, max_length=256)
    city: str | None = Field(None, max_length=128)
    region: str | None = Field(None, max_length=128)
    postal_code: str | None = Field(None, max_length=32)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")


class Company(StrictModel):
    name: str = Field(min_length=1, max_length=256)
    legal_name: str | None = Field(None, max_length=256)
    domain: str | None = Field(None, max_length=253)
    website_url: str | None = Field(None, max_length=2048)
    registration_number: str | None = Field(None, max_length=128)
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    industry: str | None = Field(None, max_length=128)
    address: Address = Field(
        default_factory=lambda: Address(
            line1=None,
            line2=None,
            city=None,
            region=None,
            postal_code=None,
            country_code=None,
        )
    )

    @field_validator("website_url")
    @classmethod
    def website_is_safe(cls, value: str | None) -> str | None:
        return safe_public_url(value) if value else value


class Contact(StrictModel):
    first_name: str | None = Field(None, max_length=128)
    last_name: str | None = Field(None, max_length=128)
    full_name: str | None = Field(None, max_length=256)
    title: str | None = Field(None, max_length=128)
    department: str | None = Field(None, max_length=128)
    business_email: str | None = Field(None, max_length=320)
    business_phone: str | None = Field(None, max_length=64)
    country_code: str | None = Field(None, pattern=r"^[A-Z]{2}$")

    @field_validator("business_email")
    @classmethod
    def valid_email(cls, value: str | None) -> str | None:
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("malformed business email")
        return value

    @field_validator("business_phone")
    @classmethod
    def valid_phone_shape(cls, value: str | None) -> str | None:
        if value and (
            not re.fullmatch(r"[+()0-9 .xXextEXT-]+", value)
            or len(re.sub(r"\D", "", value)) < 7
        ):
            raise ValueError("malformed business telephone")
        return value


class Evidence(StrictModel):
    field: str = Field(min_length=1, max_length=128)
    source_url: str = Field(max_length=2048)
    page_title: str | None = Field(None, max_length=256)
    snippet: str = Field(max_length=1000)
    content_hash: str = Field(pattern=r"^(?:sha256:)?[0-9a-f]{64}$")
    observed_at: datetime
    _safe_url = field_validator("source_url")(safe_public_url)
    _utc = field_validator("observed_at")(utc_timestamp)

    @field_validator("snippet")
    @classmethod
    def no_html(cls, value: str) -> str:
        if re.search(r"<\s*(?:html|script|body|iframe)\b", value, re.I):
            raise ValueError("raw HTML is prohibited")
        return value


class SourceClaims(StrictModel):
    consent_claimed: bool = False
    consent_source: str | None = Field(None, max_length=256)
    consent_timestamp: datetime | None = None
    _utc = field_validator("consent_timestamp")(
        lambda value: utc_timestamp(value) if value else value
    )


class LeadCandidate(StrictModel):
    schema_version: str
    tenant_id: str = Field(min_length=1, max_length=128)
    campaign_id: str = Field(min_length=1, max_length=128)
    source: Source
    company: Company
    contact: Contact = Field(
        default_factory=lambda: Contact(
            first_name=None,
            last_name=None,
            full_name=None,
            title=None,
            department=None,
            business_email=None,
            business_phone=None,
            country_code=None,
        )
    )
    evidence: list[Evidence] = Field(default_factory=list, max_length=25)
    source_claims: SourceClaims = Field(
        default_factory=lambda: SourceClaims(
            consent_claimed=False,
            consent_source=None,
            consent_timestamp=None,
        )
    )
    metadata: dict[str, str | int | bool | None] = Field(
        default_factory=dict, max_length=32
    )

    @field_validator("schema_version")
    @classmethod
    def correct_schema(cls, value: str) -> str:
        if value != CANDIDATE_SCHEMA:
            raise ValueError("unsupported schema version")
        return value


def comparison_text(value: str | None) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = LEGAL_SUFFIXES.sub(" ", value)
    return " ".join(re.sub(r"[^\w\s]", " ", value).split())


def normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value if "://" in value else f"//{value}")
    host = (parsed.hostname or "").rstrip(".").lower()
    if host.startswith("www."):
        host = host[4:]
    try:
        return host.encode("idna").decode("ascii") or None
    except UnicodeError as exc:
        raise ValueError("invalid international domain") from exc


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    local, domain = value.rsplit("@", 1)
    normalized_domain = normalize_domain(domain)
    return f"{local}@{normalized_domain}"


def normalize_phone(
    value: str | None, country_code: str | None
) -> tuple[str | None, str | None]:
    if not value:
        return None, None
    extension_match = re.search(r"(?:ext\.?|x)\s*(\d+)$", value, re.I)
    extension = extension_match.group(1) if extension_match else None
    core = value[: extension_match.start()] if extension_match else value
    if not core.strip().startswith("+") and not country_code:
        raise ValueError("ambiguous telephone; country context is required")
    try:
        parsed = phonenumbers.parse(core, country_code)
    except phonenumbers.NumberParseException as exc:
        raise ValueError("invalid telephone") from exc
    if not phonenumbers.is_valid_number(parsed):
        raise ValueError("ambiguous or invalid telephone")
    return phonenumbers.format_number(
        parsed, phonenumbers.PhoneNumberFormat.E164
    ), extension


class Decision(StrEnum):
    NET_NEW = "NET_NEW"
    EXACT_EXISTING = "EXACT_EXISTING"
    POSSIBLE_DUPLICATE = "POSSIBLE_DUPLICATE"
    BLOCKED = "BLOCKED"
    REJECTED = "REJECTED"
    CONFLICT = "CONFLICT"


@dataclass(frozen=True)
class OdooRecord:
    tenant_id: str
    company_id: str | None = None
    lead_id: str | None = None
    registration_number: str | None = None
    jurisdiction: str | None = None
    domain: str | None = None
    company_name: str | None = None
    city: str | None = None
    region: str | None = None
    email: str | None = None
    phone: str | None = None
    full_name: str | None = None
    campaign_id: str | None = None
    global_dnc: bool = False
    campaign_dnc: bool = False
    suppressed: bool = False
    consent: str = "UNKNOWN"


class OdooUnavailable(RuntimeError):
    pass


class OdooReadOnlyPort(Protocol):
    create_count: int
    update_count: int
    delete_count: int

    def lookup(
        self, tenant_id: str, candidate: LeadCandidate, *, limit: int = 100
    ) -> list[OdooRecord]: ...


class FakeOdooReadOnly:
    def __init__(
        self, records: list[OdooRecord] | None = None, unavailable: bool = False
    ):
        self.records = records or []
        self.unavailable = unavailable
        self.create_count = self.update_count = self.delete_count = 0

    def lookup(
        self, tenant_id: str, candidate: LeadCandidate, *, limit: int = 100
    ) -> list[OdooRecord]:
        if self.unavailable:
            raise OdooUnavailable("authoritative lookup unavailable")
        if limit < 1 or limit > 100:
            raise ValueError("unbounded Odoo lookup")
        return [
            record
            for record in self.records
            if hmac.compare_digest(record.tenant_id, tenant_id)
        ][:limit]


@dataclass
class Match:
    matched: bool = False
    record_id: str | None = None
    score: int = 0
    reasons: list[str] = field(default_factory=list)


def match_candidate(
    candidate: LeadCandidate, records: list[OdooRecord]
) -> tuple[Match, Match]:
    best_company, best_contact = Match(), Match()
    candidate_domain = normalize_domain(
        candidate.company.domain or candidate.company.website_url
    )
    candidate_email = normalize_email(candidate.contact.business_email)
    candidate_phone, _ = (
        normalize_phone(
            candidate.contact.business_phone,
            candidate.contact.country_code or candidate.company.country_code,
        )
        if candidate.contact.business_phone
        else (None, None)
    )
    for record in records:
        score, reasons = 0, []
        if (
            candidate.company.registration_number
            and record.registration_number == candidate.company.registration_number
            and record.jurisdiction == candidate.company.country_code
        ):
            score, reasons = 100, ["COMPANY_REGISTRATION_JURISDICTION_EXACT"]
        elif candidate_domain and normalize_domain(record.domain) == candidate_domain:
            score, reasons = 95, ["COMPANY_ROOT_DOMAIN_EXACT"]
        elif (
            comparison_text(record.company_name)
            == comparison_text(candidate.company.legal_name or candidate.company.name)
            and record.city
            and comparison_text(record.city)
            == comparison_text(candidate.company.address.city)
            and record.jurisdiction == candidate.company.country_code
        ):
            score, reasons = 85, ["COMPANY_NAME_LOCATION_STRONG"]
        elif comparison_text(record.company_name) == comparison_text(
            candidate.company.name
        ):
            score, reasons = 70, ["COMPANY_NAME_ONLY_REVIEW"]
        if score > best_company.score:
            best_company = Match(score >= 90, record.company_id, score, reasons)

        contact_score, contact_reasons = 0, []
        if (
            candidate_email
            and normalize_email(record.email) == candidate_email
            and candidate_email.split("@", 1)[0].casefold() not in ROLE_EMAILS
        ):
            contact_score, contact_reasons = 100, ["CONTACT_BUSINESS_EMAIL_EXACT"]
        elif (
            candidate_phone
            and record.phone == candidate_phone
            and record.company_id
            and record.company_id == best_company.record_id
        ):
            contact_score, contact_reasons = 95, ["CONTACT_E164_COMPANY_EXACT"]
        elif (
            comparison_text(record.full_name)
            and comparison_text(record.full_name)
            == comparison_text(candidate.contact.full_name)
            and score >= 70
        ):
            contact_score, contact_reasons = 80, ["CONTACT_NAME_COMPANY_REVIEW"]
        if contact_score > best_contact.score:
            best_contact = Match(
                contact_score >= 90, record.lead_id, contact_score, contact_reasons
            )
    return best_company, best_contact


class ComplianceEngine:
    def evaluate(
        self, candidate: LeadCandidate, records: list[OdooRecord]
    ) -> tuple[dict[str, str], list[str]]:
        gates = {
            "global_dnc": "ELIGIBLE",
            "campaign_dnc": "ELIGIBLE",
            "suppression": "ELIGIBLE",
            "consent": "REVIEW_CONSENT_UNKNOWN",
            "channel_eligibility": "REVIEW_REQUIRED",
        }
        reasons: list[str] = []
        for record in records:
            if record.global_dnc:
                gates["global_dnc"] = "BLOCKED_GLOBAL_DNC"
                reasons.append("GLOBAL_DNC_BLOCK")
            if record.suppressed:
                gates["suppression"] = "BLOCKED_INTERNAL_SUPPRESSION"
                reasons.append("INTERNAL_SUPPRESSION_BLOCK")
            if record.campaign_dnc and record.campaign_id == candidate.campaign_id:
                gates["campaign_dnc"] = "BLOCKED_CAMPAIGN_DNC"
                reasons.append("CAMPAIGN_DNC_BLOCK")
            if record.consent == "WITHDRAWN":
                gates["consent"] = "BLOCKED_CONSENT_WITHDRAWN"
                reasons.append("CONSENT_WITHDRAWN_BLOCK")
            elif record.consent == "GRANTED":
                gates["consent"] = "ELIGIBLE"
        return gates, reasons


class IdempotencyConflict(RuntimeError):
    pass


@dataclass
class VerificationJob:
    job_id: str
    tenant_id: str
    state: str = "COMPLETED"
    total: int = 0
    processed: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)


class SalesLeadService:
    def __init__(self, odoo: OdooReadOnlyPort | None = None):
        self.odoo = odoo or FakeOdooReadOnly()
        self.idempotency: dict[tuple[str, str, str], tuple[str, dict[str, Any]]] = {}
        self.nonces: set[tuple[str, str]] = set()
        self.reviews: list[dict[str, Any]] = []
        self.audit: list[dict[str, Any]] = []
        self.jobs: dict[str, VerificationJob] = {}
        self._lock = threading.Lock()

    @staticmethod
    def payload_hash(candidate: LeadCandidate) -> str:
        canonical = json.dumps(
            candidate.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return hashlib.sha256(canonical.encode()).hexdigest()

    def resolve(self, candidate: LeadCandidate, idempotency_key: str) -> dict[str, Any]:
        if not 8 <= len(idempotency_key) <= 255:
            raise ValueError("invalid idempotency key")
        digest = self.payload_hash(candidate)
        scope = (candidate.tenant_id, "lead-candidate.resolve", idempotency_key)
        with self._lock:
            prior = self.idempotency.get(scope)
            if prior:
                if prior[0] != digest:
                    raise IdempotencyConflict("IDEMPOTENCY_PAYLOAD_CONFLICT")
                self._audit(
                    "idempotent_replay.returned",
                    candidate,
                    prior[1]["correlation_id"],
                    ["IDEMPOTENT_REPLAY"],
                )
                return prior[1]
            correlation_id = str(uuid4())
            try:
                records = self.odoo.lookup(candidate.tenant_id, candidate, limit=100)
            except OdooUnavailable:
                result = self._response(
                    candidate,
                    correlation_id,
                    Decision.BLOCKED,
                    Match(),
                    Match(),
                    {
                        "global_dnc": "DEPENDENCY_UNAVAILABLE",
                        "campaign_dnc": "DEPENDENCY_UNAVAILABLE",
                        "suppression": "DEPENDENCY_UNAVAILABLE",
                        "consent": "DEPENDENCY_UNAVAILABLE",
                        "channel_eligibility": "DEPENDENCY_UNAVAILABLE",
                    },
                    ["ODOO_DEPENDENCY_UNAVAILABLE"],
                    True,
                )
            else:
                company, contact = match_candidate(candidate, records)
                gates, blocked = ComplianceEngine().evaluate(candidate, records)
                review = (
                    (70 <= company.score < 90)
                    or (70 <= contact.score < 90)
                    or gates["consent"] == "REVIEW_CONSENT_UNKNOWN"
                )
                if blocked:
                    decision = Decision.BLOCKED
                elif company.matched or contact.matched:
                    decision = Decision.EXACT_EXISTING
                elif company.score >= 70 or contact.score >= 70:
                    decision = Decision.POSSIBLE_DUPLICATE
                else:
                    decision = Decision.NET_NEW
                reasons = blocked or (
                    ["POSSIBLE_DUPLICATE_REVIEW"]
                    if decision == Decision.POSSIBLE_DUPLICATE
                    else ["DETERMINISTIC_RESOLUTION_COMPLETE"]
                )
                result = self._response(
                    candidate,
                    correlation_id,
                    decision,
                    company,
                    contact,
                    gates,
                    reasons,
                    review,
                )
                if decision == Decision.POSSIBLE_DUPLICATE:
                    self.reviews.append(
                        {
                            "tenant_id": candidate.tenant_id,
                            "campaign_id": candidate.campaign_id,
                            "candidate_id": result["candidate_id"],
                            "odoo_company_id": company.record_id,
                            "odoo_lead_id": contact.record_id,
                            "company_score": company.score,
                            "contact_score": contact.score,
                            "reason_codes": reasons,
                            "evidence_hashes": [
                                item.content_hash for item in candidate.evidence
                            ],
                            "policy_version": POLICY_VERSION,
                            "created_at": datetime.now(UTC).isoformat(),
                            "state": "PENDING",
                            "reviewer_identity": None,
                            "reviewed_at": None,
                        }
                    )
            self.idempotency[scope] = (digest, result)
            self._audit(
                "identity_resolution.completed",
                candidate,
                correlation_id,
                result["rejection_reasons"],
            )
            return result

    def create_job(self, body: dict[str, Any], idempotency_key: str) -> VerificationJob:
        if (
            body.get("source") != "odoo"
            or body.get("dry_run") is not True
            or body.get("write_changes") is not False
            or body.get("publish_to_vicidial") is not False
        ):
            raise ValueError("PHASE1_DRY_RUN_REQUIRED")
        batch = body.get("batch_size", 100)
        if not isinstance(batch, int) or not 1 <= batch <= 100:
            raise ValueError("BATCH_SIZE_OUT_OF_RANGE")
        tenant = body.get("tenant_id")
        if not isinstance(tenant, str) or not tenant:
            raise ValueError("TENANT_REQUIRED")
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        scope = (tenant, "verification-job.create", idempotency_key)
        with self._lock:
            prior = self.idempotency.get(scope)
            if prior:
                if prior[0] != digest:
                    raise IdempotencyConflict("IDEMPOTENCY_PAYLOAD_CONFLICT")
                return self.jobs[prior[1]["job_id"]]
            job = VerificationJob(str(uuid4()), tenant)
            self.jobs[job.job_id] = job
            self.idempotency[scope] = (digest, {"job_id": job.job_id})
            return job

    def accept_scraper(
        self, candidate: LeadCandidate, idempotency_key: str
    ) -> dict[str, Any]:
        if not 8 <= len(idempotency_key) <= 255:
            raise ValueError("invalid idempotency key")
        digest = self.payload_hash(candidate)
        scope = (candidate.tenant_id, "scraper-result.ingest", idempotency_key)
        with self._lock:
            prior = self.idempotency.get(scope)
            if prior:
                if prior[0] != digest:
                    raise IdempotencyConflict("IDEMPOTENCY_PAYLOAD_CONFLICT")
                return prior[1]
            result: dict[str, Any] = {
                "accepted": True,
                "dry_run": True,
                "candidate_id": str(uuid4()),
                "request_id": candidate.source.request_id,
                "correlation_id": str(uuid4()),
            }
            self.idempotency[scope] = (digest, result)
            self._audit(
                "scraper_webhook.accepted",
                candidate,
                result["correlation_id"],
                ["SCRAPER_RESULT_ACCEPTED"],
            )
            return result

    def _audit(
        self,
        event: str,
        candidate: LeadCandidate,
        correlation_id: str,
        reasons: list[str],
    ) -> None:
        self.audit.append(
            {
                "event": event,
                "tenant_id": candidate.tenant_id,
                "actor": candidate.source.provider,
                "correlation_id": correlation_id,
                "candidate_request_id": candidate.source.request_id,
                "reason_codes": reasons,
                "policy_version": POLICY_VERSION,
                "timestamp": datetime.now(UTC).isoformat(),
                "payload_hash": self.payload_hash(candidate),
                "source_provider": candidate.source.provider,
            }
        )

    @staticmethod
    def _response(
        candidate: LeadCandidate,
        correlation: str,
        decision: Decision,
        company: Match,
        contact: Match,
        gates: dict[str, str],
        reasons: list[str],
        review: bool,
    ) -> dict[str, Any]:
        return {
            "schema_version": RESOLUTION_SCHEMA,
            "candidate_id": str(uuid4()),
            "decision": decision.value,
            "company_resolution": {
                "matched": company.matched,
                "odoo_company_id": company.record_id,
                "score": company.score,
                "reasons": company.reasons,
            },
            "contact_resolution": {
                "matched": contact.matched,
                "odoo_lead_id": contact.record_id,
                "score": contact.score,
                "reasons": contact.reasons,
            },
            "gates": gates,
            "rejection_reasons": reasons,
            "review_required": review,
            "dry_run": True,
            "correlation_id": correlation,
            "policy_version": POLICY_VERSION,
        }


class ProviderResult(StrictModel):
    provider: str
    status: str
    confidence: int | None = Field(None, ge=0, le=100)
    evidence_sources: list[str] = Field(default_factory=list, max_length=25)
    data: dict[str, str | int | bool | None] = Field(
        default_factory=dict, max_length=32
    )


class DisabledProvider:
    """Provider-neutral, no-call Phase 1 adapter with bounded operational metadata."""

    enabled = False
    timeout_seconds = 10
    max_retries = 2
    rate_limit_per_minute = 30
    circuit_breaker_threshold = 5
    usage_count = 0
    cost_micro_usd = 0

    def execute(
        self,
        *,
        tenant_id: str,
        campaign_id: str,
        operation: str,
        payload: dict[str, Any],
    ) -> ProviderResult:
        del tenant_id, campaign_id, operation, payload
        return ProviderResult(
            provider=self.__class__.__name__,
            status="DEPENDENCY_UNAVAILABLE",
            confidence=None,
        )


class HunterAdapter(DisabledProvider):
    pass


class ApolloAdapter(DisabledProvider):
    pass


class TwilioLookupAdapter(DisabledProvider):
    pass


class OpenCorporatesAdapter(DisabledProvider):
    pass


class OpenAIClassificationAdapter(DisabledProvider):
    """Non-authoritative classification only; never used by matching or compliance."""


def sign_scraper(
    body: bytes,
    secret: bytes,
    *,
    identity: str,
    tenant: str,
    campaign: str,
    request_id: str,
    timestamp: str,
    nonce: str,
) -> str:
    digest = hashlib.sha256(body).hexdigest()
    material = "\n".join(
        ("HMAC-V1", identity, tenant, campaign, request_id, timestamp, nonce, digest)
    ).encode()
    return hmac.new(secret, material, hashlib.sha256).hexdigest()


def verify_scraper(
    body: bytes,
    headers: dict[str, str],
    secret: bytes,
    expected_identity: str,
    nonces: set[tuple[str, str]],
    now: datetime | None = None,
) -> None:
    required = (
        "X-Scraper-Identity",
        "X-Tenant-ID",
        "X-Campaign-ID",
        "X-Request-ID",
        "X-Codestra-Timestamp",
        "X-Codestra-Nonce",
        "X-Content-SHA256",
        "X-Signature-Version",
        "X-Codestra-Signature",
    )
    if any(not headers.get(key) for key in required):
        raise PermissionError("MISSING_SIGNATURE")
    if headers["X-Signature-Version"] != "HMAC-V1" or not hmac.compare_digest(
        headers["X-Scraper-Identity"], expected_identity
    ):
        raise PermissionError("UNKNOWN_SCRAPER_IDENTITY")
    digest = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(digest, headers["X-Content-SHA256"]):
        raise PermissionError("MODIFIED_PAYLOAD")
    try:
        occurred = datetime.fromisoformat(headers["X-Codestra-Timestamp"])
    except ValueError as exc:
        raise PermissionError("EXPIRED_TIMESTAMP") from exc
    now = now or datetime.now(UTC)
    if (
        occurred.tzinfo is None
        or abs((now - occurred.astimezone(UTC)).total_seconds()) > 300
    ):
        raise PermissionError("EXPIRED_TIMESTAMP")
    nonce_key = (headers["X-Scraper-Identity"], headers["X-Codestra-Nonce"])
    if nonce_key in nonces:
        raise PermissionError("REPLAYED_NONCE")
    expected = sign_scraper(
        body,
        secret,
        identity=headers["X-Scraper-Identity"],
        tenant=headers["X-Tenant-ID"],
        campaign=headers["X-Campaign-ID"],
        request_id=headers["X-Request-ID"],
        timestamp=headers["X-Codestra-Timestamp"],
        nonce=headers["X-Codestra-Nonce"],
    )
    if not hmac.compare_digest(expected, headers["X-Codestra-Signature"]):
        raise PermissionError("INVALID_SIGNATURE")
    nonces.add(nonce_key)
