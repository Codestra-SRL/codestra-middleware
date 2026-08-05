"""Typed Odoo business adapter boundary; production delivery is fail-closed."""

from dataclasses import dataclass
from typing import Protocol

from app.core.odoo_business import BusinessCommand


@dataclass(frozen=True)
class DeliveryResult:
    status: str
    remote_model: str | None = None
    remote_id: int | None = None
    remote_version: str | None = None


class OdooBusinessAdapter(Protocol):
    async def deliver(self, command: BusinessCommand) -> DeliveryResult: ...


class DisabledOdooBusinessAdapter:
    async def deliver(self, command: BusinessCommand) -> DeliveryResult:
        command.validate()
        return DeliveryResult(status="DISABLED")


class MockOdooBusinessAdapter:
    """Synthetic adapter for disposable tests; it never opens a network socket."""

    async def deliver(self, command: BusinessCommand) -> DeliveryResult:
        command.validate()
        return DeliveryResult(
            status="SUCCEEDED",
            remote_model=f"mock.{command.resource_type}",
            remote_id=abs(hash((command.resource_type, command.resource_key))) % 1_000_000 + 1,
            remote_version="synthetic-v1",
        )
