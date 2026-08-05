from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import (
    INT4RANGE,
    JSONB,
    ExcludeConstraint,
)
from sqlalchemy.dialects.postgresql import (
    UUID as PGUUID,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class TelephonyCommandJournal(Base):
    __tablename__ = "telephony_command_journal"
    command_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    command_public_id: Mapped[str] = mapped_column(
        String(144), nullable=False, unique=True, default=lambda: f"CMD-{uuid4().hex}"
    )
    command_type: Mapped[str] = mapped_column(String(96), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_public_id: Mapped[str] = mapped_column(String(144), nullable=False)
    aggregate_version: Mapped[int] = mapped_column(Integer, nullable=False)
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    business_unit_public_id: Mapped[str] = mapped_column(String(144), nullable=False)
    campaign_public_id: Mapped[str] = mapped_column(String(144), nullable=False)
    idempotency_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    causation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_decision_id: Mapped[str] = mapped_column(String(144), nullable=False)
    policy_decision_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    request_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (
        CheckConstraint("aggregate_version >= 1", name="ck_telephony_command_version"),
        CheckConstraint(
            "environment IN ('staging','test','production')",
            name="ck_telephony_command_environment",
        ),
        UniqueConstraint(
            "environment",
            "aggregate_type",
            "aggregate_public_id",
            "aggregate_version",
            name="uq_telephony_command_aggregate_version",
        ),
        Index(
            "ix_telephony_command_aggregate",
            "aggregate_type",
            "aggregate_public_id",
            "aggregate_version",
        ),
        Index("ix_telephony_command_correlation", "correlation_id"),
    )


class TelephonyOperationJournal(Base):
    __tablename__ = "telephony_operation_journal"
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    operation_public_id: Mapped[str] = mapped_column(
        String(144), nullable=False, unique=True, default=lambda: f"OPR-{uuid4().hex}"
    )
    command_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("telephony_command_journal.command_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter_service_key: Mapped[str] = mapped_column(
        String(144), nullable=False, default="telephony-adapter"
    )
    adapter_operation_id: Mapped[str] = mapped_column(
        String(144), nullable=False, default=""
    )
    target_system: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    target_resource_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default=""
    )
    target_public_id: Mapped[str] = mapped_column(
        String(144), nullable=False, default=""
    )
    desired_state_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1
    )
    idempotency_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, default=lambda: uuid4().hex
    )
    transition_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    endpoint_key: Mapped[str] = mapped_column(String(96), nullable=False)
    readback_endpoint_key: Mapped[str] = mapped_column(String(96), nullable=False)
    target_configuration_checksum: Mapped[str] = mapped_column(
        String(71), nullable=False
    )
    target_attested: Mapped[bool] = mapped_column(Boolean, nullable=False)
    desired_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    actual_hash: Mapped[str | None] = mapped_column(String(64))
    readback_matches: Mapped[bool | None] = mapped_column(Boolean)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    response_json: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint(
            "(readback_matches IS NOT TRUE) OR (actual_hash IS NOT NULL)",
            name="ck_telephony_operation_readback_hash",
        ),
        Index("ix_telephony_operation_correlation", "correlation_id"),
    )


class TelephonyOperationTransition(Base):
    __tablename__ = "telephony_operation_transition"
    transition_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("telephony_operation_journal.operation_id", ondelete="RESTRICT"),
        nullable=False,
    )
    command_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("telephony_command_journal.command_id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    from_state: Mapped[str] = mapped_column(String(32), nullable=False)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    transition_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    binding_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "operation_id", "sequence", name="uq_telephony_transition_sequence"
        ),
        UniqueConstraint(
            "operation_id",
            "transition_hash",
            name="uq_telephony_transition_hash",
        ),
    )


class TelephonyTerminalResult(Base):
    __tablename__ = "telephony_terminal_result"
    result_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    result_public_id: Mapped[str] = mapped_column(
        String(144), nullable=False, unique=True, default=lambda: f"RES-{uuid4().hex}"
    )
    operation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("telephony_operation_journal.operation_id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    command_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("telephony_command_journal.command_id", ondelete="RESTRICT"),
        nullable=False,
    )
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    application_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    readback_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    target_system: Mapped[str] = mapped_column(String(32), nullable=False)
    target_resource_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_public_id: Mapped[str] = mapped_column(String(144), nullable=False)
    requested_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    applied_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    observed_state_version: Mapped[int] = mapped_column(Integer, nullable=False)
    application_status: Mapped[str] = mapped_column(String(32), nullable=False)
    readback_status: Mapped[str] = mapped_column(String(32), nullable=False)
    adapter_service_key: Mapped[str] = mapped_column(String(144), nullable=False)
    adapter_configuration_checksum: Mapped[str] = mapped_column(
        String(71), nullable=False
    )
    safe_summary: Mapped[str] = mapped_column(String(512), nullable=False)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    readback_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    odoo_callback_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING"
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reconciliation_status: Mapped[str] = mapped_column(String(32), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    immutable_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "result_hash", "operation_id", name="uq_telephony_result_binding"
        ),
        Index("ix_telephony_result_correlation", "correlation_id"),
    )


class TelephonyReconciliationRun(Base):
    __tablename__ = "telephony_reconciliation_run"
    run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    run_public_id: Mapped[str] = mapped_column(
        String(144), nullable=False, unique=True, default=lambda: f"REC-{uuid4().hex}"
    )
    command_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("telephony_command_journal.command_id", ondelete="RESTRICT"),
    )
    environment: Mapped[str] = mapped_column(String(16), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_public_id: Mapped[str] = mapped_column(String(144), nullable=False)
    target_system: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    classification: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    evidence_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        Index("ix_telephony_reconciliation_correlation", "correlation_id"),
    )


class IntegrationEvent(Base):
    __tablename__ = "integration_event"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[str] = mapped_column(
        String(16), nullable=False, default="1.0"
    )
    original_event_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    entity_key: Mapped[str | None] = mapped_column(String(256))
    source_system: Mapped[str] = mapped_column(
        String(50), nullable=False, default="vicidial"
    )
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (Index("ix_integration_event_payload_hash", "payload_hash"),)


class IntegrationDelivery(Base):
    __tablename__ = "integration_delivery"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("integration_event.id", ondelete="CASCADE"),
        nullable=False,
    )
    target: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="disabled")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[str | None] = mapped_column(String(128))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    result_json: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("event_id", "target", name="uq_delivery_event_target"),
    )


class BroadEventDelivery(Base):
    __tablename__ = "broad_event_delivery"
    delivery_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("integration_event.id"), nullable=False
    )
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(128), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    target_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    target_environment: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RESERVED")
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    response_received_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_class: Mapped[str | None] = mapped_column(String(64))
    response_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "workflow_id",
            "workflow_version",
            "idempotency_key",
            name="uq_broad_event_delivery_scope",
        ),
    )


class N8nTargetAttestation(Base):
    __tablename__ = "n8n_target_attestation"
    attestation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    target_identity: Mapped[str] = mapped_column(String(128), nullable=False)
    target_environment: Mapped[str] = mapped_column(String(32), nullable=False)
    canonical_host: Mapped[str] = mapped_column(String(255), nullable=False)
    image_digest: Mapped[str] = mapped_column(String(71), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    workflow_package_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    request_nonce: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    result: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class N8nExecutionRegistration(Base):
    __tablename__ = "n8n_execution_registration"
    execution_registration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    registration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True
    )
    delivery_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("broad_event_delivery.delivery_id"),
        unique=True,
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(128), nullable=False)
    execution_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(24), nullable=False, default="REGISTERED"
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    response_hash: Mapped[str] = mapped_column(String(64), nullable=False)


class N8nExecutionTransition(Base):
    __tablename__ = "n8n_execution_transition"
    transition_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    registration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("n8n_execution_registration.registration_id"),
        nullable=False,
    )
    from_status: Mapped[str] = mapped_column(String(24), nullable=False)
    to_status: Mapped[str] = mapped_column(String(24), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    persisted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "registration_id",
            "to_status",
            name="uq_n8n_transition_registration_status",
        ),
    )


