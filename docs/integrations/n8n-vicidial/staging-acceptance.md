# Staging acceptance checklist

1. Verify root-only secret mounts without printing values.
2. Verify n8n owner/service identity and approved project scope.
3. Run signed callback rejection tests.
4. Run authenticated Qwen synthetic tasks.
5. Run VICIdial non-call fixtures and, only with owner authorization, one test number call.
6. Run Postiz draft-only tests with publication disabled.
7. Run the authenticated synthetic lead twice.
8. Restore every workflow and feature flag to inactive/false.
