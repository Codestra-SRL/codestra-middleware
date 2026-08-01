# Security governance

## Security Owner approval delegation

For Server A isolated-staging risk decisions only, `kazan555` is the Security Owner approval delegate and `appolon1908-hue` is the requestor. This delegation grants no production, Server B, telephony, communications, recording, deployment, or activation authority.

The delegate must independently approve the exact governance or application commit and the protected `security-owner-signing` environment. The requestor cannot self-approve. Every decision remains digest-bound, time-limited, auditable, and default-deny outside its stated scope.