class N8nAcknowledgement(Base):
    __tablename__ = "n8n_acknowledgement"
    acknowledgement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True
    )
    registration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("n8n_execution_registration.registration_id"),
        nullable=False,
    )
    delivery_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("broad_event_delivery.delivery_id"),
        unique=True,
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_id: Mapped[str] = mapped_column(String(128), nullable=False)
    workflow_version: Mapped[str] = mapped_column(String(128), nullable=False)
    execution_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    execution_status: Mapped[str] = mapped_column(String(24), nullable=False)
    result_classification: Mapped[str] = mapped_column(String(64), nullable=False)
    result_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    persisted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OdooResultDelivery(Base):
    __tablename__ = "odoo_result_delivery"
    result_delivery_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    acknowledgement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("n8n_acknowledgement.acknowledgement_id"),
        nullable=False,
        unique=True,
    )
    result_public_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), nullable=False, unique=True, default=uuid4
    )
    originating_outbox_public_id: Mapped[str] = mapped_column(
        String(128), nullable=False
    )
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reserved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    odoo_result_inbox_id: Mapped[str | None] = mapped_column(String(64))
    response_hash: Mapped[str | None] = mapped_column(String(64))
    last_error_class: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_record"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    scope: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    event_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("integration_event.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("scope", "key_hash", name="uq_idempotency_scope_key"),
    )


class PublisherNonce(Base):
    __tablename__ = "publisher_nonce"
    key_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    nonce: Mapped[str] = mapped_column(String(128), primary_key=True)
    signed_at: Mapped[int] = mapped_column(BigInteger, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class PublisherAcknowledgement(Base):
    __tablename__ = "publisher_acknowledgement"
    acknowledgement_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    event_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False)
    retryable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    acknowledgement: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SecurityRejection(Base):
    __tablename__ = "security_rejection"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    claimed_publisher: Mapped[str | None] = mapped_column(String(128))
    authentication_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="UNVERIFIED"
    )
    key_id: Mapped[str | None] = mapped_column(String(64))
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ip_classification: Mapped[str] = mapped_column(String(16), nullable=False)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint(
            "authentication_state = 'UNVERIFIED'",
            name="ck_security_rejection_unverified",
        ),
    )


class InvalidEventQuarantine(Base):
    __tablename__ = "invalid_event_quarantine"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    server_correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    client_correlation_id: Mapped[str | None] = mapped_column(String(128))
    claimed_source: Mapped[str | None] = mapped_column(String(64))
    claimed_publisher_identity: Mapped[str | None] = mapped_column(String(128))
    authenticated_publisher_id: Mapped[str] = mapped_column(String(128), nullable=False)
    authentication_state: Mapped[str] = mapped_column(String(24), nullable=False)
    authentication_key_id: Mapped[str | None] = mapped_column(String(64))
    original_signature_verification: Mapped[str] = mapped_column(
        String(24), nullable=False
    )
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_payload: Mapped[bytes | None] = mapped_column(LargeBinary)
    encryption_nonce: Mapped[bytes | None] = mapped_column(LargeBinary)
    encryption_key_version: Mapped[str | None] = mapped_column(String(32))
    sanitized_preview: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    business_unit: Mapped[str | None] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="PENDING_REVIEW"
    )
    review_owner: Mapped[str | None] = mapped_column(String(128))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[str | None] = mapped_column(String(128))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replayed_event_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("integration_event.id")
    )
    replay_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    retention_policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    retention_deadline: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    record_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        CheckConstraint("replay_count >= 0", name="ck_quarantine_replay_count"),
        CheckConstraint("occurrence_count >= 1", name="ck_quarantine_occurrence_count"),
        CheckConstraint(
            "retention_deadline > received_at", name="ck_quarantine_retention"
        ),
        CheckConstraint("record_version >= 1", name="ck_quarantine_record_version"),
        CheckConstraint(
            "(review_owner IS NULL) = (reviewed_at IS NULL)",
            name="ck_quarantine_review_consistency",
        ),
        CheckConstraint(
            "(resolved_by IS NULL) = (resolved_at IS NULL)",
            name="ck_quarantine_resolution_consistency",
        ),
        CheckConstraint(
            "replayed_event_id IS NULL OR (authentication_state = 'VERIFIED' AND "
            "status = 'REPLAYED' AND resolved_at IS NOT NULL)",
            name="ck_quarantine_replay_eligibility",
        ),
        CheckConstraint(
            "status IN ('PENDING_REVIEW','UNDER_REVIEW','CORRECTABLE',"
            "'REPLAY_APPROVED','REPLAYING','REPLAYED','RESOLVED_NO_REPLAY',"
            "'EXPIRED','REJECTED')",
            name="ck_quarantine_state",
        ),
        CheckConstraint(
            "authentication_state = 'VERIFIED' AND "
            "original_signature_verification = 'VERIFIED'",
            name="ck_quarantine_verified_auth",
        ),
        CheckConstraint(
            "(encrypted_payload IS NULL AND encryption_nonce IS NULL AND "
            "encryption_key_version IS NULL) OR "
            "(encrypted_payload IS NOT NULL AND encryption_nonce IS NOT NULL AND "
            "encryption_key_version IS NOT NULL)",
            name="ck_quarantine_encryption_fields",
        ),
        Index("ix_quarantine_status_received", "status", "received_at"),
        Index(
            "ix_quarantine_publisher_received",
            "authenticated_publisher_id",
            "received_at",
        ),
        Index("ix_quarantine_correlation", "server_correlation_id"),
        Index(
            "ix_quarantine_retention_active",
            "retention_deadline",
            postgresql_where=text("legal_hold = false"),
        ),
        Index("ix_quarantine_fingerprint", "payload_fingerprint"),
    )


class QuarantineCorrection(Base):
    __tablename__ = "quarantine_correction"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    quarantine_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("invalid_event_quarantine.id", ondelete="RESTRICT"),
        nullable=False,
    )
    correction_version: Mapped[int] = mapped_column(Integer, nullable=False)
    correction_reason: Mapped[str] = mapped_column(String(512), nullable=False)
    reviewer: Mapped[str] = mapped_column(String(128), nullable=False)
    derived_correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    payload_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    encrypted_payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_version: Mapped[str] = mapped_column(String(32), nullable=False)
    sanitized_diff: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "quarantine_id",
            "correction_version",
            name="uq_quarantine_correction_version",
        ),
        CheckConstraint(
            "correction_version >= 1", name="ck_quarantine_correction_version"
        ),
    )


class EventInbox(Base):
    __tablename__ = "event_inbox"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    event_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    source: Mapped[str] = mapped_column(String(32))
    event_type: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    correlation_id: Mapped[str] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(24), default="accepted")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OutboxEvent(Base):
    __tablename__ = "outbox_event"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    topic: Mapped[str] = mapped_column(String(128))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    correlation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    status: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    replay_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SyncJob(Base):
    __tablename__ = "sync_job"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    job_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookDelivery(Base):
    __tablename__ = "webhook_delivery"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    target: Mapped[str] = mapped_column(String(128))
    event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = "audit_event"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    action: Mapped[str] = mapped_column(String(128))
    subject: Mapped[str] = mapped_column(String(128))
    correlation_id: Mapped[str] = mapped_column(String(128))
    decision: Mapped[str] = mapped_column(String(32))
    redacted_payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AIJob(Base):
    """Canonical AI job record; provider execution is always asynchronous."""

    __tablename__ = "ai_job"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    service_code: Mapped[str] = mapped_column(String(64), nullable=False)
    task_code: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    requested_by: Mapped[str | None] = mapped_column(String(128))
    prompt_version_id: Mapped[str | None] = mapped_column(String(128))
    model_policy_id: Mapped[str | None] = mapped_column(String(128))
    input_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    context_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    output_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(512))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_ai_job_tenant_idempotency"),
        CheckConstraint("priority BETWEEN 0 AND 9", name="ck_ai_job_priority"),
        CheckConstraint("attempt_count >= 0", name="ck_ai_job_attempt_count"),
    )


