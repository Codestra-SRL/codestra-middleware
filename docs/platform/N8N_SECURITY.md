# n8n security

Allowed nodes are Codestra private nodes and explicitly reviewed n8n core nodes. Execute Command, SSH, arbitrary Code and filesystem-write nodes are prohibited by CI policy. Direct provider and Odoo-write references, embedded credentials, missing audit callback and missing dead-letter routes fail validation.

`CdstN8nSecurityAuditV1` is inactive until staged. It records findings without deleting workflows. HIGH/CRITICAL findings require an operations alert and human containment decision.
