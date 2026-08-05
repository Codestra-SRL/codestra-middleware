# Loan and financial-services architecture

Server A (`65.109.65.169`) owns tenant-scoped applicants, applications, consent, documents, matching, review, servicing, audit, and reconciliation. Server B (`5.9.108.250`) provides private middleware-controlled document and summary AI. Server C (`49.12.145.107`) provides approved routing and health checks. Server D (`65.21.67.207`) provides narrowly scoped call-center integration.

Real providers, lender submission, servicing handoff, production notifications, and production activation remain disabled.
