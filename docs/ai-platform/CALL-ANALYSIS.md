# Call analysis

Prompt `call-analysis-v1` treats transcripts as untrusted evidence and emits structured JSON only. Claims must be traceable to transcript content. The model cannot take actions, change dispositions, create callbacks, expose hidden reasoning, make legal conclusions or make disciplinary decisions. Schema failures receive a bounded retry, then human review.

