# Production defaults

The middleware settings define fail-closed defaults for high-risk operations:
`AI_INFERENCE_ENABLED=false`, `SCRAPER_REAL_HTTP_FETCH_ENABLED=false`,
`ODOO_LEAD_CREATE_ENABLED=false`, `VICIDIAL_LIVE_DIALING_ENABLED=false`,
`CALL_RECORDING_PROCESSING_ENABLED=false`, `AGENT_ASSIST_REAL_AUDIO_ENABLED=false`,
`POSTIZ_PUBLISHING_ENABLED=false`, and `AUTOMATIC_PRODUCTION_ACTIVATION_ENABLED=false`.

Any deployment manifest that deviates must be rejected by release review.
