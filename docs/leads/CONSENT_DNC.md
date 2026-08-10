# Consent and DNC

Public availability is not consent. Consent states are `UNKNOWN`, `NOT_REQUIRED`, `PENDING`, `GRANTED`, `REVOKED`, and `EXPIRED`; DNC states include `CLEAR`, `INTERNAL_DNC`, `NATIONAL_DNC`, `CUSTOMER_REQUEST`, `LEGAL_BLOCK`, and `UNKNOWN`.

Confirmed DNC has final authority and produces `DO_NOT_CONTACT`. Consent other than `GRANTED` produces `MANUAL_REVIEW` in the current conservative policy. Neither AI nor n8n can override these decisions. National-DNC status must carry an authoritative evidence reference.
