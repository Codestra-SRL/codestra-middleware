# n8n workflow inventory

The source-controlled inventory contains 51 inactive exports:

| Family | Count |
| --- | ---: |
| Approved-order | 14 |
| Qwen | 11 |
| VICIdial | 14 |
| Postiz | 12 |

`integrations/n8n/cross-system-workflow-registry.json` is the allowlist and is validated one-to-one against the exports. Workflow JSON contains middleware credential references only; provider URLs, database nodes, SQL, and secret values are prohibited by artifact checks.

Live n8n owner/service-identity validation remains operational because the staging public API is disabled. No workflow is activated by repository checks.
