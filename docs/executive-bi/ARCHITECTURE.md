# Executive BI architecture

The BI platform aggregates authoritative Odoo, middleware, VICIdial, scraper/Postiz and AI service read models. It does not replace those systems. Server A (65.109.65.169) owns KPI definitions, tenant scoping, dashboard APIs, audit and report scheduling; Server B (5.9.108.250) provides advisory AI forecasts; Server C (49.12.145.107) provides marketing read models; Server D (65.21.67.207) provides read-only call analytics.

Production BI and forecasting are disabled until source access, freshness, governance and tenant-isolation evidence exist.
