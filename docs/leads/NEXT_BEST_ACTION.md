# Next-best-action

The engine returns recommendations only: `CALL_NOW`, `CALL_LATER`, `EMAIL`, `SOCIAL_REPLY`, `BOOK_APPOINTMENT`, `NURTURE`, `REQUEST_INFORMATION`, `SUPPORT_HANDOFF`, `MANUAL_REVIEW`, `DO_NOT_CONTACT`, `CLOSE_LOST`, or `NO_ACTION`.

Policy order is DNC, consent, jurisdiction/channel rules, then evidence-based intent and contactability. Feedback records outcomes but never directly retrains a production model. `AUTOMATIC_CONTACTING_ENABLED` defaults false and is rejected by safety validation if enabled.
