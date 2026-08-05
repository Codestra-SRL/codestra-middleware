# Host-key verification

Candidate ED25519 fingerprints observed from Server A:

- B private/public: `SHA256:jUuqkDC7yMnpFgeXTtLGb7C1+19ZnpgPCaEFlzALzIU`
- C public: `SHA256:qWstgD4YwjHJeNbk7uEAnc0LQbXaSr2RT+ugpvDMGJs`
- D previously recorded: `SHA256:xd3t8F4HaMywKG62th9ZsxKlrgCW3kNgbz9BU6pYrkw`

B and C scans match Server A's existing hashed `known_hosts` entries. This is
continuity evidence, not destination-console verification. D did not respond to
a fresh scan.

Before first mesh authentication, each destination-local session must run
`ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub` and return the fingerprint.
Only an exact match may be retained in the source's root-owned mode-0600
`known_hosts`. Never use `StrictHostKeyChecking=no`.
