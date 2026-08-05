from app.core.data_integration import (
    ConnectorRequest,
    DataRecord,
    authorize_connector,
    idempotency_is_new,
    retry_allowed,
    validate_data_record,
)


def test_data_records_require_classification_and_scope():
    assert validate_data_record(DataRecord("t1", "w1", "CUSTOMER", "c1", "INTERNAL", "odoo"))
    assert not validate_data_record(DataRecord("t1", "w1", "CUSTOMER", "c1", "UNKNOWN", "odoo"))


def test_connectors_are_sandboxed_permissioned_and_idempotent():
    req = ConnectorRequest("t1", "w1", "odoo", "v1", "k1", True, True)
    assert authorize_connector(req) == (True, "VALID")
    assert authorize_connector(ConnectorRequest("t1", "w1", "odoo", "v1", "k1", False, True))[1] == "PRODUCTION_CONNECTOR_DISABLED"
    assert authorize_connector(ConnectorRequest("t1", "w1", "odoo", "v1", "k1", True, False))[1] == "PERMISSION_DENIED"
    assert idempotency_is_new(existing_key=None, request_key="k1")
    assert not idempotency_is_new(existing_key="k1", request_key="k1")
    assert retry_allowed(retryable=True, attempt=0, max_attempts=2)
    assert not retry_allowed(retryable=True, attempt=2, max_attempts=2)
