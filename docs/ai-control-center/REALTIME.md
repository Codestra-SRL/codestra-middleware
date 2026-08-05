# Realtime updates

Realtime transport is reserved for an authenticated middleware SSE/WebSocket
implementation with tenant scope, sequence numbers, heartbeats, bounded
payloads and reconnect support. It is not enabled in this repository-only
foundation; clients must use bounded polling when the transport is deployed.