class AIJobEvent(Base):
    __tablename__ = "ai_job_event"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    ai_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class AIJobAttempt(Base):
    __tablename__ = "ai_job_attempt"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    ai_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(128))
    workflow_id: Mapped[str | None] = mapped_column(String(128))
    workflow_execution_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_class: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(512))
    __table_args__ = (
        UniqueConstraint("ai_job_id", "attempt_number", name="uq_ai_job_attempt"),
    )


class AIPrompt(Base):
    __tablename__ = "ai_prompt"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    service_code: Mapped[str] = mapped_column(String(64), nullable=False)
    task_code: Mapped[str] = mapped_column(String(96), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(String(512))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIPromptVersion(Base):
    __tablename__ = "ai_prompt_version"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    prompt_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    developer_prompt: Mapped[str | None] = mapped_column(Text)
    output_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT")
    approved_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("prompt_id", "version", name="uq_ai_prompt_version"),)


class AIModel(Base):
    __tablename__ = "ai_model"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    model_code: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    capabilities: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    context_length: Mapped[int | None] = mapped_column(Integer)
    maximum_output_tokens: Mapped[int | None] = mapped_column(Integer)
    data_classification_limit: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DISABLED")
    health_status: Mapped[str | None] = mapped_column(String(24))
    fallback_model_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIModelPolicy(Base):
    __tablename__ = "ai_model_policy"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    policy_code: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(512))
    primary_model_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    fallback_model_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    maximum_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    maximum_input_size: Mapped[int] = mapped_column(Integer, nullable=False, default=65536)
    maximum_output_size: Mapped[int] = mapped_column(Integer, nullable=False, default=65536)
    allowed_data_classifications: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIApproval(Base):
    __tablename__ = "ai_approval"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    ai_job_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    action_type: Mapped[str] = mapped_column(String(96), nullable=False)
    action_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    requested_by: Mapped[str | None] = mapped_column(String(128))
    reviewed_by: Mapped[str | None] = mapped_column(String(128))
    review_comment: Mapped[str | None] = mapped_column(String(1024))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIOutputSchema(Base):
    __tablename__ = "ai_output_schema"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    schema_code: Mapped[str] = mapped_column(String(96), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    service_code: Mapped[str] = mapped_column(String(64), nullable=False)
    task_code: Mapped[str] = mapped_column(String(96), nullable=False)
    json_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT")
    approved_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("schema_code", "schema_version", name="uq_ai_output_schema"),)


class LeadSearch(Base):
    __tablename__ = "lead_search"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    ai_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    industry: Mapped[str | None] = mapped_column(String(128))
    keywords: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    location_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    requirements_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    maximum_results: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    minimum_confidence: Mapped[float] = mapped_column(nullable=False, default=0.75)
    target_odoo_team: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    created_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LeadIntelligenceRecord(Base):
    __tablename__ = "lead_intelligence_record"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    search_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(String(2048))
    normalized_domain: Mapped[str | None] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(64))
    normalized_phone: Mapped[str | None] = mapped_column(String(64), index=True)
    email: Mapped[str | None] = mapped_column(String(320), index=True)
    normalized_email: Mapped[str | None] = mapped_column(String(320), index=True)
    address_payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    social_profiles: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    contacts: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    ownership_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    ownership_confidence: Mapped[float] = mapped_column(nullable=False, default=0.0)
    ownership_source: Mapped[str | None] = mapped_column(String(2048))
    verification_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNVERIFIED")
    lead_score: Mapped[float] = mapped_column(nullable=False, default=0.0)
    duplicate_status: Mapped[str] = mapped_column(String(32), nullable=False, default="UNREVIEWED")
    duplicate_of_record_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    source_history: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    odoo_lead_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DISCOVERED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIReconciliation(Base):
    __tablename__ = "ai_reconciliation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRY_RUN")
    observed_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    discrepancy_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LeadReview(Base):
    __tablename__ = "lead_review"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    lead_record_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="REVIEW_REQUIRED", index=True)
    assigned_reviewer_id: Mapped[str | None] = mapped_column(String(128))
    review_policy_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    review_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    review_notes: Mapped[str | None] = mapped_column(Text)
    decision: Mapped[str | None] = mapped_column(String(32))
    decision_reason: Mapped[str | None] = mapped_column(String(1024))
    decision_by: Mapped[str | None] = mapped_column(String(128))
    decision_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "lead_record_id", name="uq_lead_review_scope"),)


class LeadReviewEvent(Base):
    __tablename__ = "lead_review_event"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    lead_review_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_type: Mapped[str] = mapped_column(String(32), nullable=False)
    payload_safe: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LeadApprovalPolicy(Base):
    __tablename__ = "lead_approval_policy"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    policy_code: Mapped[str] = mapped_column(String(96), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="TESTING")
    approved_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "workspace_id", "policy_code", "version", name="uq_lead_approval_policy"),)


class OdooImportBatch(Base):
    __tablename__ = "odoo_import_batch"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    batch_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="REQUESTED", index=True)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    lead_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_odoo_import_batch_idempotency"),)


class OdooImportItem(Base):
    __tablename__ = "odoo_import_item"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    lead_record_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED", index=True)
    odoo_model: Mapped[str] = mapped_column(String(64), nullable=False, default="crm.lead")
    odoo_record_id: Mapped[int | None] = mapped_column(BigInteger)
    odoo_external_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    command_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_class: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OdooImportAttempt(Base):
    __tablename__ = "odoo_import_attempt"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    import_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_safe: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_safe: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_class: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(String(512))
    __table_args__ = (UniqueConstraint("import_item_id", "attempt_number", name="uq_odoo_import_attempt"),)


class OdooImportReconciliation(Base):
    __tablename__ = "odoo_import_reconciliation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    import_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING", index=True)
    reconciliation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_external_key: Mapped[str] = mapped_column(String(255), nullable=False)
    observed_odoo_record_id: Mapped[int | None] = mapped_column(BigInteger)
    result_safe: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class VicidialAssignmentPolicy(Base):
    __tablename__ = "vicidial_assignment_policy"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    policy_code: Mapped[str] = mapped_column(String(96), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="TESTING")
    approved_by: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "workspace_id", "policy_code", "version", name="uq_vicidial_assignment_policy"),)


class VicidialAssignmentBatch(Base):
    __tablename__ = "vicidial_assignment_batch"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    batch_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    policy_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    target_campaign_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_list_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="REQUESTED", index=True)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    lead_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unknown_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_vicidial_assignment_batch_idempotency"),)


class VicidialAssignmentItem(Base):
    __tablename__ = "vicidial_assignment_item"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    lead_record_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    odoo_lead_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ASSIGNMENT_QUEUED", index=True)
    vicidial_lead_id: Mapped[str | None] = mapped_column(String(128))
    vicidial_list_id: Mapped[str] = mapped_column(String(128), nullable=False)
    vicidial_campaign_id: Mapped[str] = mapped_column(String(128), nullable=False)
    external_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    command_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_class: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VicidialAssignmentAttempt(Base):
    __tablename__ = "vicidial_assignment_attempt"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    assignment_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    request_safe: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    response_safe: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_class: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(String(512))
    __table_args__ = (UniqueConstraint("assignment_item_id", "attempt_number", name="uq_vicidial_assignment_attempt"),)


