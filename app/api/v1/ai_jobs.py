from fastapi import APIRouter, Header, HTTPException

from app.core.ai_jobs import AIActionDecision, AIJobControl, AIJobRequest, AIJobResult, TenantScope
from app.core.config import settings

router = APIRouter(prefix="/api/v1/ai", tags=["ai-control"])
service = AIJobControl()
service.enabled = settings.ai_platform_enabled
service.submission_enabled = settings.ai_job_submission_enabled
service.results_enabled = settings.ai_result_processing_enabled
service.decisions_enabled = settings.ai_action_decision_enabled


def _scope(tenant: str, company: int, business_unit: str, campaign: str) -> TenantScope:
    return TenantScope(
        tenant_id=tenant,
        company_id=company,
        business_unit_key=business_unit,
        campaign_key=campaign,
    )


@router.post("/jobs", status_code=202)
def create_job(request: AIJobRequest):
    try:
        return service.create(request)
    except (PermissionError, ValueError) as exc:
        raise HTTPException(403 if isinstance(exc, PermissionError) else 409, str(exc)) from exc


@router.get("/jobs/{job_id}")
def get_job(
    job_id: str,
    tenant: str = Header(alias="X-Codestra-Tenant"),
    company: int = Header(alias="X-Codestra-Company"),
    business_unit: str = Header(alias="X-Codestra-Business-Unit"),
    campaign: str = Header(alias="X-Codestra-Campaign"),
):
    try:
        return service.get(job_id, _scope(tenant, company, business_unit, campaign))
    except LookupError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/results", status_code=202)
def receive_result(result: AIJobResult):
    try:
        return service.receive_result(result)
    except (PermissionError, LookupError) as exc:
        raise HTTPException(403, str(exc)) from exc


@router.post("/action-proposals/{proposal_id}/decision", status_code=202)
def decide(proposal_id: str, decision: AIActionDecision):
    if proposal_id != decision.proposal_id:
        raise HTTPException(409, "proposal binding mismatch")
    try:
        return service.decide(decision)
    except (PermissionError, LookupError, ValueError) as exc:
        raise HTTPException(403, str(exc)) from exc
