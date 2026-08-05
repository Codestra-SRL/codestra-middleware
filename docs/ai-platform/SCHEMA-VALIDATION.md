# Schema validation

Registered codes include `lead_discovery_v1`, `lead_normalization_v1`, `lead_verification_v1`, `lead_score_v1`, and `ai_error_result_v1`. The middleware guard enforces registered codes and confidence/score bounds; gateway and n8n must perform the same JSON-schema validation before callbacks. Invalid output cannot become an approved lead.
