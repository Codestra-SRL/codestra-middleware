import type { DesktopData } from "../types/desktop";

export interface DesktopService { load():Promise<DesktopData>; saveNotes(leadId:string,notes:string,interactionId?:string):Promise<void>; disposition(leadId:string,value:string,interactionId?:string):Promise<void>; scheduleCallback(leadId:string,iso:string,reason:string,timezone:string,priority:string,interactionId?:string):Promise<void>; }
const data:DesktopData={lead:{id:"SYN-9001",name:"John Smith",phoneMasked:"••• ••• 0100",email:"john.smith@example.test",company:"Smith Transport",score:88,source:"Synthetic inbound",owner:"WEBSET01",closer:"WEBCLO01",campaign:"TRANSFER_TEST",timezone:"America/New_York",tags:["Transportation","Qualified","Synthetic"],notes:"Interested in fleet coverage. Follow up on payment terms."},history:[{id:"C-1003",when:"Today, 10:42",duration:"04:18",result:"Qualified",agent:"WEBSET01"},{id:"C-1002",when:"Jul 18, 15:05",duration:"02:44",result:"Callback",agent:"WEBAI01"},{id:"C-1001",when:"Jul 17, 09:30",duration:"01:11",result:"No answer",agent:"WEBSET01"}],notifications:[{id:"N1",level:"warning",message:"Required disclosure remains incomplete",time:"Now",read:false},{id:"N2",level:"success",message:"Synthetic lead assigned to WEBSET01",time:"2m",read:false},{id:"N3",level:"info",message:"WebRTC diagnostic build available",time:"12m",read:true}],team:[{id:"WEBSET01",name:"Maya Rivera",role:"Setter",status:"On Call",activeCall:"John Smith",quality:96},{id:"WEBCLO01",name:"Daniel Ortiz",role:"Closer",status:"Ready",quality:99},{id:"WEBSUP01",name:"Nina Patel",role:"Supervisor",status:"Ready",quality:98},{id:"WEBAI01",name:"AI Qualifier",role:"AI Test",status:"Paused",quality:94}],ai:{transcript:["Customer: We operate twelve delivery vehicles.","Agent: Are all vehicles titled to the business?","Customer: Yes, and we may add three this quarter."],sentiment:"Positive",confidence:92,nextQuestion:"What is the target effective date for coverage?",objection:"Customer is comparing payment terms.",disclosure:"Required — not yet confirmed",summary:"Qualified transportation lead with 12 vehicles and near-term expansion."}};
const pause=()=>new Promise<void>(r=>setTimeout(r,180));

/**
 * @deprecated writes are mocked (no-op) -- kept only as the `load()` data
 * source, which is a separate, tracked gap (AGENT-05, screen-pop/CRM data
 * accuracy), not covered by this change. Never call the write methods on
 * this object directly; use `liveDesktopService`.
 */
export const mockDesktopService:DesktopService={async load(){await pause();return structuredClone(data)},async saveNotes(){await pause()},async disposition(){await pause()},async scheduleCallback(){await pause()}};

const jsonHeaders = { "Content-Type": "application/json" };

/**
 * Fallback interaction id when no live call context (screen-pop `call_id`)
 * is available -- e.g. an agent editing notes outside an active call. This
 * keeps writes correctly attributed and idempotent per lead, but does not
 * correlate to a specific VICIdial call. Threading a real active-call id
 * through from the phone/session layer for every write is tracked separately
 * (AGENT-04, ACD state model) and should replace this fallback.
 */
function fallbackInteractionId(leadId: string): string {
  return `no-active-call:${leadId}`;
}

async function post(path: string, body: unknown): Promise<void> {
  const response = await fetch(path, {
    method: "POST",
    credentials: "include",
    headers: {
      ...jsonHeaders,
      "Idempotency-Key": crypto.randomUUID(),
      "X-Correlation-ID": crypto.randomUUID(),
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    throw new Error(`Interaction save failed (${response.status})`);
  }
}

export const liveDesktopService: DesktopService = {
  load: () => mockDesktopService.load(),
  async saveNotes(leadId, notes, interactionId) {
    const id = interactionId ?? fallbackInteractionId(leadId);
    await post(`/api/v1/interactions/${encodeURIComponent(id)}/notes`, {
      crm_lead_public_id: leadId,
      notes_text: notes,
    });
  },
  async disposition(leadId, value, interactionId) {
    const id = interactionId ?? fallbackInteractionId(leadId);
    await post(`/api/v1/interactions/${encodeURIComponent(id)}/disposition`, {
      crm_lead_public_id: leadId,
      disposition_code: value,
    });
  },
  async scheduleCallback(leadId, iso, reason, timezone, _priority, interactionId) {
    const id = interactionId ?? fallbackInteractionId(leadId);
    await post(`/api/v1/interactions/${encodeURIComponent(id)}/callback`, {
      crm_lead_public_id: leadId,
      scheduled_for: iso,
      timezone,
      reason,
    });
  },
};
