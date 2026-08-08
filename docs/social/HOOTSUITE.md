# Hootsuite

Phase 3 implements Hootsuite REST API v1 behind the existing provider-neutral adapter contract. Supported operations are OAuth, profile discovery, message create/schedule, message lookup, delete/cancel, and media-upload initialization/status. Unsupported operations return capability errors rather than synthetic success.

The adapter registers in source but remains inert unless `HOOTSUITE_ENABLED=true`. Default provider selection and all publishing gates remain disabled. Hootsuite never receives Odoo traffic directly and never becomes a failover for Postly-owned jobs.
