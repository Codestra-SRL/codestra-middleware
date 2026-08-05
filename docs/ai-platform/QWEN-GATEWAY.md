# Qwen Gateway staging contract

Middleware and n8n use a private, authenticated OpenAI-compatible gateway. The gateway endpoint is configured by `AI_GATEWAY_BASE_URL`; its API key is read from `AI_GATEWAY_API_KEY_FILE`. This checkout does not contain the server address or key.

The middleware client enforces a 120-second default timeout, two-connection pool, health checks, model labels, and safe error metrics. Qwen remains `TESTING`; public inference exposure is not permitted.
