# VICIdial adapter

Allowed reads: health, agents, states, active calls, campaign/queue summaries, callbacks, dispositions, transfers, call and recording metadata. Browser access, arbitrary SQL, carrier/trunk/dial-plan changes, campaign activation, auto-dial increases and deletion are prohibited. All future commands require middleware policy, idempotency, confirmation and audit; command flags are off.
