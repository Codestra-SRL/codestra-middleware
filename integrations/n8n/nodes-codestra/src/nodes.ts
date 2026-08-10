type NodeDescription = { displayName: string; name: string; group: string[]; version: number; description: string; defaults: { name: string }; inputs: string[]; outputs: string[]; credentials: Array<{ name: string; required: boolean }>; properties: unknown[] };

const operations: Record<string, string[]> = {
  CodestraEventTrigger: ['receive'],
  CodestraSocial: ['createDraft', 'schedule', 'cancel', 'status', 'analytics', 'listAccounts', 'accountHealth'],
  CodestraCampaign: ['create', 'read', 'transition', 'requestApproval', 'approve', 'reject', 'pause', 'resume', 'scheduleContent', 'analytics'],
  CodestraLead: ['submit', 'validate', 'dedupe', 'enrich', 'score', 'assignCampaign', 'requestOdooDryRun'],
  CodestraOdoo: ['dryRunProjection', 'requestGovernedCommand', 'deliveryStatus'],
  CodestraAI: ['contentGeneration', 'rewrite', 'translation', 'classification', 'leadScoring', 'intentDetection', 'sentiment', 'spamDetection', 'contentRisk', 'campaignAnalysis', 'optimizationRecommendation'],
  CodestraAnalytics: ['snapshot', 'campaignSummary', 'postSummary'],
  CodestraAudit: ['recordResult', 'recordDecision'],
  CodestraNotification: ['notifyOperations'],
  CodestraDeadLetter: ['record', 'inspect', 'requestReplay'],
  CodestraApproval: ['request', 'approve', 'reject'],
  CodestraMedia: ['register', 'status', 'validate'],
};

function description(name: string): NodeDescription {
  return {
    displayName: name,
    name,
    group: ['Codestra'],
    version: 1,
    description: 'Calls the provider-neutral Codestra Middleware control plane.',
    defaults: { name },
    inputs: name === 'CodestraEventTrigger' ? [] : ['main'],
    outputs: ['main'],
    credentials: [{ name: 'codestraMiddleware', required: true }],
    properties: [{ displayName: 'Operation', name: 'operation', type: 'options', default: operations[name][0], options: operations[name].map(value => ({ name: value, value })) }],
  };
}

export class CodestraEventTrigger { description = description('CodestraEventTrigger'); }
export class CodestraSocial { description = description('CodestraSocial'); }
export class CodestraCampaign { description = description('CodestraCampaign'); }
export class CodestraLead { description = description('CodestraLead'); }
export class CodestraOdoo { description = description('CodestraOdoo'); }
export class CodestraAI { description = description('CodestraAI'); }
export class CodestraAnalytics { description = description('CodestraAnalytics'); }
export class CodestraAudit { description = description('CodestraAudit'); }
export class CodestraNotification { description = description('CodestraNotification'); }
export class CodestraDeadLetter { description = description('CodestraDeadLetter'); }
export class CodestraApproval { description = description('CodestraApproval'); }
export class CodestraMedia { description = description('CodestraMedia'); }
