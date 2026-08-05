# Governed production canary plan

Production deployment is blocked until signed release-owner, security-owner,
rollback-authority and maintenance-window approvals exist, approved commit and
image digests are recorded, backups are verified, and isolated restore drills
pass.

The safe initial state is read-only: inference, real HTTP scraping, contact
verification, Odoo creation, VICIdial lead creation/dialing, real recording
processing, Agent Assist real audio, Postiz publishing and automatic production
activation are disabled. Each limited canary must be separately authorized,
bounded, audited, reconciled, and returned to this state.

No production canary was attempted in this environment because all assigned
servers rejected SSH authentication and no signed governance approvals were
available.
