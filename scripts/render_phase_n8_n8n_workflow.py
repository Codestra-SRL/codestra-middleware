#!/usr/bin/env python3
"""Render the isolated, standard-node Phase N8 n8n workflow.

Secrets are referenced only through n8n environment variables and are never
embedded in the generated workflow document.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


CODE = r"""
const crypto = require('crypto');
const inbound = $input.first().json;
const headers = inbound.headers || {};
const envelope = inbound.body || {};
const canonical = value => Array.isArray(value)
  ? `[${value.map(canonical).join(',')}]`
  : value && typeof value === 'object'
    ? `{${Object.keys(value).sort().map(k => `${JSON.stringify(k)}:${canonical(value[k])}`).join(',')}}`
    : JSON.stringify(value);
const base = $env.PHASE_N8_MIDDLEWARE_BASE_URL;
const bearer = $env.PHASE_N8_MIDDLEWARE_TOKEN;
const secret = $env.PHASE_N8_RUNTIME_HMAC_SECRET;
if (!base || !bearer || !secret || secret.length < 32) throw new Error('isolated canary secrets unavailable');
const authHeaders = {
  Authorization: `Bearer ${bearer}`,
  'X-Codestra-Permissions': 'identity.review,lead.write,lead.score,lead.audit.read,revenue.write,attribution.read,social.ops.read',
  'X-Correlation-ID': envelope.correlation_id,
  'Content-Type': 'application/json',
};
const post = async (path, body, extraHeaders = authHeaders) => $helpers.httpRequest({
  method: 'POST', url: `${base}${path}`, headers: extraHeaders, body, json: true, returnFullResponse: false,
});
const rawEnvelope = canonical(envelope);
const authorizeHeaders = {
  'Content-Type': 'application/json',
  'X-Codestra-Identity': headers['x-codestra-identity'],
  'X-Codestra-Tenant': headers['x-codestra-tenant'],
  'X-Codestra-Workflow': headers['x-codestra-workflow'],
  'X-Codestra-Execution': headers['x-codestra-execution'],
  'X-Codestra-Correlation-ID': headers['x-codestra-correlation-id'],
  'X-Codestra-Timestamp': headers['x-codestra-timestamp'],
  'X-Codestra-Nonce': headers['x-codestra-nonce'],
  'X-Codestra-Body-SHA256': headers['x-codestra-body-sha256'],
  'X-Codestra-Signature': headers['x-codestra-signature'],
};
const authorized = await post('/api/v1/n8n-runtime/social-authorize', JSON.parse(rawEnvelope), authorizeHeaders);
const social = authorized.event;
const leadPayload = social.payload;
const identity = await post('/api/v1/identity/resolve', {
  tenant_id: social.tenant_id,
  display_name: leadPayload.name,
  email: leadPayload.email,
  phone: leadPayload.phone,
  country_hint: 'US',
  social_provider: social.provider,
  social_network: leadPayload.network,
  social_profile_id: leadPayload.social_profile_id,
});
const lead = await post('/api/v1/leads', {
  tenant_id: social.tenant_id, person_id: identity.person_id,
  campaign_id: leadPayload.campaign_id, source: 'SOCIAL',
  consent_status: leadPayload.consent_status || 'UNKNOWN', dnc_status: leadPayload.dnc_status || 'CLEAR',
});
const interaction = await post(`/api/v1/leads/${lead.lead_id}/interactions`, {
  tenant_id: social.tenant_id, interaction_type: 'SOCIAL_MESSAGE', source: social.provider,
  source_event_id: social.event_id, campaign_id: leadPayload.campaign_id,
  content_id: leadPayload.content_id, occurred_at: social.occurred_at,
  safe_payload: {intent: 'BUYING_INTENT', message_class: 'QUOTE_REQUEST', synthetic: true},
});
const action = await post(`/api/v1/leads/${lead.lead_id}/next-action`, {
  tenant_id: social.tenant_id, intent: 'BUYING_INTENT',
  score_components: {intent_quality:25,contactability:15,identity_confidence:15,campaign_fit:10,urgency:5,source_quality:5},
  has_phone: true, has_email: true, has_social: true,
});
const dryRun = await post('/api/v1/odoo/leads/dry-run', {
  tenant_id: social.tenant_id, lead_intelligence_id: action.decision_id,
  fields: {lead_id: lead.lead_id, source:'SOCIAL', score:action.score, next_action:action.action},
});
const touch = await post('/api/v1/analytics/attribution/touches', {
  tenant_id: social.tenant_id, lead_id: lead.lead_id, campaign_id: leadPayload.campaign_id,
  content_id: leadPayload.content_id, network: leadPayload.network, provider: social.provider,
  source: 'SYNTHETIC_N8N', source_event_id: `touch-${social.event_id}`,
  event_type: 'CAMPAIGN_TOUCH', occurred_at: social.occurred_at,
});
const revenue = await post('/api/v1/analytics/attribution/revenue', {
  tenant_id: social.tenant_id, lead_id: lead.lead_id, event_type: 'PAYMENT_RECEIVED',
  amount: '1000', currency: 'USD', source_system: 'SYNTHETIC_TEST',
  external_reference: `revenue-${social.event_id}`, occurred_at: new Date().toISOString(), is_synthetic: true,
});
const attribution = {};
for (const model of ['FIRST_TOUCH','LAST_TOUCH','LINEAR','POSITION_BASED','TIME_DECAY']) {
  attribution[model] = await post(`/api/v1/analytics/attribution/revenue/${revenue.revenue_event_id}/calculate`, {tenant_id:social.tenant_id,model});
}
const callback = {
  schema_version:'codestra.n8n.result.v1', workflow_code:envelope.workflow_code,
  workflow_version:envelope.workflow_version, execution_id:envelope.execution_id,
  correlation_id:envelope.correlation_id, tenant_id:envelope.tenant_id, status:'completed',
  occurred_at:new Date().toISOString(),
  result:{person_id:identity.person_id,lead_id:lead.lead_id,interaction_id:interaction.interaction_id,
    decision_id:action.decision_id,touch_id:touch.touch_id,revenue_event_id:revenue.revenue_event_id,
    attribution_calculation_ids:Object.fromEntries(Object.entries(attribution).map(([k,v])=>[k,v.calculation_id])),
    odoo_dry_run:dryRun.dry_run,automatic_contact:false}, error_code:null,
};
const callbackRaw = canonical(callback);
const timestamp = String(Math.floor(Date.now()/1000));
const nonce = crypto.randomUUID().replaceAll('-','');
const bodyHash = crypto.createHash('sha256').update(callbackRaw).digest('hex');
const identityName = 'codestra-n8n-phase-n8';
const material = ['v1',identityName,envelope.tenant_id,envelope.workflow_code,envelope.execution_id,envelope.correlation_id,timestamp,nonce,bodyHash].join('\n');
const signature = crypto.createHmac('sha256',secret).update(material).digest('hex');
const callbackResult = await post('/api/v1/n8n-runtime/results', JSON.parse(callbackRaw), {
  'Content-Type':'application/json','X-Codestra-Identity':identityName,'X-Codestra-Tenant':envelope.tenant_id,
  'X-Codestra-Workflow':envelope.workflow_code,'X-Codestra-Execution':envelope.execution_id,
  'X-Codestra-Correlation-ID':envelope.correlation_id,'X-Codestra-Timestamp':timestamp,
  'X-Codestra-Nonce':nonce,'X-Codestra-Body-SHA256':`sha256:${bodyHash}`,'X-Codestra-Signature':`sha256=${signature}`,
});
return [{json:{accepted:true,synthetic:true,execution_id:envelope.execution_id,correlation_id:envelope.correlation_id,
  person_id:identity.person_id,lead_id:lead.lead_id,decision:action,revenue_event_id:revenue.revenue_event_id,
  attribution,odoo_dry_run:dryRun,callback:callbackResult,external_actions:0}}];