class VicidialAssignmentReconciliation(Base):
    __tablename__ = "vicidial_assignment_reconciliation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    assignment_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING", index=True)
    expected_external_key: Mapped[str] = mapped_column(String(255), nullable=False)
    observed_vicidial_lead_id: Mapped[str | None] = mapped_column(String(128))
    result_safe: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class VicidialCampaignActivationApproval(Base):
    __tablename__ = "vicidial_campaign_activation_approval"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    campaign_id: Mapped[str] = mapped_column(String(128), nullable=False)
    list_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="REQUESTED", index=True)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    authorization_reference: Mapped[str | None] = mapped_column(String(255))
    maintenance_window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    maintenance_window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(1024), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    shut_down_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VicidialDialingWindowPolicy(Base):
    __tablename__ = "vicidial_dialing_window_policy"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    policy_code: Mapped[str] = mapped_column(String(96), nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    start_local: Mapped[str] = mapped_column(String(8), nullable=False)
    end_local: Mapped[str] = mapped_column(String(8), nullable=False)
    max_agents: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    max_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="TESTING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class VicidialCanaryRun(Base):
    __tablename__ = "vicidial_canary_run"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    approval_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    assignment_item_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    allowlisted_phone_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="AUTHORIZED", index=True)
    agent_reference: Mapped[str | None] = mapped_column(String(128))
    carrier_check: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    dialing_window_check: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    call_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    call_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VicidialCanaryEvent(Base):
    __tablename__ = "vicidial_canary_event"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    canary_run_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_safe: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CallIntelligenceJob(Base):
    __tablename__ = "call_intelligence_job"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    vicidial_call_id: Mapped[str] = mapped_column(String(128), nullable=False)
    vicidial_uniqueid: Mapped[str] = mapped_column(String(128), nullable=False)
    odoo_lead_id: Mapped[int | None] = mapped_column(BigInteger)
    campaign_id: Mapped[str | None] = mapped_column(String(128))
    agent_user: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CALL_COMPLETED", index=True)
    language: Mapped[str | None] = mapped_column(String(16))
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    recording_reference_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    transcript_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    analysis_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    qa_review_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_class: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(String(512))
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_call_intelligence_job_idempotency"), UniqueConstraint("tenant_id", "vicidial_uniqueid", name="uq_call_intelligence_job_uniqueid"))


class CallRecordingReference(Base):
    __tablename__ = "call_recording_reference"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    call_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    recording_id: Mapped[str] = mapped_column(String(128), nullable=False)
    storage_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    format: Mapped[str] = mapped_column(String(16), nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    checksum: Mapped[str | None] = mapped_column(String(128))
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retention_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    access_policy: Mapped[str] = mapped_column(String(64), nullable=False, default="AUTHENTICATED_SHORT_LIVED")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="AVAILABLE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CallTranscript(Base):
    __tablename__ = "call_transcript"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    call_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    model_code: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False)
    language_confidence: Mapped[float] = mapped_column()
    speaker_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transcript_text_encrypted_or_protected: Mapped[str] = mapped_column(Text, nullable=False)
    segments: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    redaction_status: Mapped[str] = mapped_column(String(24), nullable=False, default="REDACTED")
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CallAnalysis(Base):
    __tablename__ = "call_analysis"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    call_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    prompt_version: Mapped[str] = mapped_column(String(128), nullable=False)
    model_code: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    sentiment: Mapped[str] = mapped_column(String(16), nullable=False)
    disposition_recommendation: Mapped[str | None] = mapped_column(String(128))
    objections: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    products_discussed: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    commitments: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    callback_recommendation: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    next_best_action: Mapped[str | None] = mapped_column(Text)
    compliance_findings: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False, default=list)
    coaching_recommendations: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    confidence: Mapped[float] = mapped_column()
    raw_result_safe: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CallQAScore(Base):
    __tablename__ = "call_qa_score"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    call_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True)
    scorecard_version: Mapped[str] = mapped_column(String(64), nullable=False)
    scores: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    overall_score: Mapped[float] = mapped_column()
    severity: Mapped[str] = mapped_column(String(32), nullable=False)
    review_status: Mapped[str] = mapped_column(String(24), nullable=False, default="REVIEW_REQUIRED")
    reviewed_by: Mapped[str | None] = mapped_column(String(128))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CallComplianceAlert(Base):
    __tablename__ = "call_compliance_alert"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    call_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="OPEN")
    assigned_to: Mapped[str | None] = mapped_column(String(128))
    resolved_by: Mapped[str | None] = mapped_column(String(128))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CallIntelligenceAttempt(Base):
    __tablename__ = "call_intelligence_attempt"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    call_job_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False)
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    service_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    error_class: Mapped[str | None] = mapped_column(String(64))
    error_code: Mapped[str | None] = mapped_column(String(64))
    safe_error_message: Mapped[str | None] = mapped_column(String(512))
    __table_args__ = (UniqueConstraint("call_job_id", "stage", "attempt_number", name="uq_call_intelligence_attempt"),)


class ServiceInventory(Base):
    __tablename__ = "service_inventory"
    service_code: Mapped[str] = mapped_column(String(96), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    server_ip: Mapped[str] = mapped_column(String(64), nullable=False)
    environment: Mapped[str] = mapped_column(String(24), nullable=False)
    criticality: Mapped[str] = mapped_column(String(16), nullable=False)
    health_endpoint: Mapped[str | None] = mapped_column(String(255))
    metrics_endpoint: Mapped[str | None] = mapped_column(String(255))
    dependencies: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    backup_policy: Mapped[str | None] = mapped_column(String(128))
    recovery_priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    rto_target: Mapped[str | None] = mapped_column(String(32))
    rpo_target: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="UNKNOWN")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Incident(Base):
    __tablename__ = "incident"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    incident_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DETECTED", index=True)
    environment: Mapped[str] = mapped_column(String(24), nullable=False)
    service_codes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    tenant_impact: Mapped[str | None] = mapped_column(String(64))
    customer_impact: Mapped[str | None] = mapped_column(String(255))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mitigated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_id: Mapped[str | None] = mapped_column(String(128))
    commander_id: Mapped[str | None] = mapped_column(String(128))
    root_cause: Mapped[str | None] = mapped_column(Text)
    resolution_summary: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IncidentEvent(Base):
    __tablename__ = "incident_event"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    incident_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(128))
    payload_safe: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ReadinessGate(Base):
    __tablename__ = "readiness_gate"
    gate_code: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="NOT_STARTED")
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    owner: Mapped[str | None] = mapped_column(String(128))
    reviewer: Mapped[str | None] = mapped_column(String(128))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    blocking_findings: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    waiver_reference: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BackupVerification(Base):
    __tablename__ = "backup_verification"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    system_code: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    backup_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="CURRENT_UNVERIFIED")
    checksum: Mapped[str | None] = mapped_column(String(128))
    encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    off_server: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    restore_tested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    restore_result: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ExpansionStage(Base):
    __tablename__ = "expansion_stage"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    stage_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PLANNED", index=True)
    limits: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    approval_reference: Mapped[str | None] = mapped_column(String(255))
    observation_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observation_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gate_outcome: Mapped[str | None] = mapped_column(String(24))
    stop_reason: Mapped[str | None] = mapped_column(String(512))
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ExpansionObservation(Base):
    __tablename__ = "expansion_observation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    stage_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CustomerAccount(Base):
    __tablename__ = "customer_account"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    odoo_partner_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="INVITED")
    subscription_plan: Mapped[str | None] = mapped_column(String(64))
    allowed_modules: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    primary_contact: Mapped[str | None] = mapped_column(String(255))
    billing_contact: Mapped[str | None] = mapped_column(String(255))
    support_contact: Mapped[str | None] = mapped_column(String(255))
    retention_policy: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CustomerUser(Base):
    __tablename__ = "customer_user"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="CUSTOMER_READ_ONLY")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="INVITED")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_customer_user_tenant_email"),)


class KPIDefinition(Base):
    __tablename__ = "kpi_definition"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(96), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    definition: Mapped[str] = mapped_column(Text, nullable=False)
    formula: Mapped[str] = mapped_column(String(512), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    owner: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT")
    guardrails: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("code", "version", name="uq_kpi_definition_version"),)


