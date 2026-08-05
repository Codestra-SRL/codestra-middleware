# Firewall Matrix

| Source | Destination | Port | Required result | Observed from middleware |
|---|---|---:|---|---|
| Internet | Middleware | 22 | approved administration | open |
| Internet | Middleware | 80 | ACME/redirect | open |
| Internet | Middleware | 443 | public HTTPS | open |
| Internet | middleware databases/internal apps | any | deny | no public listeners |
| Qwen 10.40.0.4 | Middleware 10.40.0.1 | 443 | mTLS/HMAC only | policy configured; remote matrix pending |
| other private source | Qwen verifier route | 443 | deny | Caddy source matcher configured |
| Middleware 10.40.0.1 | VICIdial 10.40.0.2 | 8443 | allow restricted adapter | unreachable |
| VICIdial 10.40.0.2 | Middleware 10.40.0.1 | 443 | allow callback route only | reverse test pending |
| Browser | Qwen/Ollama/LiteLLM | any | deny | no middleware proxy route |

The host uses UFW default deny incoming/routed and allow outgoing. Docker's
forward path also contains an explicit 10.250.240.0/28 to 10.40.0.2:8443
allow rule. Firewall changes were not made during this inventory.
