# Recording storage rollback

Rollback disables new reservations, preserves every object version, and
restores the previously approved Compose artifact by exact checksum. Service
identities, legal holds, and bucket data are not deleted. Retention execution
remains disabled. Rollback requires the prior Compose checksum and image
digests plus a read-only inventory showing zero pending upload completions.
