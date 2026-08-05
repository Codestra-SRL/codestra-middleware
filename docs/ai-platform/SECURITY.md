# Security

Requests require existing middleware authentication and tenant headers. n8n result callbacks additionally require timestamp, nonce, service identity, and HMAC-SHA256 over `timestamp.raw_body`. Nonces prevent replay. Sensitive input keys are rejected before persistence.
