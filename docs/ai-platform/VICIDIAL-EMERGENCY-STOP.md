# Emergency stop

Set `vicidial_live_canary_authorized=false`, disable campaign activation and
canary flags, shut down the staging campaign through the approved operational
adapter, and preserve all audit/reconciliation records. The API shutdown
endpoint is safe to call independently of live-call enablement.
