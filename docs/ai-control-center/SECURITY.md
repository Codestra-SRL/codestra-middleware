# Security

Production actions and feature-flag writes are disabled by default. The UI
does not store service credentials, uses no direct internal-service URLs, and
does not expose protected recordings or raw AI payloads. High-risk mutations
must use existing middleware authorization and audit paths.
