# n8n handoff

Approved direction is `n8n → Codestra Middleware → Postly`. n8n receives neither Postly API keys nor social OAuth tokens and cannot schedule or publish.

Production workflows return only the versioned JSON documents in `schemas/n8n-*.schema.json`: generated proposal, translation variants, prepared media manifest, brand validation, approval-notification result, or workflow failure. Media references must point to Middleware-controlled objects; never embed credentials or local Postly paths.

Middleware must bind every result to organization, workspace, campaign, job, version, and workflow execution; reject stale content versions; scan media; enforce approval; and create the Postly command itself. Human approval notifications are informational—the approval decision must be recorded in Middleware, not inferred from n8n execution success.
