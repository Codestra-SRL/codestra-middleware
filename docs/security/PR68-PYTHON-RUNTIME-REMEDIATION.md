# PR #68 Python runtime remediation

Registry and upstream verification performed on 2026-08-01 established that
`python:3.12.14-slim-bookworm` does not exist. The newest Docker Official Image
in the Python 3.12 slim-bookworm line is 3.12.13.

```text
OLD_BASE_IMAGE=docker.io/library/python:3.12.13-alpine3.24
OLD_BASE_DIGEST=sha256:6d43704baacd1bfbe7c295d7f13079d5d8104ed33568873133f8fc69980419df
NEW_BASE_IMAGE=docker.io/library/python:3.12.13-slim-bookworm
NEW_BASE_DIGEST=sha256:d50fb7611f86d04a3b0471b46d7557818d88983fc3136726336b2a4c657aa30b
PYTHON_RUNTIME_VERSION=3.12.13
LINUX_AMD64_MANIFEST_DIGEST=sha256:72d3d75f2639ab82b34b29390ad3d6e0827c775befee94edda8e9976818f488d
UPSTREAM_SOURCE_COMMIT=3362634339580d3232e65a66dd5a36c47ae7ff14
```

The image index, amd64 manifest, OCI source annotation, upstream Dockerfile,
and runtime version were independently verified before the pin was changed.
The candidate workflow resolves the base with `--pull --no-cache`, builds the
application, and scans the final candidate digest with both Trivy and Grype.

The base is not asserted to be vulnerability-free. A preliminary base-only
scan reported nonzero High and Critical findings from both scanners. Those
counts are not candidate results and cannot be used to approve or reject the
final application image. The exact candidate workflow preserves all final
findings in the evidence package and creates only an unsigned, pending Security
Owner request. It never suppresses findings or creates an exception.
