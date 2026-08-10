# Lead domain

`LeadRecord` links tenant-scoped canonical people and companies to campaign context. Provider status names do not become lead states. The canonical lifecycle is `NEW`, `IDENTIFYING`, `QUALIFYING`, `QUALIFIED`, `NURTURE`, `CONTACT_READY`, `CONTACTED`, `APPOINTMENT`, `OPPORTUNITY`, `WON`, `LOST`, `DISQUALIFIED`, `DNC`, and `ARCHIVED`.

`LeadInteraction` is append-only and deduplicated by tenant, source, and source event. Payloads are allowlisted summaries rather than raw provider bodies. The same canonical identity may have a separate lead only where explicit campaign policy requires it.
