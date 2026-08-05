# Workflow state

Every transition uses the allowlisted state graph and increments `state_version` atomically. APIs require `If-Match-State-Version`; stale writers receive HTTP 409. Terminal states cannot silently reopen.
