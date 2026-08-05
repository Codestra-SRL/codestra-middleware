# Workflow results

Results are accepted only from the authenticated n8n result writer. The result endpoint checks job/tenant correlation, timestamp, nonce, schema, and terminal-state rules. Duplicate completed results are acknowledged without repeating side effects.