class KPIObservation(Base):
    __tablename__ = "kpi_observation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str | None] = mapped_column(String(128), index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    kpi_code: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    value: Mapped[float] = mapped_column(Integer, nullable=False)
    numerator: Mapped[float | None] = mapped_column(Integer)
    denominator: Mapped[float | None] = mapped_column(Integer)
    source_freshness: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    quality_status: Mapped[str] = mapped_column(String(24), nullable=False, default="UNVERIFIED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SaasAccount(Base):
    __tablename__ = "saas_account"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    primary_workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    odoo_partner_id: Mapped[str | None] = mapped_column(String(128))
    account_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    onboarding_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    subscription_plan_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True))
    subscription_status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    billing_status: Mapped[str] = mapped_column(String(32), nullable=False, default="NO_BILLING_REQUIRED")
    trial_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    trial_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SaasPlan(Base):
    __tablename__ = "saas_plan"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT")
    entitlements: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SaasProvisioningRequest(Base):
    __tablename__ = "saas_provisioning_request"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    onboarding_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    plan_code: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="REQUESTED", index=True)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_id: Mapped[str | None] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SaasUsageEvent(Base):
    __tablename__ = "saas_usage_event"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str | None] = mapped_column(String(128), index=True)
    meter_code: Mapped[str] = mapped_column(String(96), nullable=False, index=True)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_service: Mapped[str] = mapped_column(String(96), nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MarketplacePlugin(Base):
    __tablename__ = "marketplace_plugin"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    plugin_code: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    plugin_type: Mapped[str] = mapped_column(String(64), nullable=False)
    publisher_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MarketplacePluginVersion(Base):
    __tablename__ = "marketplace_plugin_version"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    plugin_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    package_digest: Mapped[str] = mapped_column(String(80), nullable=False)
    signature: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("plugin_id", "version", name="uq_marketplace_plugin_version"),)


class MarketplaceTenantInstallation(Base):
    __tablename__ = "marketplace_tenant_installation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    plugin_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="INSTALLING", index=True)
    configuration: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_marketplace_install_tenant_key"),)


class DeveloperApplication(Base):
    __tablename__ = "developer_application"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    client_type: Mapped[str] = mapped_column(String(24), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE")
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DeveloperWebhookSubscription(Base):
    __tablename__ = "developer_webhook_subscription"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(96), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(512), nullable=False)
    secret_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DeveloperSandbox(Base):
    __tablename__ = "developer_sandbox"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(24), nullable=False, default="sandbox")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PROVISIONING")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MobileDevice(Base):
    __tablename__ = "mobile_device"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    user_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    app_version: Mapped[str] = mapped_column(String(32), nullable=False)
    device_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING", index=True)
    last_active_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MobilePushToken(Base):
    __tablename__ = "mobile_push_token"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    device_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    token_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MobileSyncSession(Base):
    __tablename__ = "mobile_sync_session"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    client_session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    item_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class VoiceSession(Base):
    __tablename__ = "voice_session"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    campaign_code: Mapped[str] = mapped_column(String(96), nullable=False)
    direction: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="REQUESTED", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class VoiceCallbackRequest(Base):
    __tablename__ = "voice_callback_request"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(64), nullable=False)
    scheduled_at: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="REQUESTED")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIGovernanceAsset(Base):
    __tablename__ = "ai_governance_asset"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    code: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT", index=True)
    schema_reference: Mapped[str | None] = mapped_column(String(255))
    model_reference: Mapped[str | None] = mapped_column(String(255))
    definition: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    __table_args__ = (UniqueConstraint("asset_type", "code", "version", name="uq_ai_governance_asset_version"),)


class AIEvaluationRun(Base):
    __tablename__ = "ai_evaluation_run"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str | None] = mapped_column(String(128), index=True)
    asset_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    dataset_code: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="QUEUED")
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    gate_outcome: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class PolicyDecision(Base):
    __tablename__ = "policy_decision"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    policy: Mapped[str] = mapped_column(String(128))
    allowed: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(128))
    context: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class OrchestrationRequest(Base):
    __tablename__ = "orchestration_request"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    request_uid: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    business_unit: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    subject_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    department_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    team_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    supervisor_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    campaign_references: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    requested_resources: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    idempotency_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="disabled")
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CredentialGrant(Base):
    __tablename__ = "credential_grant"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    orchestration_request_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("orchestration_request.id", ondelete="CASCADE"),
        nullable=False,
    )
    credential_type: Mapped[str] = mapped_column(String(32), nullable=False)
    vault_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    secret_fingerprint: Mapped[str] = mapped_column(String(128), nullable=False)
    retrieval_token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class LeadSyncRequest(Base):
    __tablename__ = "lead_sync_request"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    business_unit: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    campaign_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    list_reference: Mapped[str] = mapped_column(String(128), nullable=False)
    canonical_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="disabled")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ReconciliationCheckpoint(Base):
    __tablename__ = "reconciliation_checkpoint"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    source: Mapped[str] = mapped_column(String(64), unique=True)
    cursor: Mapped[str | None] = mapped_column(String(256))
    status: Mapped[str] = mapped_column(String(24), default="idle")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TransferPolicyDecision(Base):
    __tablename__ = "transfer_policy_decision"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    transfer_id: Mapped[str] = mapped_column(String(128))
    allowed: Mapped[bool] = mapped_column(Boolean)
    reason: Mapped[str] = mapped_column(Text)
    correlation_id: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SystemHealthSnapshot(Base):
    __tablename__ = "system_health_snapshot"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    component: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(24))
    details: Mapped[dict[str, Any]] = mapped_column(JSONB)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class TelephonyExtensionPool(Base):
    __tablename__ = "telephony_extension_pool"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    business_unit: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    role_class: Mapped[str] = mapped_column(String(32), nullable=False)
    range_start: Mapped[int] = mapped_column(Integer, nullable=False)
    range_end: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    __table_args__ = (
        CheckConstraint("range_start >= 6100", name="ck_telephony_pool_start"),
        CheckConstraint("range_end <= 9999", name="ck_telephony_pool_end"),
        CheckConstraint("range_start <= range_end", name="ck_telephony_pool_order"),
    )


class CampaignExtensionAllocation(Base):
    """Authoritative immutable campaign extension-block ledger."""

    __tablename__ = "campaign_extension_allocation"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    campaign_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    campaign_number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    allocation_public_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    extension_start: Mapped[int] = mapped_column(Integer, nullable=False)
    extension_end: Mapped[int] = mapped_column(Integer, nullable=False)
    extension_range: Mapped[Any] = mapped_column(
        INT4RANGE,
        Computed(
            "int4range(extension_start, extension_end, '[]')",
            persisted=True,
        ),
        nullable=False,
    )
    allocation_status: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="PROPOSED"
    )
    allocated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    retired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_change_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        CheckConstraint(
            "extension_start >= 6100",
            name="ck_campaign_extension_allocation_start",
        ),
        CheckConstraint(
            "extension_end <= 9999",
            name="ck_campaign_extension_allocation_end",
        ),
        CheckConstraint(
            "extension_start <= extension_end",
            name="ck_campaign_extension_allocation_order",
        ),
        CheckConstraint(
            "campaign_number > 0 AND campaign_number % 100 = 0",
            name="ck_campaign_extension_allocation_number",
        ),
        CheckConstraint(
            "allocation_status IN "
            "('PROPOSED','RESERVED_DISABLED','ACTIVE','PAUSED','RETIRED')",
            name="ck_campaign_extension_allocation_status",
        ),
        ExcludeConstraint(
            ("extension_range", "&&"),
            using="gist",
            name="ex_campaign_extension_allocation_no_overlap",
        ),
    )


