# Service permission matrix

| Identity | Allowed boundary | Explicitly denied |
| --- | --- | --- |
| n8n router/result | Middleware workflow and result APIs | Provider APIs, databases, user/admin APIs |
| command worker | Middleware command store and adapter network | Public provider endpoints, direct databases |
| outbox worker | Middleware outbox and n8n webhook | Provider databases |
| VICIdial adapter | Middleware-authenticated commands and approved VICIdial API | n8n direct access, SQL, predictive dialing |
| event collector | Approved read/event source and middleware ingest | Middleware database direct writes |
