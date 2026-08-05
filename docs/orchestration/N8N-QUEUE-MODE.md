# Queue mode

Redis queues are operational transport only. Worker groups claim bounded work and
heartbeat; durable command and execution state remains in PostgreSQL.
