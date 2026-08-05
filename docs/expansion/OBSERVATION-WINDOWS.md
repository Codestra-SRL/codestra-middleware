# Observation windows

The stage owner records start/end timestamps and evaluates a bounded window after the final job. The next stage cannot start until the prior outcome is `PASS`. A warning or backlog pauses the stage; any duplicate, unauthorized write, cross-tenant event, live call, hopper entry, critical alert, Postiz outage or website outage requires rollback.
