"""Sanitized failures: upstream response bodies must not enter logs."""


class LifeSmartError(Exception):
    """An upstream error safe to include in a local log."""


class AuthenticationError(LifeSmartError):
    """Credentials must be replaced or refreshed."""


class CannotConnect(LifeSmartError):
    """The server is unreachable."""


class ProtocolError(LifeSmartError):
    """The response does not match the supported protocol."""


class IdentityMismatch(LifeSmartError):
    """The connection belongs to another station."""


class MissingIdentity(LifeSmartError):
    """No verified station identifier is available."""


class UnsupportedCapability(LifeSmartError):
    """The model does not expose the requested operation."""


class CommandOutcomeUnknown(LifeSmartError):
    """A write may have reached the station. Do not replay it."""


class RateLimited(LifeSmartError):
    """Retry no sooner than the server's requested delay."""

    def __init__(self, retry_after: float = 60):
        super().__init__("LifeSmart rate limit")
        self.retry_after = max(1, min(retry_after, 3600))
