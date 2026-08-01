# Isolated Lead Automation staging architecture

The future project name is `codestra-lead-staging`. Its network is internal,
publishes no host ports, and has unique PostgreSQL, Redis, Odoo, n8n, and
Middleware volumes. It must never attach to existing Codestra networks.

Middleware and Odoo use separate PostgreSQL containers and databases. Redis is
dedicated to this project. Odoo addons must come from exact commit
`f3a51feff8b06021bead395add82a5c5aed45ee5`; the next Middleware candidate must
use an image built from `f48761d35f1c88b3a9960484cc7252f10644916b`. There is no public ingress,
production DNS, Caddy route, Server B route, telephony route, communication
provider, live n8n connection, or production database route.

All persistent services are behind the `deployment` profile. Rendering the
manifest does not create or start them. Initial deployment remains a separate
authorized phase.
