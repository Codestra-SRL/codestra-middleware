# Recording API security contract

The recording API is reachable only through Server A's private mTLS proxy.
That proxy removes any client-supplied `X-Verified-MTLS-Client-ID` header,
validates the client certificate against the recording-service CA, and sets
the header from the verified certificate identity. Direct access to the ASGI
port is prohibited by the deployment network policy.

Accepted identities are endpoint-specific:

- `server-b-recording-exporter`: reservation, completion, failure, and status
- `odoo-recording-service`: status and short-lived playback URL
- `recording-retention-worker`: status only

Presigned upload URLs expire after 300 seconds. Playback URLs expire after 120
seconds. Permanent credentials, raw object keys, filesystem paths, and bucket
root credentials are never returned.
