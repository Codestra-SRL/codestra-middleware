# VICIdial recording integration

The adapter is read-only and limited to health, call metadata, recording metadata and short-lived access preparation. It must validate the call-to-recording mapping, normalize the path under the configured recording root, reject traversal, enforce size/format/checksum rules and audit access. Permanent/public URLs, unrestricted SQL and recording/call/campaign mutation are forbidden.

