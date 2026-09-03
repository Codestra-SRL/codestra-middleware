# Firewall matrix

Default inbound and routed policy must remain deny.

| Destination | Port | Sources | Purpose |
|---|---:|---|---|
| A | 22/tcp | B and D private; approved stable C source; emergency management until matrix passes | SSH administration |
| A | 80,443/tcp | Approved public clients | HTTP redirect/certificate and HTTPS |
| B | 22/tcp | A private | SSH administration |
| B | approved private HTTPS only | A private | AI gateway; no public AI runtime ports |
| C | 22/tcp | A stable public source until private route exists | SSH administration |
| C | 80,443/tcp | Public | Websites and HTTPS gateway |
| D | 22/tcp | A private | SSH administration |
| D | reviewed private application port | A/B private as specifically approved | Telephony/media adapter |

Never expose PostgreSQL, Redis, Qdrant, Ollama, LiteLLM, AMI, ARI, internal
administrative APIs, or SIP management publicly.

Server A currently has UFW default deny but public TCP/22 remains allowed. Do
not remove that emergency path until all replacement paths are proven from
independent sessions.
