# n8n lead-result callback authentication

This is the source contract for n8n callbacks to Middleware. It does not authorize workflow import, credential creation, activation, or production use.

## Endpoint and headers

The only accepted endpoint is `POST /api/v1/lead-automation/results`. A trailing slash, query string, encoded-path variant, or any other HTTP method or path is rejected before result processing.

Every request supplies exactly one of each header:

- `X-Service-Identity: codestra-n8n-lead-automation`
- `X-Service-Audience: codestra-middleware-lead-automation`
- `X-Codestra-Timestamp`
- `X-Codestra-Nonce`
- `X-Codestra-Content-SHA256`
- `X-Codestra-Signature`
- `Idempotency-Key`
- `X-Codestra-Environment`

There is no bearer-token fallback. Duplicate authentication headers fail closed.

## Exact signed material

The HMAC-SHA256 input is exactly six newline-separated ASCII values and has no terminal newline:

```text
POST
/api/v1/lead-automation/results
<X-Codestra-Timestamp>
<X-Codestra-Nonce>
<Idempotency-Key>
<lowercase SHA-256 of exact transmitted body bytes>
```

The method is uppercase ASCII and must be exactly `POST`. The path is the undecoded request-target path and must match exactly. Middleware does not normalize a trailing slash, percent-encoding, fragments, or query parameters into the approved path.

The content digest is lowercase hexadecimal SHA-256 over the exact bytes transmitted as the HTTP body. The signature is lowercase hexadecimal HMAC-SHA256 using the runtime callback secret and the canonical material above.

Identity, audience, and environment are validated independently through their required headers. The request environment must equal the result body environment. These controls remain mandatory even though the six-line signed material is intentionally limited to the canonical method, path, timestamp, nonce, idempotency key, and body digest.

## Replay and idempotency

`X-Codestra-Timestamp` is an ISO-8601 timestamp with an explicit timezone and must fall within the Middleware five-minute tolerance. `X-Codestra-Nonce` is single-use within the environment. `Idempotency-Key` is bound into the signature and into result processing. Identical result replay is deterministic; conflicting replay is rejected or quarantined and never creates another Odoo operation.

## Runtime secret delivery

Assign the callback secret at runtime through the approved secret-delivery mechanism. Source workflow exports contain only a credential-name placeholder or runtime reference. They must not contain a secret, live credential ID, token, or private key. The synthetic vector generator at `scripts/generate_lead_callback_auth_test_vector.py` is test-only and cannot be used operationally.

## Failure and retry behavior

Authentication, schema, identity, audience, environment, replay, path, method, and signature failures are permanent and must not be retried automatically. Network timeouts and HTTP `429`, `500`, `502`, `503`, and `504` responses are retryable only within the binding registry's bounded attempt limit. No authentication rejection may reach result processing or cause a state transition.
