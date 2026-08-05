from app.core.orchestration_contracts import WorkflowContext, callback_allowed, retryable_failure, valid_transition, valid_workflow_context
from app.core.redis_state import RedisKeyContext, namespace_ttl_required, redis_command_allowed, redis_key


def test_workflow_context_transition_and_retry_are_bounded():
    context = WorkflowContext("CDA-WF-00", "v1", "t", "w", "cmd", "corr", "trace", "idem-1234")
    assert valid_workflow_context(context)
    assert valid_transition("QUEUED", "EXECUTING")
    assert retryable_failure("TIMEOUT", 0, 3)
    assert not retryable_failure("AUTHORIZATION_FINAL", 0, 3)


def test_callback_and_redis_guards_fail_closed():
    assert callback_allowed(known_workflow=True, known_execution=True, tenant_match=True, workspace_match=True, signature_valid=True, replay=False, result_state="SUCCEEDED") == (True, "VALID")
    assert callback_allowed(known_workflow=True, known_execution=True, tenant_match=True, workspace_match=True, signature_valid=True, replay=True, result_state="SUCCEEDED")[0] is False
    key = redis_key(RedisKeyContext("staging", "t", "w", "workflows", "queue", "core"))
    assert key.startswith("codestra:staging:t:w:workflows:")
    assert namespace_ttl_required("voice")
    assert not redis_command_allowed("FLUSHALL")
