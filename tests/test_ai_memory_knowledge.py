from app.core.ai_memory_knowledge import (
    RetrievalCandidate,
    RetrievalContext,
    authorize_promotion,
    authorize_retrieval,
    citation_is_resolvable,
    filter_candidate,
)


def context(**kwargs):
    values = dict(tenant_id="t1", workspace_id="w1", employee_id="e1", permissions=frozenset(), requested_scope="WORKSPACE")
    values.update(kwargs)
    return RetrievalContext(**values)


def test_retrieval_requires_complete_context_and_active_policy():
    assert authorize_retrieval(context())
    assert not authorize_retrieval(context(tenant_id=""))
    assert not authorize_retrieval(context(source_states=frozenset({"ACTIVE", "EXPIRED"})))


def test_candidate_filter_blocks_cross_scope_and_invalid_source_states():
    allowed = RetrievalCandidate("t1", "w1", "INTERNAL", "ACTIVE")
    assert filter_candidate(context(), allowed)
    assert not filter_candidate(context(), RetrievalCandidate("t2", "w1", "INTERNAL", "ACTIVE"))
    assert not filter_candidate(context(), RetrievalCandidate("t1", "w1", "INTERNAL", "REVOKED"))
    assert not filter_candidate(context(), RetrievalCandidate("t1", "w1", "INTERNAL", "ACTIVE", expired=True))


def test_memory_promotion_requires_human_review_and_source():
    assert authorize_promotion(human_approved=True, source_backed=True, classification="INTERNAL", contains_secret=False)
    assert not authorize_promotion(human_approved=False, source_backed=True, classification="INTERNAL", contains_secret=False)
    assert not authorize_promotion(human_approved=True, source_backed=True, classification="SECRET", contains_secret=False)
    assert not authorize_promotion(human_approved=True, source_backed=True, classification="INTERNAL", contains_secret=True)


def test_citations_must_resolve_to_active_versioned_sources():
    assert citation_is_resolvable(source_id="s1", source_version="v1", state="ACTIVE", citation_label="Policy §1")
    assert not citation_is_resolvable(source_id="s1", source_version="v1", state="REVOKED", citation_label="Policy §1")
