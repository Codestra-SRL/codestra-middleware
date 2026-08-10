from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Protocol


AI_TASKS = frozenset(
    {
        "content_generation",
        "rewrite",
        "translation",
        "classification",
        "lead_scoring",
        "intent_detection",
        "sentiment",
        "spam_detection",
        "content_risk",
        "campaign_analysis",
        "optimization_recommendation",
    }
)


@dataclass(frozen=True)
class AIRequest:
    task: str
    template_version: str
    minimized_input: dict[str, Any]
    correlation_id: str

    @property
    def input_hash(self) -> str:
        return hashlib.sha256(
            repr(sorted(self.minimized_input.items())).encode()
        ).hexdigest()


class AIProvider(Protocol):
    async def execute(self, request: AIRequest) -> dict[str, Any]: ...


class DisabledAIProvider:
    async def execute(self, request: AIRequest) -> dict[str, Any]:
        raise RuntimeError("AI_PROVIDER_DISABLED")


def minimize_ai_input(values: dict[str, Any]) -> dict[str, Any]:
    prohibited = {"token", "secret", "password", "oauth", "api_key", "email", "phone"}
    return {
        key: value for key, value in values.items() if key.casefold() not in prohibited
    }


def optimization_recommendation(
    metrics: dict[str, float], baseline: dict[str, float]
) -> dict[str, Any]:
    engagement = metrics.get("engagements", 0) / max(metrics.get("impressions", 0), 1)
    previous = baseline.get("engagements", 0) / max(baseline.get("impressions", 0), 1)
    action = "KEEP" if engagement >= previous else "TEST_VARIANT"
    return {
        "action": action,
        "evidence": {"engagement_rate": engagement, "baseline_rate": previous},
        "requires_approval": True,
    }
