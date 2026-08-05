"""Small allowlisted JSON condition language; never executes user code."""

from typing import Any

ALLOWED_FIELDS = frozenset(
    {
        "status",
        "priority",
        "provider_health",
        "approval_state",
        "budget_usage",
        "due_at",
        "event_type",
    }
)
ALLOWED_OPERATORS = frozenset({"eq", "ne", "lt", "lte", "gt", "gte", "in"})


def evaluate(rule: dict[str, Any], facts: dict[str, Any]) -> bool:
    if set(rule) != {"field", "operator", "value"}:
        raise ValueError("condition must contain exactly field/operator/value")
    field = rule["field"]
    operator = rule["operator"]
    if field not in ALLOWED_FIELDS or operator not in ALLOWED_OPERATORS:
        raise ValueError("condition field or operator denied")
    if field not in facts:
        return False
    actual = facts[field]
    expected = rule["value"]
    operations = {
        "eq": lambda: actual == expected,
        "ne": lambda: actual != expected,
        "lt": lambda: actual < expected,
        "lte": lambda: actual <= expected,
        "gt": lambda: actual > expected,
        "gte": lambda: actual >= expected,
        "in": lambda: actual in expected if isinstance(expected, list) else False,
    }
    return bool(operations[operator]())
