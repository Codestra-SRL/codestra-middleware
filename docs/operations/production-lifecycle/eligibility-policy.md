# Eligibility policy

Eligibility is an AND policy over campaign, business unit, exact source
extension, exact agent group, direction, exact dialplan context, destination
classification, producer identity and boot session, schema version, event type,
and activation high-water mark.

Any missing, unknown, ambiguous, or mismatched attribute is rejected. Fixture
6198, synthetic contexts, P3SIP01, TEST_SYN, extension 1101, emergency routes,
service codes, transfers, callbacks, queues, conferences, voicemail, unknown
destinations, and the broad contexts listed in `scope-v1.yaml` are excluded.
No production event is presently eligible because the approved extension and
context arrays are empty.
