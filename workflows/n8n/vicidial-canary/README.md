# VICIdial campaign canary workflows

The CDA-AI-11 workflow set is governance-only and inactive. Middleware owns
authorization, dialing-window checks, capacity checks, one-lead/one-call limits,
and emergency stop. No workflow in this directory places a call or activates a
campaign. Credentials are supplied only by the deployment secret manager.
