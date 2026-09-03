# Production lifecycle scope v1

Continuous delivery remains disabled. Read-only discovery found no existing
non-fixture campaign, extension, and dialplan-context tuple that is both able to
produce lifecycle traffic and isolated from trunks, transfers, queues,
conferences, callbacks, service codes, or external workflow integrations.

The narrowest candidate is inactive campaign `P3TST001`, agent group `P3TEST`,
no assigned extension, no approved context, and observation-only direction.
This is a design scope, not an activation scope. A live canary requires business
approval and a separately reviewed exact extension plus a closed context with
no includes, trunks, AGIs, transfers, queues, conferences, voicemail, emergency
routes, or customer destinations.

Schema 1 currently has no campaign field, and repository business-unit
taxonomies conflict. Campaign/business-unit attribution must be resolved before
producer implementation.
