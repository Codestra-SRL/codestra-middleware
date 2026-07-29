# Release acceptance policy

Release and security acceptance are separate from source review and repository
administration.

## Authority

Only identities assigned in the reviewed and merged
`role-assignments.yaml` may issue decisions for their respective roles. A
person may hold multiple roles only when each assignment is explicit.

An assignment cannot become authoritative solely because the proposed assignee
authored or approved the assignment. The approving organization owner must
already possess independently established assignment authority.

## Binding requirements

Every acceptance must be an authenticated GitHub decision that states:

- the exact role;
- the exact source head and merge commit;
- the exact CI run identities;
- all relevant artifact and evidence SHA-256 digests;
- the decision;
- the decision timestamp.

Changes to any bound source or evidence invalidate the acceptance.

## PR #33 ordering deviation

The PR #33 ordering deviation cannot be accepted until the governance role
assignment is authoritative. Afterward, separate `RELEASE_OWNER` and
`SECURITY_OWNER` decisions must bind:

- head `068db5ec68422c9e86e46d182aa464091bd85092`;
- merge `e73c026bb6a74a6fffdb8ef45a3e165c4b5454dc`;
- head CI run `30409023486`;
- merge CI run `30409136230`;
- deviation SHA-256
  `e0b58bf35760a2d8d36148cb5e144b6c00cc840fa3d9a3d5f21299ac6509cf29`.

No production release may treat an unassigned identity or an unbound comment as
role-based acceptance.
