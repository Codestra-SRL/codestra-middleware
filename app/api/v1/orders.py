from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Response, status

from app.order_orchestration import (
    ApprovalRequest,
    ErrorEnvelope,
    OrderEnvelope,
    OrderStatus,
    ResultEnvelope,
    STORE,
    content_hash,
    validate_for_dispatch,
)

router = APIRouter(prefix="/api/v1", tags=["approved-order-orchestration"])


@router.post("/orders", status_code=status.HTTP_202_ACCEPTED)
async def receive_order(order: OrderEnvelope, response: Response) -> dict[str, Any]:
    record = STORE.create(order)
    response.headers["X-Order-Status"] = record["status"]
    return record


@router.get("/orders/{order_id}")
async def get_order(order_id: str) -> dict[str, Any]:
    return STORE.get(order_id)


@router.post("/orders/{order_id}/approve", status_code=status.HTTP_202_ACCEPTED)
async def approve_order(order_id: str, approval: ApprovalRequest) -> dict[str, Any]:
    record = STORE.get(order_id)
    if approval.content_hash != record["content_hash"]:
        raise HTTPException(409, "approval content hash does not match order")
    if approval.approved_by == record["envelope"]["source_system"]:
        raise HTTPException(403, "self approval is not permitted")
    record["envelope"]["approval"].update(
        {"status": "approved", "approved_by": approval.approved_by,
         "approved_at": datetime.now(timezone.utc).isoformat()}
    )
    record["status"] = OrderStatus.APPROVED.value
    return record


@router.post("/orders/{order_id}/reject", status_code=status.HTTP_202_ACCEPTED)
async def reject_order(order_id: str) -> dict[str, Any]:
    record = STORE.get(order_id)
    record["status"] = OrderStatus.REJECTED.value
    return record


@router.post("/integrations/n8n/dispatch", status_code=status.HTTP_202_ACCEPTED)
async def dispatch_order(order: OrderEnvelope) -> dict[str, Any]:
    record = STORE.get(order.order_id)
    validate_for_dispatch(order)
    if record["content_hash"] != content_hash(order):
        raise HTTPException(409, "order content changed after intake")
    record["status"] = OrderStatus.DISPATCHED_TO_N8N.value
    record["n8n_dispatch"] = {"workflow_code": order.workflow_code, "accepted_at": datetime.now(timezone.utc).isoformat()}
    return {"accepted": True, "status": record["status"], "command_id": order.command_id, "trace_id": order.trace_id}


@router.post("/integrations/n8n/results", status_code=status.HTTP_202_ACCEPTED)
async def receive_result(result: ResultEnvelope) -> dict[str, Any]:
    record = STORE.get(result.order_id)
    if record["command_id"] != result.command_id or record["trace_id"] != result.trace_id:
        raise HTTPException(409, "command or trace reference mismatch")
    record["status"] = OrderStatus.COMPLETED.value if result.status == "completed" else OrderStatus.PARTIALLY_COMPLETED.value
    record["result"] = result.model_dump(mode="json")
    return {"accepted": True, "status": record["status"], "order_id": result.order_id}


@router.post("/integrations/n8n/errors", status_code=status.HTTP_202_ACCEPTED)
async def receive_error(error: ErrorEnvelope) -> dict[str, Any]:
    record = STORE.get(error.order_id)
    if record["command_id"] != error.command_id or record["trace_id"] != error.trace_id:
        raise HTTPException(409, "command or trace reference mismatch")
    record["status"] = OrderStatus.FAILED_RETRYABLE.value if error.retryable else OrderStatus.FAILED_FINAL.value
    record["error_code"] = error.error_code
    return {"accepted": True, "status": record["status"], "order_id": error.order_id}


@router.post("/integrations/n8n/reconciliation", status_code=status.HTTP_202_ACCEPTED)
async def reconcile_order(order: OrderEnvelope) -> dict[str, Any]:
    record = STORE.get(order.order_id)
    return {"accepted": True, "order_id": order.order_id, "canonical_status": record["status"]}
