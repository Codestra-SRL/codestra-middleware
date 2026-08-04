#!/bin/sh
set -eu

# Docker mounts these files read-only. Values are inherited by the child only;
# they are never printed, serialized into workflow JSON, or written to disk.
QUEUE_BULL_REDIS_USERNAME=$(cat /run/secrets/redis-n8n-username)
QUEUE_BULL_REDIS_PASSWORD=$(cat /run/secrets/redis-n8n-password)
export QUEUE_BULL_REDIS_USERNAME QUEUE_BULL_REDIS_PASSWORD
export HOME=/home/node
export N8N_USER_FOLDER=/home/node/.n8n

# The explicit argv terminator and "$@" preserve every argument literally,
# including worker flags beginning with '-'. No shell interpolation occurs.
exec su -p node -s /bin/sh -c 'exec /docker-entrypoint.sh "$@"' n8n-entrypoint "$@"
