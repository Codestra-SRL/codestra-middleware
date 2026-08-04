#!/bin/sh
set -eu

# Docker mounts these files read-only. Values are inherited by the child only;
# they are never printed, serialized into workflow JSON, or written to disk.
USERNAME_FILE=/run/secrets/redis-n8n-username
PASSWORD_FILE=/run/secrets/redis-n8n-password
for secret_file in "$USERNAME_FILE" "$PASSWORD_FILE"; do
  if [ ! -r "$secret_file" ] || [ ! -s "$secret_file" ]; then
    echo "Required Redis secret is missing or unreadable: $secret_file" >&2
    exit 1
  fi
done
QUEUE_BULL_REDIS_USERNAME=$(cat "$USERNAME_FILE")
QUEUE_BULL_REDIS_PASSWORD=$(cat "$PASSWORD_FILE")
export QUEUE_BULL_REDIS_USERNAME QUEUE_BULL_REDIS_PASSWORD
export HOME=/home/node
export N8N_USER_FOLDER=/home/node/.n8n

# The helper receives the original argv after an explicit terminator; no shell
# interpolation or flattened argument string is used.
exec su -p node -s /usr/local/bin/n8n-node-entrypoint -- "$@"
