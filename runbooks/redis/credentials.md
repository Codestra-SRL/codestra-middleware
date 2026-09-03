# Credentials and rotation

Generate separate middleware, n8n, and recovery credentials. Store them as
root-owned mode-0600 secrets, add the new ACL identity, validate health and
isolation, rotate mounts, then revoke the old identity. Never put values in
Compose environment, workflows, logs, or Git.
