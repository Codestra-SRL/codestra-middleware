# Postly API credential rotation

1. Open an approved change ticket; identify all Middleware consumers from the secret manager, never from logs.
2. Verify the latest encrypted backup and rollback reference.
3. Rotate the organization API key using the supported Postiz organization-admin mechanism.
4. Write the new value directly to the Middleware secret manager; record only its secret reference and SHA-256 fingerprint.
5. Reload the adapter without printing environment values and perform only `GET /public/v1/integrations`.
6. Confirm the previous key returns 401, audit actor/time/old and new fingerprints, and monitor authentication failures.
7. On failure, disable adapter writes and investigate; do not paste either key into tickets, Git, n8n JSON, or shell arguments.
