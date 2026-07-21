"""Dead-letter policy helpers. No delivery is attempted while flags are false."""

MAX_ATTEMPTS = 8


def should_dead_letter(attempts: int) -> bool:
    return attempts >= MAX_ATTEMPTS
