# Runbook

If a gate fails, pause mutations, preserve audit and outbox state, verify service
health, and roll back the release or feature flag. Do not repair state by direct
database edits.
