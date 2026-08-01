# n8n isolated-staging security-risk acceptance package

Status: **unapproved — security-owner decision required**

This package is limited to an isolated, default-off staging environment. It
does not authorize production use, public ingress, workflow activation, live
bindings, customer data, or deployment. Production deployment and activation
remain blocked.

## Immutable image decision

- Selected upstream version: `2.33.3`
- Official Linux amd64 image digest:
  `sha256:e4804b13ae6e2064fa30e5bbfc14b86d0a52eb8a3aa2c351a227314ac90ff666`
- Selection basis: current compatible official 2.x release with the lowest
  observed Trivy HIGH/CRITICAL count on July 31, 2026.
- Trivy: 0 CRITICAL, 8 HIGH.
- Grype: findings differ from Trivy and include image OS packages. Both reports
  must be retained; scanner disagreement is not a pass.

## Trivy HIGH findings

| Advisory | Package | Installed | Fixed version | Runtime presence and staging exploitability |
|---|---|---:|---:|---|
| CVE-2026-14257 | brace-expansion | 2.1.2 | 5.0.8 | Present in n8n's pnpm runtime tree. Exploitation requires attacker-controlled glob/range input reaching the affected library; public ingress and arbitrary workflow execution are denied. |
| CVE-2026-14257 | brace-expansion | 5.0.7 | 5.0.8 | Present in the runtime tree. Same prerequisites and controls as above. |
| CVE-2026-16221 | fast-uri | 3.1.3 | 3.1.4 | Present in the runtime tree. Exploitation requires crafted URI processing; public editor/webhook access and arbitrary egress are denied. |
| CVE-2026-45623 | postcss | 8.5.10 | 8.5.12 | Present in the runtime tree. No untrusted stylesheet build path is authorized in isolated staging. |
| CVE-2026-59887 | linkify-it | 5.0.1 | 5.0.2 | Present in the runtime tree. Exploitation requires crafted text reaching link parsing; no customer content is permitted. |
| CVE-2026-59892 | @opentelemetry/propagator-jaeger | 2.7.1 | 2.9.0 | Present in the runtime tree. External tracing input and public ingress are denied. |
| GHSA-p6gq-j5cr-w38f | nodemailer | 8.0.10 | 9.0.1 | Present in the runtime tree. All email delivery and communication-provider access are disabled and denied. |
| GHSA-r28c-9q8g-f849 | postcss | 8.5.10 | 8.5.18 | Present in the runtime tree. No untrusted stylesheet build path is authorized. |

## Additional Grype HIGH/CRITICAL findings

Grype reported the following additional records. They are not suppressed or
declared false positives. Vendor fixes were not present in the selected
official digest at scan time.

| Advisory | Package | Installed | Grype severity | Fixed version reported | Exposure and mitigation |
|---|---|---:|---|---|---|
| CVE-2025-32460 | graphicsmagick | 1.3.47-r0 | Critical | none reported | Image/media processing is not part of the Lead Automation workflow; no customer files or public ingress are permitted. |
| CVE-2007-0770 | graphicsmagick | 1.3.47-r0 | High | none reported | Same restrictions as above; unexpected file-processing activity is an immediate revocation condition. |
| CVE-2023-52356 | tiff | 4.7.1-r0 | High | none reported | No customer images or TIFF input are permitted. |
| CVE-2026-4775 | tiff | 4.7.1-r0 | High | none reported | No customer images or TIFF input are permitted. |
| GHSA-3jxr-9vmj-r5cp | brace-expansion | 5.0.5 | High | 5.0.7 | Runtime tree; public/editor input denied. |
| GHSA-45rx-2jwx-cxfr | @opentelemetry/propagator-jaeger | 2.7.1 | High | 2.9.0 | External tracing denied. |
| GHSA-6g55-p6wh-862q | postcss | 8.5.10 | High | 8.5.12 | Untrusted stylesheet processing denied. |
| GHSA-mh99-v99m-4gvg | brace-expansion | 2.1.2, 5.0.5, 5.0.7 | High | 5.0.8 | Public/editor input denied. |
| GHSA-p6gq-j5cr-w38f | nodemailer | 8.0.10 | High | 9.0.1 | Communications disabled; provider egress denied. |
| GHSA-r28c-9q8g-f849 | postcss | 8.5.10 | High | 8.5.18 | Untrusted stylesheet processing denied. |
| GHSA-v245-v573-v5vm | linkify-it | 5.0.1 | High | 5.0.2 | No customer text; workflow inactive. |
| GHSA-v2hh-gcrm-f6hx | fast-uri | 3.1.3 | High | 3.1.4 | Public ingress and arbitrary egress denied. |

## Required compensating controls

- Internal Docker network only; no published host ports, DNS route, or Caddy
  route.
- Workflow remains `active=false`; binding remains `enabled=false`.
- n8n editor and external webhook ingress remain inaccessible.
- Read-only root filesystem where supported, `no-new-privileges`, all
  unnecessary Linux capabilities dropped, resource and process limits.
- No access to production PostgreSQL, Redis, Odoo, n8n, Server B, telephony,
  recording systems, or communication providers.
- Synthetic data only; zero customer, production-identifier, and recording
  data.
- Short-lived staging credentials, audit logging, execution alerts, and an
  unexpected-activation kill switch.

These controls reduce exposure but do not remove the vulnerabilities. They
must be verified by commands in the controlled deployment phase before this
acceptance can become effective.

## Acceptance scope and expiry

- Scope: isolated staging only.
- Maximum proposed expiry: **August 30, 2026** (30 days).
- Re-evaluation: daily official-image watch and immediately upon an upstream
  n8n release.
- Upgrade trigger: any compatible official digest that reduces or clears the
  accepted findings.
- Immediate revocation: public ingress, workflow activation, binding enablement,
  customer data, production connectivity, unexpected execution, communication
  attempt, scanner count increase, or compensating-control failure.

No security owner has accepted this package. See
`SECURITY_OWNER_DECISION.md`.
