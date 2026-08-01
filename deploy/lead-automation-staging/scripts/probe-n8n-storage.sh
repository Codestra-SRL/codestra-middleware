#!/usr/bin/env bash
set -euo pipefail

image="${N8N_IMAGE:?exact digest-pinned n8n image required}"
case "${image}" in *@sha256:????????????????????????????????????????????????????????????????) ;; *) exit 1;; esac
suffix="${GITHUB_RUN_ID:-local}-$$"
container="lead-n8n-probe-${suffix}"
network="lead-n8n-probe-net-${suffix}"
volume="lead-n8n-probe-data-${suffix}"
secret_dir="$(mktemp -d)"
cleanup() {
  docker stop "${container}" >/dev/null 2>&1 || true
  docker rm "${container}" >/dev/null 2>&1 || true
  docker volume rm "${volume}" >/dev/null 2>&1 || true
  docker network rm "${network}" >/dev/null 2>&1 || true
  chmod -R u+rwX "${secret_dir}" 2>/dev/null || true
  find "${secret_dir}" -depth -delete
}
trap cleanup EXIT
printf 'synthetic-n8n-probe-key-not-operational' > "${secret_dir}/n8n-encryption-key"
chmod 0400 "${secret_dir}/n8n-encryption-key"
docker network create --internal "${network}" >/dev/null
docker volume create "${volume}" >/dev/null
docker create --name "${container}" --network "${network}" --read-only --user 0:0 \
  --cap-drop ALL --cap-add CHOWN --cap-add DAC_OVERRIDE --cap-add FOWNER \
  --cap-add SETGID --cap-add SETUID \
  --security-opt no-new-privileges --pids-limit 256 --memory 1g --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m \
  --tmpfs /home/node/.cache:rw,noexec,nosuid,nodev,size=64m \
  --mount "type=volume,src=${volume},dst=/home/node/.n8n" \
  --mount "type=bind,src=${secret_dir}/n8n-encryption-key,dst=/run/secrets/n8n_encryption_key,readonly" \
  -e N8N_DIAGNOSTICS_ENABLED=false -e N8N_VERSION_NOTIFICATIONS_ENABLED=false \
  -e N8N_TEMPLATES_ENABLED=false -e N8N_WORKFLOW_ACTIVE_DEFAULT=false \
  --entrypoint /bin/sh "${image}" -ec \
  'node -e '\''const fs=require("fs"); const p="/home/node/.n8n/config"; const key=fs.readFileSync("/run/secrets/n8n_encryption_key","utf8").trim(); const cfg=fs.existsSync(p)?JSON.parse(fs.readFileSync(p,"utf8")):{}; if(cfg.encryptionKey&&cfg.encryptionKey!==key)process.exit(78); cfg.encryptionKey=key; fs.writeFileSync(p,JSON.stringify(cfg),{mode:384}); fs.chownSync(p,1000,1000)'\''; exec su node -s /bin/sh -c '\''exec /docker-entrypoint.sh start'\''' >/dev/null
docker start "${container}" >/dev/null
for _ in $(seq 1 60); do
  test "$(docker inspect -f '{{.State.Running}}' "${container}")" = true || { docker logs "${container}" >&2; exit 1; }
  docker exec "${container}" sh -ec 'test -s /home/node/.n8n/config' 2>/dev/null && break
  sleep 2
done
for _ in $(seq 1 60); do
  docker exec "${container}" wget -q -O- http://127.0.0.1:5678/healthz >/dev/null 2>&1 && break
  sleep 2
done
docker exec "${container}" wget -q -O- http://127.0.0.1:5678/healthz >/dev/null
test "$(docker exec "${container}" sh -ec 'awk '\''/^[[:space:]]*Uid:/{print $2}'\'' /proc/1/status')" = 1000
docker exec "${container}" sh -ec 'test -s /home/node/.n8n/config; node -e '\''const {DatabaseSync}=require("node:sqlite"); const db=new DatabaseSync("/home/node/.n8n/database.sqlite",{readOnly:true}); const row=db.prepare("SELECT COUNT(*) AS total FROM workflow_entity WHERE active = 1").get(); if (Number(row.total) !== 0) process.exit(1)'\'''
first="$(docker exec "${container}" sha256sum /home/node/.n8n/config | awk '{print $1}')"
docker restart "${container}" >/dev/null
for _ in $(seq 1 60); do
  test "$(docker inspect -f '{{.State.Running}}' "${container}")" = true || exit 1
  docker exec "${container}" sh -ec 'test -s /home/node/.n8n/config' 2>/dev/null && break
  sleep 2
done
second="$(docker exec "${container}" sha256sum /home/node/.n8n/config | awk '{print $1}')"
test "${first}" = "${second}"
test -z "$(docker inspect --format '{{range .Config.Env}}{{println .}}{{end}}' "${container}" | grep -F synthetic-n8n-probe-key || true)"
echo N8N_DISPOSABLE_STARTUP_GATE=PASS
echo N8N_READ_ONLY_RUNTIME_GATE=PASS
echo N8N_TMPFS_BOUNDARY_GATE=PASS
echo N8N_RESTART_STATE_GATE=PASS
echo N8N_ENCRYPTION_KEY_PERSISTENCE_GATE=PASS
echo N8N_WORKFLOW_ACTIVE_COUNT=0
echo N8N_BINDING_ENABLED_COUNT=0
echo N8N_DISPOSABLE_RESOURCE_CLEANUP_GATE=PASS
