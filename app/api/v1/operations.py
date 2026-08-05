from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.db.models import AuditEvent, Incident, IncidentEvent, ReadinessGate, BackupVerification, ExpansionStage, ExpansionObservation
from app.core.expansion import evaluate_observation, ObservationSnapshot, transition, ExpansionGateError
from app.workers.dead_letter import list_dead_letters, replay
from app.workers.outbox import queue_metrics, recover_expired_leases
from app.workers.reconciliation import reconcile_internal_outbox


router = APIRouter(prefix="/api/v1/operations", tags=["operations"])


def require_integration_admin(role: str) -> None:
    if role != "integration_admin":
        raise HTTPException(403, "integration administrator role required")


@router.get("/reliability")
async def reliability(db: AsyncSession = Depends(get_session)):
    return {"outbox": await queue_metrics(db)}


@router.get("/dead-letters")
async def dead_letters(limit: int = 100, db: AsyncSession = Depends(get_session)):
    return {"items": await list_dead_letters(db, limit)}


@router.post("/dead-letters/{item_id}/replay", status_code=202)
async def replay_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_session),
    x_codestra_role: str = Header("", alias="X-Codestra-Role"),
):
    require_integration_admin(x_codestra_role)
    if not await replay(db, item_id):
        raise HTTPException(409, "item is not eligible for replay")
    return {"id": str(item_id), "status": "pending"}


@router.post("/maintenance/recover", status_code=202)
async def recover(
    db: AsyncSession = Depends(get_session),
    x_codestra_role: str = Header("", alias="X-Codestra-Role"),
):
    require_integration_admin(x_codestra_role)
    return {"recovered": await recover_expired_leases(db)}


@router.post("/reconciliation", status_code=202)
async def reconcile(
    db: AsyncSession = Depends(get_session),
    x_codestra_role: str = Header("", alias="X-Codestra-Role"),
):
    require_integration_admin(x_codestra_role)
    return await reconcile_internal_outbox(db)


def require_ops_role(role: str) -> None:
    if role not in {"AI_PLATFORM_ADMIN", "AI_SECURITY_ADMIN", "AI_AUDITOR", "integration_admin"}:
        raise HTTPException(403, "operations administrator role required")


@router.get("/incidents")
async def incidents(limit: int = 100, db: AsyncSession = Depends(get_session), role: str = Header("", alias="X-Codestra-Role")):
    require_ops_role(role)
    rows = (await db.scalars(select(Incident).order_by(Incident.detected_at.desc()).limit(min(limit, 100)))).all()
    return {"items": [{"id": str(row.id), "incident_code": row.incident_code, "title": row.title, "severity": row.severity, "status": row.status, "environment": row.environment, "services": row.service_codes, "detected_at": row.detected_at} for row in rows]}


@router.post("/incidents", status_code=202)
async def create_incident(body: dict, db: AsyncSession = Depends(get_session), role: str = Header("", alias="X-Codestra-Role")):
    require_ops_role(role)
    title = str(body.get("title", "")).strip()
    if not title or len(title) > 255:
        raise HTTPException(422, "incident title is required")
    incident = Incident(incident_code=f"INC-{uuid4().hex[:12].upper()}", title=title, severity=str(body.get("severity", "WARNING")), status="DETECTED", environment=str(body.get("environment", "staging")), service_codes=list(body.get("service_codes", [])), correlation_id=str(body.get("correlation_id", uuid4())))
    db.add(incident)
    await db.flush()
    db.add(IncidentEvent(incident_id=incident.id, event_type="CREATED", actor_id=role, payload_safe={"severity": incident.severity}))
    db.add(AuditEvent(action="operations.incident.created", subject=str(incident.id), correlation_id=incident.correlation_id, decision="accepted", redacted_payload={"severity": incident.severity}))
    await db.commit()
    return {"incident_id": str(incident.id), "incident_code": incident.incident_code, "status": incident.status}


