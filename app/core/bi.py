"""Versioned, explainable KPI contracts for Executive BI."""
from dataclasses import dataclass


@dataclass(frozen=True)
class KPIContract:
    code: str
    name: str
    unit: str
    definition: str
    source: str
    owner: str
    guardrail: str | None = None


KPI_CONTRACTS = (
    KPIContract("revenue", "Revenue", "currency", "Sum of posted customer invoice totals in the selected period.", "odoo.account.move", "finance"),
    KPIContract("open_leads", "Open leads", "count", "Count of tenant-scoped leads not in a terminal stage.", "odoo.crm.lead", "sales"),
    KPIContract("call_answer_rate", "Call answer rate", "ratio", "Answered calls divided by attempted calls for the selected period.", "vicidial.call_log", "operations", "must not be inferred when attempts are incomplete"),
    KPIContract("open_tickets", "Open tickets", "count", "Count of tenant-scoped support tickets not closed.", "odoo.helpdesk.ticket", "customer_success"),
    KPIContract("ai_job_success_rate", "AI job success rate", "ratio", "Completed AI jobs divided by terminal AI jobs.", "middleware.ai_job", "platform", "schema-valid output is a separate quality KPI"),
)


def kpi_contract(code: str) -> KPIContract:
    for contract in KPI_CONTRACTS:
        if contract.code == code:
            return contract
    raise KeyError(code)
