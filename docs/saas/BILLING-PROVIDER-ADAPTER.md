# Billing provider adapter

Implement `BillingProvider`, `PaymentMethodProvider`, `InvoiceProvider` and `TaxProvider` interfaces. Never expose provider secrets to browser, n8n or tenant services. Webhooks require signature, timestamp, replay and idempotency checks.