@router.post("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: UUID, db: AsyncSession = Depends(get_session), role: str = Header("", alias="X-Codestra-Role")):
    require_ops_role(role)
    incident = await db.get(Incident, incident_id)
    if not incident:
        raise HTTPException(404, "incident not found")
    incident.status = "ACKNOWLEDGED"
    incident.acknowledged_at = datetime.now(UTC)
    db.add(IncidentEvent(incident_id=incident.id, event_type="ACKNOWLEDGED", actor_id=role, payload_safe={}))
    await db.commit()
    return {"incident_id": str(incident.id), "status": incident.status}


@router.get("/readiness")
async def readiness(db: AsyncSession = Depends(get_session), role: str = Header("", alias="X-Codestra-Role")):
    require_ops_role(role)
    rows = (await db.scalars(select(ReadinessGate).order_by(ReadinessGate.gate_code))).all()
    blocking = [row.gate_code for row in rows if row.status in {"FAIL", "BLOCKED"}]
    return {"status": "BLOCKED" if blocking else "IN_REVIEW", "blocking_gates": blocking, "gates": [{"code": row.gate_code, "status": row.status, "evidence": row.evidence, "expires_at": row.expires_at} for row in rows]}


@router.get("/backups")
async def backups(db: AsyncSession = Depends(get_session), role: str = Header("", alias="X-Codestra-Role")):
    require_ops_role(role)
    rows = (await db.scalars(select(BackupVerification).order_by(BackupVerification.created_at.desc()).limit(200))).all()
    return {"items": [{"id": str(row.id), "system_code": row.system_code, "state": row.state, "encrypted": row.encrypted, "off_server": row.off_server, "restore_tested": row.restore_tested, "last_verified_at": row.last_verified_at} for row in rows]}


@router.get("/expansion/stages")
async def expansion_stages(db: AsyncSession = Depends(get_session), role: str = Header("", alias="X-Codestra-Role")):
    require_ops_role(role)
    rows = (await db.scalars(select(ExpansionStage).order_by(ExpansionStage.created_at.desc()))).all()
    return {"items": [{"id": str(r.id), "stage_code": r.stage_code, "status": r.status, "limits": r.limits, "gate_outcome": r.gate_outcome, "stop_reason": r.stop_reason} for r in rows]}


@router.post("/expansion/stages", status_code=202)
async def create_expansion_stage(body: dict, db: AsyncSession = Depends(get_session), role: str = Header("", alias="X-Codestra-Role")):
    require_ops_role(role)
    code = str(body.get("stage_code", "")).strip()
    if not code or len(code) > 64 or not isinstance(body.get("limits", {}), dict):
        raise HTTPException(422, "stage_code and limits are required")
    stage = ExpansionStage(stage_code=code, limits=body["limits"], correlation_id=str(body.get("correlation_id", uuid4())))
    db.add(stage)
    await db.flush()
    db.add(AuditEvent(action="expansion.stage.created", subject=str(stage.id), correlation_id=stage.correlation_id, decision="accepted", redacted_payload={"stage_code": code, "limits": body["limits"]}))
    await db.commit()
    return {"stage_id": str(stage.id), "status": stage.status}


@router.post("/expansion/stages/{stage_id}/observe", status_code=202)
async def observe_expansion_stage(stage_id: UUID, body: dict, db: AsyncSession = Depends(get_session), role: str = Header("", alias="X-Codestra-Role")):
    require_ops_role(role)
    stage = await db.get(ExpansionStage, stage_id)
    if not stage:
        raise HTTPException(404, "expansion stage not found")
    try:
        snapshot = ObservationSnapshot(**{k: body.get(k, 0) for k in ObservationSnapshot.__dataclass_fields__})
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "invalid observation snapshot") from exc
    outcome = evaluate_observation(snapshot)
    stage.gate_outcome = outcome
    if outcome == "FAIL_ROLLBACK":
        stage.stop_reason = "automatic stop gate triggered"
    db.add(ExpansionObservation(stage_id=stage.id, outcome=outcome, snapshot=body))
    db.add(AuditEvent(action="expansion.observation.evaluated", subject=str(stage.id), correlation_id=stage.correlation_id, decision=outcome, redacted_payload={"outcome": outcome}))
    await db.commit()
    return {"stage_id": str(stage.id), "outcome": outcome}


@router.post("/expansion/stages/{stage_id}/transition")
async def transition_expansion_stage(stage_id: UUID, body: dict, db: AsyncSession = Depends(get_session), role: str = Header("", alias="X-Codestra-Role")):
    require_ops_role(role)
    stage = await db.get(ExpansionStage, stage_id)
    if not stage:
        raise HTTPException(404, "expansion stage not found")
    try:
        stage.status = transition(stage.status, str(body.get("status", "")))
    except ExpansionGateError as exc:
        raise HTTPException(409, str(exc)) from exc
    db.add(AuditEvent(action="expansion.stage.transitioned", subject=str(stage.id), correlation_id=stage.correlation_id, decision="accepted", redacted_payload={"status": stage.status}))
    await db.commit()
    return {"stage_id": str(stage.id), "status": stage.status}
