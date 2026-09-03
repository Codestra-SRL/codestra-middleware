# Codestra Network Topology

## Physical and VLAN view

```mermaid
flowchart LR
  VS[Hetzner vSwitch / VLAN 4001]
  MW[Middleware\n65.109.65.169\n10.40.0.1]
  VI[VICIdial\n65.21.67.207\nexpected 10.40.0.2]
  QW[Qwen\n5.9.108.250\n10.40.0.4]
  WEB[Web zone\n49.12.145.107\nno registered private IP]
  MW --- VS
  VI -. currently unreachable .- VS
  QW --- VS
  WEB -. public network only .- MW
```

## Logical service dependencies

```mermaid
flowchart TD
  Browser -->|HTTPS 443| Caddy
  Caddy --> IAM[Keycloak]
  Caddy --> MW[Middleware]
  Caddy --> Odoo
  Caddy --> N8N[n8n]
  Qwen -->|private mTLS/HMAC 443| Caddy
  MW -->|private mTLS 8443| VIC[VICIdial adapter]
  MW -->|public HTTPS, allowlisted contracts| Web[Web/Marketplace zone]
```

No overlay network is configured. Docker networks are local bridges. The
private verifier network is `codestra_qwen_auth_private` (10.250.241.0/29):
Caddy is 10.250.241.2 and the verifier is 10.250.241.3. Telephony provisioning
uses `codestra-provisioning-service_telephony_private` (10.250.240.0/28).
