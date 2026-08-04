# Testing and acceptance

Offline acceptance includes schema validation, provider mock adapters, retry/timeout/dead-letter/reconciliation tests, 51-export registry mapping, direct-path scans, and the synthetic cross-system sales flow. The synthetic flow uses test-prefixed records and makes no real call or public post.

Authenticated acceptance is separate and requires owner-provided Qwen, VICIdial, Postiz, and n8n access. The only permitted live call test is one owner-controlled number when explicitly authorized.
