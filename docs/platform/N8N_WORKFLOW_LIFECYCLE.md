# n8n workflow lifecycle

Git JSON under `integrations/n8n/workflows` is authoritative. Each file includes owner, schemas, version, credentials, node inventory, risk, production eligibility, rollback version and enabled events.

Run `python -m app.tools.validate_n8n_workflows`. Development permits local editing; staging imports an exact Git SHA for synthetic tests; production requires reviewed immutable artifacts. Deployment records bind workflow/version/SHA/environment/deployer/previous version/rollback pointer. Drift compares canonical JSON hashes and alerts rather than overwriting n8n.
