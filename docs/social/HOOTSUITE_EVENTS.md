# Hootsuite events

`HOOTSUITE_EVENT_MODE=POLLING`. The message API permits callback URLs, but the reviewed official reference does not document a signature-verification contract acceptable to Middleware. Codestra therefore reconciles Hootsuite-owned messages through `GET /v1/messages/{messageId}` and emits the existing normalized IntegrationEvent contract.
