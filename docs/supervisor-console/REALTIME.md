# Realtime

SSE is the initial transport, with monotonic event IDs, `Last-Event-ID` recovery, heartbeat, no-store responses, bounded events and proxy buffering disabled. Every event is filtered by validated tenant, workspace and team scope. PostgreSQL event history is authoritative; Redis/WebSocket acceleration may be added without weakening scope.
