import hashlib
import hmac


class BearerAuthError(ValueError):
    pass


def authenticated_service_subject(authorization: str, secret: str) -> str:
    """Validate the service credential and derive its non-forgeable audit subject."""
    if not secret:
        raise BearerAuthError("authorization service unavailable")
    scheme, separator, supplied = authorization.partition(" ")
    if scheme.lower() != "bearer" or not separator or not supplied:
        raise BearerAuthError("missing or invalid bearer authorization")
    if not hmac.compare_digest(supplied, secret):
        raise BearerAuthError("invalid bearer authorization")
    fingerprint = hashlib.sha256(supplied.encode()).hexdigest()[:24]
    return f"service:middleware:{fingerprint}"


def verify_bearer(authorization: str, secret: str) -> None:
    authenticated_service_subject(authorization, secret)
