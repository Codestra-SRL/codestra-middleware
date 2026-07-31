# Isolated Lead Automation staging architecture

The future project name is `codestra-lead-staging`. Its network is internal,
publishes no host ports, and has unique PostgreSQL, Redis, Odoo, n8n, and
Middleware volumes. It must never attach to existing Codestra networks.

Middleware and Odoo use separate PostgreSQL containers and databases. Redis is
dedicated to this project. Odoo addons must come from exact commit
`7c4a7c5444fc90f784bb87606a1b5d8f9de8275a`; Middleware must use an image built
from `1d7c72594536d4cd0c47f5e437a6d7e3a42756f4`. There is no public ingress,
production DNS, Caddy route, Server B route, telephony route, communication
provider, live n8n connection, or production database route.

All persistent services are behind the `deployment` profile. Rendering the
manifest does not create or start them. Initial deployment remains a separate
authorized phase.

