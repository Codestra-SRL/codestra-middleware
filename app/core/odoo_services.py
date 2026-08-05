"""Named Wave 3 service boundaries over the shared durable command contract."""

from dataclasses import dataclass

from app.core.odoo_business import BusinessCommand, SERVICE_RESOURCE_GROUPS


@dataclass(frozen=True)
class BusinessService:
    name: str

    @property
    def resource_types(self) -> frozenset[str]:
        return SERVICE_RESOURCE_GROUPS[self.name]

    def validate(self, command: BusinessCommand) -> None:
        command.validate()
        if command.resource_type not in self.resource_types:
            raise ValueError(f"resource type does not belong to {self.name} service")


CustomerService = BusinessService("customer")
LeadService = BusinessService("lead")
ActivityService = BusinessService("activity")
ProjectService = BusinessService("project")
AppointmentService = BusinessService("appointment")
SupportService = BusinessService("support")
VoiceService = BusinessService("voice")
AIService = BusinessService("ai")
MarketplaceService = BusinessService("marketplace")
CommercialService = BusinessService("commercial")
UsageService = BusinessService("usage")
ReconciliationService = BusinessService("audit")

SERVICES = (
    CustomerService, LeadService, ActivityService, ProjectService,
    AppointmentService, SupportService, VoiceService, AIService,
    MarketplaceService, CommercialService, UsageService, ReconciliationService,
)
