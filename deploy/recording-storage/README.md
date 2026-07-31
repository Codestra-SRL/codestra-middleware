# Private recording storage source

Source-only MinIO configuration for a TLS-terminated, private internal network.
The console is not started or published. Applications receive scoped identities;
Server B receives only one-object presigned upload URLs and no storage identity.

Object Lock is enabled at bucket creation, versioning is mandatory, staging uses
SSE-S3, and the bootstrap exits before any production setup unless an external
KMS provider is explicitly configured. This directory is not a deployment
authorization.
