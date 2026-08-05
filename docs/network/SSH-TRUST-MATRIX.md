# SSH trust matrix

## Required paths

| Source | Destination | Preferred address | Identity | Current state |
|---|---|---|---|---|
| A | B | 10.40.0.4 | `codestra_mesh_from_a_ed25519` | TCP reachable; dedicated key not authorized |
| A | C | 49.12.145.107 | `codestra_mesh_from_a_ed25519` | Public fallback reachable; dedicated key not authorized |
| A | D | 10.40.0.2 | `codestra_mesh_from_a_ed25519` | Blocked before authentication by private L2 failure |
| B | A | 10.40.0.1 | `codestra_mesh_from_b_ed25519` | B public key unavailable |
| C | A | public until VLAN assigned | `codestra_mesh_from_c_ed25519` | C public key unavailable |
| D | A | 10.40.0.1 | `codestra_mesh_from_d_ed25519` | D public key unavailable |

The Server A key fingerprint is
`SHA256:Fz4vk0ujzKg7z7KYiVGb6b1mpVMlCF96KFMYP+AZlMc`. Transfer only its
`.pub` file through an approved authenticated channel. Never transfer its
private counterpart.

Destination-local Codex sessions must install exact one-line public keys with
stable `from=` restrictions and forwarding disabled. They must report the
installed fingerprint, never private-key contents.

Optional B/D/C cross paths remain unconfigured because no operational purpose
was supplied.
