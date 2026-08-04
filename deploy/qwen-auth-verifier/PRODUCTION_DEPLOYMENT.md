# Qwen verifier production deployment

This package deploys only the signed read-only authentication verifier. It
does not deploy the Qwen worker, enable a job API, or authorize business writes.

## Immutable inputs

- Image: `ghcr.io/codestra-srl/qwen-auth-verifier@sha256:a0423439705ee7f3466666e5d999b318067159335cbbd88dc9a1b5a4c2ffeaef`
- Private source: `10.40.0.4/32`
- Private route: `POST /internal/api/v1/ai/auth/verify`
- Caddy-to-verifier network: `10.250.241.0/29`, internal, with Caddy at
  `10.250.241.2` and the verifier at `10.250.241.3`

The dedicated network prevents another application container from supplying a
spoofed client-certificate header. The verifier trusts only Caddy's fixed `/32`.
Neither Compose file publishes a verifier port.

## Required preflight

1. Independently verify the exact image signature and all approved
   attestations.
2. Back up the live Compose and Caddy files, including SHA-256 checksums.
3. Require the HMAC and client-CA inputs to be regular, non-symlink files owned
   by root and no more permissive than `0600`.
4. Grant only UID 10001 read ACLs on those two source files. Record the prior
   ACLs and remove the grants during rollback.
5. Create `codestra_qwen_auth_private` with `--internal` and subnet
   `10.250.241.0/29`; stop if that subnet overlaps any route or Docker network.
6. Validate the combined live Compose plus reverse-proxy overlay and the
   verifier Compose before applying either.
7. Insert `Caddyfile.production.snippet` inside the existing private mTLS
   `route` block immediately before the VICIdial matcher. Do not modify the
   VICIdial matcher.
8. Validate Caddy before reload and arm an automatic rollback first.

## Acceptance

- The verifier container is healthy and has no published port.
- Caddy and the verifier are the only members of the dedicated network.
- Public-interface requests cannot reach the route.
- Private requests from any source except `10.40.0.4` return `403`.
- Valid Qwen mTLS/HMAC succeeds; all negative cases fail closed.
- A nonce remains rejected after verifier restart.
- Existing VICIdial configuration and behavior remain unchanged.

## Rollback

1. Restore the backed-up Caddy and live Compose files and validate them.
2. Recreate only the reverse proxy from the restored Compose configuration.
3. Stop and remove only the Qwen verifier Compose project.
4. Disconnect and remove `codestra_qwen_auth_private` after confirming it has
   no endpoints.
5. Remove only the two UID 10001 ACL entries added during deployment.
6. Preserve the replay volume, signed evidence, and middleware-controlled
   identity files.
7. Confirm the public route, private VICIdial route, and write-disable flags are
   unchanged.
