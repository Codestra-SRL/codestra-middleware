# Deployment strategies

Supported strategies are staging-only, feature-flag, canary, blue/green,
rolling, maintenance-window, and emergency hotfix.

Canaries must be bounded to an internal extension, test campaign, named agent
group, or approved test DID. Blue/green and rolling releases require a tested
rollback target and health monitoring. Emergency hotfixes require the same
evidence and post-implementation review; emergency status does not bypass
authorization.
