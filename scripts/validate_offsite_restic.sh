#!/usr/bin/env bash
set -euo pipefail
umask 077

repository_file=${BACKUP_REPOSITORY_FILE:-/srv/codestra-platform/secrets/restic-repository}
ssh_key_file=${BACKUP_SSH_KEY_FILE:-/srv/codestra-platform/secrets/backup-ssh-key}
password_file=${RESTIC_PASSWORD_FILE:-/srv/codestra-platform/secrets/restic-password}
access_key_file=${AWS_ACCESS_KEY_ID_FILE:-}
secret_key_file=${AWS_SECRET_ACCESS_KEY_FILE:-}
region_file=${AWS_REGION_FILE:-}
source_archive=${1:-}
source_checksum=${2:-}

fail() { printf 'OFFSITE_RESTIC_VALIDATION=BLOCKED reason=%s\n' "$1" >&2; exit 2; }
require_root_0600() {
  local file=$1 label=$2
  [ -f "$file" ] || fail "${label}_MISSING"
  [ "$(stat -c '%u:%g:%a' "$file")" = '0:0:600' ] || fail "${label}_OWNERSHIP_OR_MODE_INVALID"
}

require_root_0600 "$repository_file" BACKUP_REPOSITORY_FILE
require_root_0600 "$password_file" RESTIC_PASSWORD_FILE
[ -n "$source_archive" ] && [ -f "$source_archive" ] || fail SOURCE_ARCHIVE_MISSING
[ -n "$source_checksum" ] && [ -f "$source_checksum" ] || fail SOURCE_CHECKSUM_MISSING

export RESTIC_REPOSITORY_FILE="$repository_file"
export RESTIC_PASSWORD_FILE="$password_file"
restic_timeout=${RESTIC_TIMEOUT_SECONDS:-300}
restic_options=()
if [ -n "$access_key_file" ] || [ -n "$secret_key_file" ]; then
  require_root_0600 "$access_key_file" AWS_ACCESS_KEY_ID_FILE
  require_root_0600 "$secret_key_file" AWS_SECRET_ACCESS_KEY_FILE
  export AWS_ACCESS_KEY_ID="$(<"$access_key_file")"
  export AWS_SECRET_ACCESS_KEY="$(<"$secret_key_file")"
  export AWS_EC2_METADATA_DISABLED=true
  if [ -n "$region_file" ]; then
    require_root_0600 "$region_file" AWS_REGION_FILE
    export AWS_DEFAULT_REGION="$(<"$region_file")"
  fi
else
  require_root_0600 "$ssh_key_file" BACKUP_SSH_KEY_FILE
  restic_options=(-o "sftp.command=ssh -i $ssh_key_file -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes")
fi
restic_cmd() { timeout "$restic_timeout" restic "${restic_options[@]}" "$@"; }

work_dir=$(mktemp -d /opt/codestra/backups/restic-validation.XXXXXX)
cleanup() { find "$work_dir" -depth -delete; }
trap cleanup EXIT

cp -- "$source_archive" "$source_checksum" "$work_dir/"
(cd "$work_dir" && sha256sum -c "$(basename "$source_checksum")")
restic_cmd snapshots --json >/dev/null
snapshot_id=$(restic_cmd backup --json "$work_dir" | jq -r 'select(.message_type=="summary") | .snapshot_id' | tail -1)
[ -n "$snapshot_id" ] || fail BACKUP_UPLOAD_NO_SNAPSHOT
restic_cmd snapshots --json | grep -Fq "$snapshot_id" || fail SNAPSHOT_LIST_MISSING
restic_cmd check --read-data-subset=5%
restore_dir="$work_dir/restore"
install -d -m 700 "$restore_dir"
restic_cmd restore "$snapshot_id" --target "$restore_dir"
restored_checksum=$(find "$restore_dir" -type f -name "$(basename "$source_checksum")" -print -quit)
[ -n "$restored_checksum" ] || fail RESTORED_CHECKSUM_MISSING
(cd "$(dirname "$restored_checksum")" && sha256sum -c "$(basename "$restored_checksum")")
printf 'OFFSITE_REPOSITORY_REACHABLE=PASS\nBACKUP_UPLOAD=PASS\nSNAPSHOT_ID=%s\nSNAPSHOT_LIST=PASS\nSNAPSHOT_CHECK=PASS\nISOLATED_RESTORE_FROM_OFFSITE=PASS\nCHECKSUM_VERIFICATION=PASS\n' "$snapshot_id"
