# Qwen worker deployment handoff

Run this only from the local Codex session on the Qwen deployment zone (`10.40.0.4`). Do not request administrative SSH to middleware or the web host.

## Fixed contract

- Middleware address: `https://10.40.0.1:443`
- TLS SNI: `middleware.internal.codestra.agency`
- Worker service: `qwen-ai-01`
- Certificate serial: `3001`
- SPIFFE ID: `spiffe://codestra.internal/service/qwen-ai-01`
- Required scopes: `ai.auth ai.worker`
- Verification endpoint: `POST /internal/api/v1/ai/auth/verify`
- Worker endpoints: claim, heartbeat, chunks, complete, fail, and cancellation check under `/internal/api/v1/ai/worker/`

## Safety

1. Inventory LiteLLM and Ollama locally. Record versions, immutable images, health, bind addresses, model inventory, and resource limits without printing credentials or prompts.
2. Require LiteLLM and Ollama to bind only to loopback or a private container network. Do not open inbound application ports.
3. Obtain the reviewed worker from its signed repository release or immutable GHCR digest. Verify Cosign identity, issuer, transparency log, SBOM, provenance, and VEX before installation.
4. Use these local protected files, supplied by the operator:
   - CA certificate
   - client certificate with serial `3001`
   - client private key
   - HMAC secret for key reference `qwen-ai-01-hmac-20260804-01`
5. Secret directories must be root-owned mode `0700`; secret files must be root-owned mode `0600`. Mount them read-only. Never copy their values into environment files, logs, Git, unit files, or evidence.
6. The worker must poll outbound only, validate server TLS with SNI, use bounded connect/read timeouts, renew leases before expiry, and persist no prompt/output logs.

## Required verification

- Positive: valid mTLS identity, current timestamp, unique nonce, exact scopes, and valid raw-body HMAC returns verified.
- Negative: wrong service, serial, SPIFFE ID, scope, source, body hash, or signature is rejected.
- Expiry: timestamp beyond the allowed skew is rejected.
- Replay: reusing a nonce is rejected.
- Fencing: a stale fencing token cannot heartbeat, append, complete, or fail a job.
- Recovery: terminate a synthetic worker after claim; verify lease expiry and exactly one later reclaim.
- Idempotency: repeat a chunk sequence and completion; verify no duplicate persisted output.
- External-write count remains zero.

## systemd requirements

Create a hardened unit using `DynamicUser=yes` where compatible, `NoNewPrivileges=yes`, `PrivateTmp=yes`, `ProtectSystem=strict`, `ProtectHome=yes`, a read-only secret mount, a bounded stop timeout, restart backoff, and an explicit network allowlist for `10.40.0.1:443`. Start only after tests pass. Confirm no listening application socket with `ss -lntup`.

Return immutable worker identity, unit status, positive/negative/replay evidence, open-port inventory, and zero-write counters. Do not include secrets.
