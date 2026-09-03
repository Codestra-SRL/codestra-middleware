# Privacy and retention

Only lifecycle status, bounded disposition, and bounded hangup cause are
permitted payload fields. Audio, names, customer records, SIP/HMAC secrets,
signatures, cookies, authorization headers, connection strings, and arbitrary
exception text are prohibited.

Customer destinations must not be enabled until an owner chooses full
exclusion, tokenization, or encrypted restricted storage. The current policy
therefore excludes every destination class.

Proposed retention pending owner approval: restricted raw response evidence 30
days, detailed ledger/diagnostic evidence 180 days, and redacted release
acceptance evidence for release lifetime plus one year. Legal hold overrides
purge. Restricted directories are mode 0700 and files 0600, encrypted at rest,
access-audited, and destroyed with a signed deletion tombstone.
