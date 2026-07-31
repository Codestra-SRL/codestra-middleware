# Security Scorecard

| Control | Status | Evidence |
|---|---|---|
| Image Security | PASS | Immutable inventory and mutable-tag policy |
| SBOM | WARN | Generated per candidate image by refresh workflow |
| Dependencies | PASS | Trivy and Grype consolidation defined |
| Secrets | PASS | Secret references only; literal-secret policy |
| Supply Chain | PASS | Digest, SBOM, provenance and scanner inventory |
| HMAC | PASS | Existing contracts unchanged |
| Default-Off | PASS | Fail-closed flag validation |
| Replay Protection | PASS | Existing controls unchanged |
| Policy Engine | PASS | OPA/Conftest and Python fail-closed gates |
| Rollback | PASS | Upgrade/test/rollback/test/upgrade/test required |
| Migration | PASS | Migration state monitoring required |
| Recording Isolation | PASS | Recording implementation excluded |
| Communication Isolation | PASS | Communication routes denied in staging |
