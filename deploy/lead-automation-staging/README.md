# Lead Automation isolated staging preparation

This directory is preparation-only. Rendering and validation are permitted;
starting the persistent stack is not part of this phase. All application
services require an explicit Compose profile, all feature switches are false,
the network is internal, and no host port is published.

Validate with:

```sh
python3 deploy/lead-automation-staging/validate.py
docker compose -f deploy/lead-automation-staging/compose.yaml \
  --profile deployment --profile operations config -q
```

Supply only immutable `name@sha256:digest` image references and staging-only
paths. Do not place secret values in an environment file. The current image
scan evidence must be reviewed and all HIGH/CRITICAL findings resolved or
formally rejected under the security policy before deployment authorization.

