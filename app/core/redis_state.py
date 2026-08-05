"""Redis operational-state policy; PostgreSQL remains authoritative."""

from dataclasses import dataclass

REDIS_NAMESPACES = frozenset({"control", "workflows", "events", "voice", "integrations"})
FORBIDDEN_REDIS_COMMANDS = frozenset({"FLUSHALL", "FLUSHDB", "CONFIG", "MODULE", "DEBUG", "SHUTDOWN", "KEYS", "MIGRATE", "SLAVEOF", "REPLICAOF"})


@dataclass(frozen=True)
class RedisKeyContext:
    environment: str
    tenant_id: str
    workspace_id: str
    namespace: str
    resource: str
    identifier: str


def redis_key(context: RedisKeyContext) -> str:
    if not all((context.environment, context.tenant_id, context.workspace_id, context.namespace, context.resource, context.identifier)):
        raise ValueError("environment, tenant, workspace, namespace, resource, and identifier are required")
    if context.namespace not in REDIS_NAMESPACES:
        raise ValueError("unknown Redis namespace")
    return f"codestra:{context.environment}:{context.tenant_id}:{context.workspace_id}:{context.namespace}:{context.resource}:{context.identifier}"


def redis_command_allowed(command: str) -> bool:
    return command.upper() not in FORBIDDEN_REDIS_COMMANDS


def namespace_ttl_required(namespace: str) -> bool:
    return namespace in {"voice", "events", "integrations"}
