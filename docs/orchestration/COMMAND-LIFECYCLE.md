# Command lifecycle

Commands move through validation, authorization, outbox, queue, execution, result,
reconciliation, and audit states. Invalid transitions are rejected.
