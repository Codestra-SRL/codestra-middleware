# Postly social staging bindings

These bindings keep n8n limited to content-generation and workflow duties.
n8n cannot schedule, publish, reconcile, or receive a Postly credential.

The bindings are default-off. Middleware resolves the workflow reference; no
workflow ID is exposed in an application-facing URL. Activation requires an
imported staging workflow, registered credential references, schema validation,
and an explicit staging approval.

Production activation and direct `n8n -> Postly` access are prohibited.