""".strip()


def workflow() -> dict:
    return {
        "id": "CdstPhaseN8BusinessCanaryV1",
        "name": "CdstPhaseN8BusinessCanaryV1",
        "active": False,
        "nodes": [
            {
                "id": "phase-n8-webhook",
                "name": "Authenticated Synthetic Ingress",
                "type": "n8n-nodes-base.webhook",
                "typeVersion": 2,
                "position": [0, 0],
                "parameters": {
                    "httpMethod": "POST",
                    "path": "codestra-social-router-v1",
                    "responseMode": "responseNode",
                    "options": {},
                },
                "webhookId": "codestra-phase-n8-business-canary-v1",
            },
            {
                "id": "phase-n8-pipeline",
                "name": "N7 Business Pipeline",
                "type": "n8n-nodes-base.code",
                "typeVersion": 2,
                "position": [300, 0],
                "parameters": {"jsCode": CODE},
            },
            {
                "id": "phase-n8-response",
                "name": "Synthetic Result",
                "type": "n8n-nodes-base.respondToWebhook",
                "typeVersion": 1.4,
                "position": [600, 0],
                "parameters": {
                    "respondWith": "json",
                    "responseBody": "={{$json}}",
                    "options": {"responseCode": 202},
                },
            },
        ],
        "connections": {
            "Authenticated Synthetic Ingress": {
                "main": [[{"node": "N7 Business Pipeline", "type": "main", "index": 0}]]
            },
            "N7 Business Pipeline": {
                "main": [[{"node": "Synthetic Result", "type": "main", "index": 0}]]
            },
        },
        "settings": {"executionOrder": "v1", "saveDataErrorExecution": "all", "saveDataSuccessExecution": "all"},
        "staticData": None,
        "meta": {"templateCredsSetupCompleted": True},
        "tags": [],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps([workflow()], separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()
