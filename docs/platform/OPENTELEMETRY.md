# OpenTelemetry and correlation

The platform accepts W3C `traceparent` and preserves trace, correlation, request, event, delivery and workflow execution identifiers. Invalid trace headers are replaced, never trusted. `platform_trace_links` stores navigation metadata without content or credentials.

Phase N5 provides propagation and persistence foundations. Collector deployment is planned for isolated staging after the existing monitoring topology is reviewed; no new collector is deployed by this branch.
