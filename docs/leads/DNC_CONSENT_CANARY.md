# DNC and consent canary

Policy order is fail-closed:

1. A confirmed DNC state returns `DO_NOT_CONTACT` regardless of score, intent, or channel availability.
2. Consent other than `GRANTED` returns `MANUAL_REVIEW` and `eligible_for_contact=false`.
3. Spam returns `DO_NOT_CONTACT` even when contact data and consent are otherwise present.
4. Support intent returns `SUPPORT_HANDOFF`, never a sales-dial recommendation.

These cases are deterministic and run without AI or external policy providers. No workflow may override DNC, reinterpret public availability as consent, or execute the recommended action during Phase N8.