class CampaignRegistry(Base):
    __tablename__ = "campaign_registry"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    campaign_number: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    campaign_code: Mapped[str] = mapped_column(String(3), nullable=False, unique=True)
    campaign_public_id: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    vicidial_campaign_id: Mapped[str] = mapped_column(
        String(8), nullable=False, unique=True
    )
    agent_group: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)
    dialplan_context: Mapped[str] = mapped_column(
        String(80), nullable=False, unique=True
    )
    parent_campaign_number: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("campaign_registry.campaign_number")
    )
    extension_allocation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("campaign_extension_allocation.id"),
        nullable=False,
        unique=True,
    )
    registry_status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="PROPOSED_DISABLED"
    )
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_change_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CampaignObjectIdentity(Base):
    __tablename__ = "campaign_object_identity"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    campaign_number: Mapped[int] = mapped_column(
        Integer, ForeignKey("campaign_registry.campaign_number"), nullable=False
    )
    identity_type: Mapped[str] = mapped_column(String(24), nullable=False)
    sequence_value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    public_id: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    full_alias: Mapped[str | None] = mapped_column(String(112), unique=True)
    source_system: Mapped[str] = mapped_column(String(32), nullable=False)
    source_object_id: Mapped[str] = mapped_column(String(128), nullable=False)
    identity_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="ID_ASSIGNED"
    )
    dialing_state: Mapped[str] = mapped_column(
        String(24), nullable=False, server_default="NOT_ELIGIBLE"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    __table_args__ = (
        UniqueConstraint(
            "campaign_number",
            "identity_type",
            "sequence_value",
            name="uq_campaign_object_identity_sequence",
        ),
        UniqueConstraint(
            "source_system",
            "source_object_id",
            "identity_type",
            name="uq_campaign_object_identity_source",
        ),
    )


class CampaignSearchAlias(Base):
    __tablename__ = "campaign_search_alias"
    alias: Mapped[str] = mapped_column(String(160), primary_key=True)
    campaign_number: Mapped[int] = mapped_column(
        Integer, ForeignKey("campaign_registry.campaign_number"), nullable=False
    )
    object_identity_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("campaign_object_identity.id")
    )
    alias_type: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CampaignFeatureGate(Base):
    __tablename__ = "campaign_feature_gate"
    campaign_number: Mapped[int] = mapped_column(
        Integer, ForeignKey("campaign_registry.campaign_number"), primary_key=True
    )
    feature_name: Mapped[str] = mapped_column(String(48), primary_key=True)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default="DISABLED"
    )
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class CampaignActivationAudit(Base):
    __tablename__ = "campaign_activation_audit"
    activation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    campaign_number: Mapped[int] = mapped_column(
        Integer, ForeignKey("campaign_registry.campaign_number"), nullable=False
    )
    policy_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    from_status: Mapped[str] = mapped_column(String(32), nullable=False)
    to_status: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class TelephonyExtensionReservation(Base):
    __tablename__ = "telephony_extension_reservation"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    extension: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    request_id: Mapped[str] = mapped_column(String(128), nullable=False)
    pool_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("telephony_extension_pool.id"), nullable=False
    )
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="RESERVED")
    idempotency_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    reserved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (
        CheckConstraint("extension <> 6101", name="ck_telephony_reservation_6101"),
        CheckConstraint("extension <> 1001", name="ck_telephony_reservation_1001"),
        CheckConstraint(
            "state IN ('RESERVED','DISABLED_READY','ACTIVE','SUSPENDED','RELEASED','EXPIRED','COOLDOWN')",
            name="ck_telephony_reservation_state",
        ),
        Index(
            "uq_telephony_active_extension",
            "extension",
            unique=True,
            postgresql_where=text(
                "state IN ('RESERVED','DISABLED_READY','ACTIVE','SUSPENDED','COOLDOWN')"
            ),
        ),
        Index(
            "uq_telephony_active_employee",
            "employee_id",
            unique=True,
            postgresql_where=text(
                "state IN ('RESERVED','DISABLED_READY','ACTIVE','SUSPENDED')"
            ),
        ),
    )


class TelephonyProvisioningSaga(Base):
    __tablename__ = "telephony_provisioning_saga"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    request_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    employee_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    business_unit: Mapped[str] = mapped_column(String(64), nullable=False)
    campaign: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    extension: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    idempotency_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True
    )
    correlation_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    record_environment: Mapped[str] = mapped_column(
        String(16), nullable=False, default="PRODUCTION"
    )
    test_run_id: Mapped[str | None] = mapped_column(String(128), index=True)
    causation_id: Mapped[str | None] = mapped_column(String(128), index=True)
    policy_hash: Mapped[str | None] = mapped_column(String(64))
    approved_odoo_request: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    credential_reference: Mapped[str | None] = mapped_column(String(255))
    completed_steps: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    last_error_code: Mapped[str | None] = mapped_column(String(64))
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_telephony_saga_version"),
        CheckConstraint(
            "record_environment IN ('PRODUCTION','STAGING','TEST')",
            name="ck_telephony_saga_environment",
        ),
        CheckConstraint(
            "(record_environment = 'PRODUCTION' AND test_run_id IS NULL) OR "
            "(record_environment IN ('STAGING','TEST') AND "
            "test_run_id IS NOT NULL AND causation_id IS NOT NULL AND "
            "policy_hash IS NOT NULL)",
            name="ck_telephony_saga_test_binding",
        ),
        CheckConstraint(
            "state IN ('DRAFT','PENDING_APPROVAL','APPROVED','INVENTORY_CHECK','RESERVED',"
            "'PROVISIONING','DISABLED_READY','ACTIVATION_PENDING','ACTIVE','FAILED',"
            "'ROLLED_BACK','SUSPENDING','SUSPENDED','DEPROVISIONING','COOLDOWN')",
            name="ck_telephony_saga_state",
        ),
    )


class TelephonyCallLifecycle(Base):
    __tablename__ = "telephony_call_lifecycle"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    correlation_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    linked_id: Mapped[str | None] = mapped_column(String(128), index=True)
    primary_unique_id: Mapped[str] = mapped_column(String(128), nullable=False)
    lifecycle_state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="STARTED"
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disposition: Mapped[str | None] = mapped_column(String(64))
    hangup_cause: Mapped[str | None] = mapped_column(String(64))
    source_extension: Mapped[str] = mapped_column(String(32), nullable=False)
    destination: Mapped[str] = mapped_column(String(64), nullable=False)
    dialplan_context: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    __table_args__ = (
        CheckConstraint(
            "lifecycle_state IN ('STARTED','CONNECTED','ENDED')",
            name="ck_telephony_call_lifecycle_state",
        ),
    )


class TelephonyCallLifecycleEvent(Base):
    __tablename__ = "telephony_call_lifecycle_event"
    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("telephony_call_lifecycle.id", ondelete="CASCADE"),
        nullable=False,
    )
    integration_event_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("integration_event.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    original_event_id: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True
    )
    unique_id: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(255), nullable=False)
    incoming_state: Mapped[str] = mapped_column(String(16), nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(16))
    resulting_state: Mapped[str] = mapped_column(String(16), nullable=False)
    transition_applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IntegrationService(Base):
    __tablename__ = "integration_service"
    service_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    service_key: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(128), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IntegrationCredentialReference(Base):
    __tablename__ = "integration_credential_reference"
    credential_reference_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    reference_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IntegrationEndpoint(Base):
    __tablename__ = "integration_endpoint"
    endpoint_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    service_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("integration_service.service_id", ondelete="RESTRICT"),
        nullable=False,
    )
    endpoint_key: Mapped[str] = mapped_column(String(96), nullable=False)
    api_version: Mapped[str] = mapped_column(String(16), nullable=False, default="v1")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "service_id", "endpoint_key", "api_version", name="uq_endpoint_identity"
        ),
    )


