import pytest

from app.core.ai_schema_registry import validate_result_schema


def test_registered_schema_accepts_bounded_fields():
    validate_result_schema("lead_score_v1", {"confidence": 0.8, "lead_score": 72.5})


@pytest.mark.parametrize("schema", ["unknown_v1", "lead_score_v9"])
def test_unknown_schema_rejected(schema):
    with pytest.raises(ValueError, match="unknown"):
        validate_result_schema(schema, {})


def test_out_of_range_score_rejected():
    with pytest.raises(ValueError, match="lead_score"):
        validate_result_schema("lead_score_v1", {"lead_score": 101})

