from __future__ import annotations

import re
import secrets
from dataclasses import dataclass

TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


@dataclass(frozen=True)
class TraceContext:
    trace_id: str
    span_id: str
    sampled: bool

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{'01' if self.sampled else '00'}"


def trace_context(value: str | None) -> TraceContext:
    if value:
        match = TRACEPARENT.fullmatch(value.casefold())
        if match and int(match.group(1), 16) and int(match.group(2), 16):
            return TraceContext(
                match.group(1), match.group(2), bool(int(match.group(3), 16) & 1)
            )
    return TraceContext(secrets.token_hex(16), secrets.token_hex(8), True)