class IntegrationEndpointVersion(Base):
    __tablename__ = "integration_endpoint_version"
    endpoint_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    endpoint_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("integration_endpoint.endpoint_id", ondelete="CASCADE"),
        nullable=False,
    )
    configuration_version: Mapped[int] = mapped_column(Integer, nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    path_template: Mapped[str] = mapped_column(String(512), nullable=False)
    http_method: Mapped[str] = mapped_column(String(10), nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(64), nullable=False, default="application/json"
    )
    authentication_mode: Mapped[str] = mapped_column(String(64), nullable=False)
    required_audience: Mapped[str] = mapped_column(String(128), nullable=False)
    required_scopes: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list
    )
    credential_reference_id: Mapped[str] = mapped_column(String(255), nullable=False)
    tls_profile_id: Mapped[str] = mapped_column(String(128), nullable=False)
    timeout_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=10000)
    connection_timeout_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3000
    )
    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0
    )
    concurrency_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    idempotency_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    retry_class: Mapped[str] = mapped_column(
        String(32), nullable=False, default="NO_RETRY"
    )
    retry_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    redirects_allowed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    target_attestation_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    stale_read_safe: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    kill_switch: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    configuration_checksum: Mapped[str] = mapped_column(String(71), nullable=False)
    effective_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "endpoint_id",
            "configuration_version",
            name="uq_endpoint_configuration_version",
        ),
        CheckConstraint("configuration_version >= 1", name="ck_endpoint_version"),
        CheckConstraint("timeout_ms > 0", name="ck_endpoint_timeout"),
        CheckConstraint(
            "connection_timeout_ms > 0", name="ck_endpoint_connection_timeout"
        ),
        CheckConstraint("retry_limit >= 0", name="ck_endpoint_retry_limit"),
        CheckConstraint(
            "retry_class IN ('NO_RETRY','BOUNDED_TRANSIENT_RETRY','MANUAL_REPLAY_ONLY')",
            name="ck_endpoint_retry_class",
        ),
    )


class IntegrationRouteBinding(Base):
    __tablename__ = "integration_route_binding"
    binding_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    endpoint_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("integration_endpoint_version.endpoint_version_id"),
        nullable=False,
    )
    environment: Mapped[str] = mapped_column(String(32), nullable=False)
    organization_scope: Mapped[str] = mapped_column(
        String(128), nullable=False, default=""
    )
    business_unit_scope: Mapped[str] = mapped_column(
        String(128), nullable=False, default=""
    )
    campaign_scope: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    workflow_scope: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    event_type_scope: Mapped[str] = mapped_column(
        String(128), nullable=False, default=""
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint(
            "environment",
            "endpoint_version_id",
            "organization_scope",
            "business_unit_scope",
            "campaign_scope",
            "workflow_scope",
            "event_type_scope",
            name="uq_route_binding_scope",
        ),
        Index(
            "ix_route_binding_lookup",
            "environment",
            "organization_scope",
            "business_unit_scope",
            "campaign_scope",
        ),
    )


