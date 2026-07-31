# Platform security hardening

This repository enforces immutable official image identities, OPA/Conftest
container policy, structured time-limited exceptions, consolidated
vulnerability evidence, CODEOWNERS review, default-off staging controls, and
review-only daily image refreshes.

No policy exception is valid unless its owner and approver appear in
`.security/owners.json`, its repository and staging environment match, its
digest is exact, and its expiry is in the future. Ordinary PR approval is not a
security-risk acceptance.

Release candidates must execute upgrade, tests, rollback, tests, re-upgrade,
and tests using disposable data. Monitoring must alert on migration-head drift,
workflow execution, replay rejection, HMAC failures, quarantine,
reconciliation gaps, unexpected activation, production access,
communications, and recording access.

Production deployment and activation remain separately blocked.
