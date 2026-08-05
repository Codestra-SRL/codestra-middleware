# Call Intelligence architecture

VICIdial emits completed-call and recording metadata events to middleware. Middleware is the sole authority for identity, state, retries, audit, QA and Odoo authorization. Inactive n8n workflows may orchestrate calls to the private AI service, but cannot own state. The AI service transcribes and analyzes protected transcript content and cannot access Odoo or VICIdial databases.

Server assignment: control plane/Odoo/n8n `65.109.65.169`; transcription/Qwen `5.9.108.250`; call/recording source `65.21.67.207`; no Call Intelligence changes on `49.12.145.107`.

The stable key is `codestra:<tenant_id>:call:<vicidial_uniqueid>`. Database uniqueness plus callback payload hashes prevents duplicate jobs, transcripts, analyses, QA records and downstream activities. Every status transition is append-only audited.