class IntegrationSchemaVersion(Base):
    __tablename__ = "integration_schema_version"
    schema_version_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    service_key: Mapped[str] = mapped_column(String(64), nullable=False)
    endpoint_key: Mapped[str] = mapped_column(String(96), nullable=False)
    api_version: Mapped[str] = mapped_column(String(16), nullable=False)
    schema_reference: Mapped[str] = mapped_column(String(512), nullable=False)
    checksum: Mapped[str] = mapped_column(String(71), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    __table_args__ = (
        UniqueConstraint(
            "service_key",
            "endpoint_key",
            "api_version",
            name="uq_integration_schema_key",
        ),
    )


class IntegrationEndpointAudit(Base):
    __tablename__ = "integration_endpoint_audit"
    audit_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    endpoint_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    actor: Mapped[str] = mapped_column(String(128), nullable=False)
    previous_checksum: Mapped[str | None] = mapped_column(String(71))
    new_checksum: Mapped[str] = mapped_column(String(71), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class IntegrationRegistryGeneration(Base):
    __tablename__ = "integration_registry_generation"
    environment: Mapped[str] = mapped_column(String(32), primary_key=True)
    generation: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    configuration_checksum: Mapped[str] = mapped_column(String(71), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_by: Mapped[str] = mapped_column(String(128), nullable=False)


class HealthcarePatient(Base):
    __tablename__ = "healthcare_patient"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    preferred_language: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    data_classification: Mapped[str] = mapped_column(String(24), nullable=False, default="PROTECTED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class HealthcareFacility(Base):
    __tablename__ = "healthcare_facility"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class HealthcareTrip(Base):
    __tablename__ = "healthcare_trip"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String(128), nullable=False)
    pickup_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    destination_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    service_level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class HealthcareClaim(Base):
    __tablename__ = "healthcare_claim"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    trip_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceApplicant(Base):
    __tablename__ = "finance_applicant"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    applicant_type: Mapped[str] = mapped_column(String(32), nullable=False, default="APPLICANT")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceApplication(Base):
    __tablename__ = "finance_application"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    applicant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT", index=True)
    consent_status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    disclosure_status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceDisclosureAcceptance(Base):
    __tablename__ = "finance_disclosure_acceptance"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    application_id: Mapped[str] = mapped_column(String(128), nullable=False)
    disclosure_code: Mapped[str] = mapped_column(String(96), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceDocument(Base):
    __tablename__ = "finance_document"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    application_id: Mapped[str] = mapped_column(String(128), nullable=False)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="REQUESTED")
    storage_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceLenderProduct(Base):
    __tablename__ = "finance_lender_product"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    lender_name: Mapped[str] = mapped_column(String(255), nullable=False)
    product_code: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE")
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False, default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class FinanceMatchResult(Base):
    __tablename__ = "finance_match_result"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    application_id: Mapped[str] = mapped_column(String(128), nullable=False)
    product_id: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    explanation_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LegalProspect(Base):
    __tablename__ = "legal_prospect"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LegalIntake(Base):
    __tablename__ = "legal_intake"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    prospect_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="DRAFT", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LegalMatter(Base):
    __tablename__ = "legal_matter"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    client_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    confidentiality_level: Mapped[str] = mapped_column(String(24), nullable=False, default="CONFIDENTIAL")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LegalConflictRequest(Base):
    __tablename__ = "legal_conflict_request"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    intake_id: Mapped[str] = mapped_column(String(128), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False, default="INSUFFICIENT_INFORMATION")
    reviewer_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LegalDocument(Base):
    __tablename__ = "legal_document"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(String(128), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    privilege_classification: Mapped[str] = mapped_column(String(32), nullable=False, default="CONFIDENTIAL")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="UPLOADED")
    storage_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class LegalEngagement(Base):
    __tablename__ = "legal_engagement"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    matter_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    version: Mapped[int] = mapped_column(BigInteger, nullable=False, default=1)
    client_signed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    firm_signed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SupportTicket(Base):
    __tablename__ = "support_ticket"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="NEW", index=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="NORMAL")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SupportConversation(Base):
    __tablename__ = "support_conversation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    ticket_id: Mapped[str] = mapped_column(String(128), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING_HUMAN_REVIEW")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SupportMessage(Base):
    __tablename__ = "support_message"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    ticket_id: Mapped[str] = mapped_column(String(128), nullable=False)
    visibility: Mapped[str] = mapped_column(String(24), nullable=False, default="CUSTOMER_VISIBLE")
    approval_status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING_REVIEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SupportSlaInstance(Base):
    __tablename__ = "support_sla_instance"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    ticket_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="NOT_STARTED")
    first_response_target_minutes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    resolution_target_minutes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SupportEscalation(Base):
    __tablename__ = "support_escalation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    ticket_id: Mapped[str] = mapped_column(String(128), nullable=False)
    escalation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RevOpsLead(Base):
    __tablename__ = "revops_lead"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(96), nullable=False, default="")
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RevOpsOpportunity(Base):
    __tablename__ = "revops_opportunity"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    lead_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NEW", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RevOpsCampaign(Base):
    __tablename__ = "revops_campaign"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class RevOpsCommission(Base):
    __tablename__ = "revops_commission"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    opportunity_id: Mapped[str] = mapped_column(String(128), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING_REVIEW")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EnterpriseIdentityProvider(Base):
    __tablename__ = "enterprise_identity_provider"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="STAGING")
    credential_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class GovernanceEvidence(Base):
    __tablename__ = "governance_evidence"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str | None] = mapped_column(String(128), index=True)
    control_code: Mapped[str] = mapped_column(String(96), nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="COLLECTED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class IntegrationWebhookEvent(Base):
    __tablename__ = "integration_webhook_event"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="RECEIVED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DataPipelineRun(Base):
    __tablename__ = "data_pipeline_run"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str | None] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="STAGING")
    row_scope_enforced: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DisasterRecoveryEvidence(Base):
    __tablename__ = "disaster_recovery_evidence"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    service: Mapped[str] = mapped_column(String(96), nullable=False)
    encrypted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    off_server: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    restore_status: Mapped[str] = mapped_column(String(24), nullable=False, default="UNVERIFIED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TradingAccount(Base):
    __tablename__ = "trading_account"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    customer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), nullable=False)
    base_currency: Mapped[str] = mapped_column(String(16), nullable=False, default="USD")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TradingInstrument(Base):
    __tablename__ = "trading_instrument"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="ACTIVE", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TradingOrder(Base):
    __tablename__ = "trading_order"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    instrument_id: Mapped[str] = mapped_column(String(128), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    order_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TradingLedgerEntry(Base):
    __tablename__ = "trading_ledger_entry"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False)
    debit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    credit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    external_reference: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TradingProviderConnection(Base):
    __tablename__ = "trading_provider_connection"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(96), nullable=False)
    environment: Mapped[str] = mapped_column(String(24), nullable=False, default="SANDBOX")
    credential_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    allowed_operations: Mapped[str] = mapped_column(String(512), nullable=False, default="health_check")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TradingContractCertification(Base):
    __tablename__ = "trading_contract_certification"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(96), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    evidence_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TradingProviderReconciliation(Base):
    __tablename__ = "trading_provider_reconciliation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    internal_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TradingComplianceReview(Base):
    __tablename__ = "trading_compliance_review"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    review_type: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    synthetic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TradingDisclosureAcceptance(Base):
    __tablename__ = "trading_disclosure_acceptance"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    disclosure_code: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TradingLicensingGap(Base):
    __tablename__ = "trading_licensing_gap"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    classification: Mapped[str] = mapped_column(String(32), nullable=False)
    jurisdiction: Mapped[str] = mapped_column(String(96), nullable=False, default="UNKNOWN")
    evidence_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="OPEN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TradingPilotApproval(Base):
    __tablename__ = "trading_pilot_approval"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT")
    synthetic_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    legal_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    security_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    compliance_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class TradingPilotEvidence(Base):
    __tablename__ = "trading_pilot_evidence"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    pilot_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="MISSING")
    reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIEmployee(Base):
    __tablename__ = "ai_employee"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    employee_code: Mapped[str] = mapped_column(String(96), nullable=False, unique=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(160), nullable=False)
    employee_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    configuration_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    human_owner_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIEmployeeTask(Base):
    __tablename__ = "ai_employee_task"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    approval_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIEmployeeTool(Base):
    __tablename__ = "ai_employee_tool"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tool_code: Mapped[str] = mapped_column(String(96), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(24), nullable=False, default="READ_ONLY")
    required_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIEmployeeApproval(Base):
    __tablename__ = "ai_employee_approval"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    task_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    reviewer_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIEmployeeMemory(Base):
    __tablename__ = "ai_employee_memory"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    classification: Mapped[str] = mapped_column(String(24), nullable=False, default="INTERNAL")
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIEmployeeDelegation(Base):
    __tablename__ = "ai_employee_delegation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    target_employee_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    collaborator_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MemoryRecord(Base):
    __tablename__ = "memory_record"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    memory_type: Mapped[str] = mapped_column(String(40), nullable=False)
    memory_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    classification: Mapped[str] = mapped_column(String(24), nullable=False, default="INTERNAL")
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="CAPTURED", index=True)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    source_version: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class KnowledgeSource(Base):
    __tablename__ = "knowledge_source"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    classification: Mapped[str] = mapped_column(String(24), nullable=False, default="INTERNAL")
    source_uri_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    publication_state: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT")
    indexing_state: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class MemoryRetrievalRequest(Base):
    __tablename__ = "memory_retrieval_request"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(128), nullable=False)
    requested_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    authorization_decision: Mapped[str] = mapped_column(String(24), nullable=False, default="DENIED")
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AITool(Base):
    __tablename__ = "ai_tool"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tool_code: Mapped[str] = mapped_column(String(128), nullable=False)
    adapter: Mapped[str] = mapped_column(String(96), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(24), nullable=False, default="READ_ONLY")
    required_approval: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIToolRequest(Base):
    __tablename__ = "ai_tool_request"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(128), nullable=False)
    task_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_code: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="REQUESTED", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIToolExecution(Base):
    __tablename__ = "ai_tool_execution"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="QUEUED")
    external_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIToolReconciliation(Base):
    __tablename__ = "ai_tool_reconciliation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    request_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="UNKNOWN")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIDepartment(Base):
    __tablename__ = "ai_department"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    department_code: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    human_manager_id: Mapped[str] = mapped_column(String(128), nullable=False)
    ai_manager_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    budget_limit: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AICollaborationSession(Base):
    __tablename__ = "ai_collaboration_session"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    goal_id: Mapped[str] = mapped_column(String(128), nullable=False)
    owning_department_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    manager_employee_id: Mapped[str] = mapped_column(String(128), nullable=False)
    human_owner_user_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    participant_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    delegation_depth_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIDelegation(Base):
    __tablename__ = "ai_delegation"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    collaboration_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    source_employee_id: Mapped[str] = mapped_column(String(128), nullable=False)
    target_employee_id: Mapped[str] = mapped_column(String(128), nullable=False)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIHandoff(Base):
    __tablename__ = "ai_handoff"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    collaboration_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    sender_employee_id: Mapped[str] = mapped_column(String(128), nullable=False)
    receiver_employee_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIEmployeeEvaluationRun(Base):
    __tablename__ = "ai_employee_evaluation_run"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(128), nullable=False)
    employee_version: Mapped[str] = mapped_column(String(64), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="DRAFT", index=True)
    human_reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    trace_id: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIEmployeeScorecard(Base):
    __tablename__ = "ai_employee_scorecard"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(128), nullable=False)
    period: Mapped[str] = mapped_column(String(24), nullable=False)
    performance_state: Mapped[str] = mapped_column(String(32), nullable=False, default="UNASSESSED")
    evidence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reviewed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIEmployeeChangeProposal(Base):
    __tablename__ = "ai_employee_change_proposal"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(128), nullable=False)
    proposal_type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="CAPTURED", index=True)
    proposed_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AILearningApproval(Base):
    __tablename__ = "ai_learning_approval"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    proposal_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    reviewer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ControlTowerService(Base):
    __tablename__ = "control_tower_service"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    service_code: Mapped[str] = mapped_column(String(96), nullable=False)
    server: Mapped[str] = mapped_column(String(64), nullable=False)
    criticality: Mapped[str] = mapped_column(String(24), nullable=False, default="STANDARD")
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="UNKNOWN", index=True)
    last_success: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ControlTowerKPI(Base):
    __tablename__ = "control_tower_kpi"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    formula: Mapped[str] = mapped_column(String(512), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    freshness: Mapped[str] = mapped_column(String(24), nullable=False, default="UNKNOWN")
    value: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ControlTowerIncident(Base):
    __tablename__ = "control_tower_incident"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM")
    incident_type: Mapped[str] = mapped_column(String(32), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="DETECTED", index=True)
    owner_id: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ControlTowerAction(Base):
    __tablename__ = "control_tower_action"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="REQUESTED")
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIPilotProgram(Base):
    __tablename__ = "ai_pilot_program"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="PROPOSED", index=True)
    max_tenants: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIPilotAdmission(Base):
    __tablename__ = "ai_pilot_admission"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    workspace_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(String(128), nullable=False)
    autonomy_level: Mapped[str] = mapped_column(String(32), nullable=False)
    human_owner_id: Mapped[str] = mapped_column(String(128), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False, default="VALIDATING", index=True)
    budget_limit: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIPilotReadinessCheck(Base):
    __tablename__ = "ai_pilot_readiness_check"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    admission_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    gate: Mapped[str] = mapped_column(String(48), nullable=False)
    outcome: Mapped[str] = mapped_column(String(24), nullable=False, default="BLOCKED")
    evidence_reference: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AIPilotSuspension(Base):
    __tablename__ = "ai_pilot_suspension"
    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    admission_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    operator_id: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
