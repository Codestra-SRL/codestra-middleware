"""Outbox claim primitive; adapters remain disabled in this phase."""

from sqlalchemy import text

CLAIM_SQL = text("""SELECT id, event_id, target FROM integration_delivery
WHERE status = 'queued' ORDER BY next_attempt_at NULLS FIRST
FOR UPDATE SKIP LOCKED LIMIT :limit""")
