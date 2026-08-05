# Webhooks

Webhook deliveries use HMAC over `timestamp.payload`, timestamp tolerance, replay protection, retries and delivery history. Subscriptions are tenant-scoped; endpoint secrets are references and never returned after creation.
