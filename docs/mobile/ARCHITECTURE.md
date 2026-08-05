# Codestra Mobile architecture

Mobile clients call only the middleware API on 65.109.65.169. Server B (5.9.108.250) provides private AI services through middleware, Server C (49.12.145.107) provides links/assets and health, and Server D (65.21.67.207) provides read-only telephony data. No mobile client receives database, SSH, Qwen, Qdrant, n8n, Odoo, VICIdial or Asterisk access.
