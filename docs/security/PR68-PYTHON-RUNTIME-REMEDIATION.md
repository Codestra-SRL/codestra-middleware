# PR #68 Python runtime remediation status

The rejected candidate from Actions run `30716111520` used the source-patched
Python 3.12.13 runtime. Grype reported 20 High matrix rows: ten vulnerability
IDs, each associated with both `/usr/local/bin/python3.12` and
`/usr/local/lib/libpython3.12.so.1.0`. Trivy reported no corresponding High or
Critical rows. No finding was suppressed.

As of 2026-08-01, Python 3.12.13 is the current Docker Official Image release
for the 3.12 line. The proposed `python:3.12.14-slim-bookworm` tag does not
exist. The fixed-version metadata begins at Python 3.13.13/3.13.14,
3.14.4/3.14.6, or 3.15 prereleases depending on the advisory. There is no
single available stable official runtime demonstrated to satisfy every row,
and moving the application to another minor Python line without compatibility
qualification would be an unsupported ABI/runtime change.

The safe remediation alternative is to retain the existing checksum-verified
source backports temporarily, keep every scanner row visible, and replace the
runtime only after an official stable image contains a version satisfying all
advisories and passes the complete application, migration, integration, and
tenant-isolation suites. No exception or Security Owner decision is created by
this change.
