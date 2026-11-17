"""Error classes that decide whether a failed task is retried."""


class TransientError(Exception):
    """Temporary failure (network, rate limit, service unavailable). Safe to retry."""


class PermanentError(Exception):
    """The input cannot be processed. Retrying will not help."""


class QuotaRateLimit(TransientError):
    """The LLM or embedding provider rejected the request due to quota."""


_TRANSIENT_NAMES = {
    "ResourceExhausted",
    "ServiceUnavailable",
    "DeadlineExceeded",
    "InternalServerError",
    "TooManyRequests",
    "TransportError",
    "ResponseHandlingException",
}


def is_transient(exc: BaseException) -> bool:
    """Classify an exception from an external provider as transient or not."""
    if isinstance(exc, TransientError):
        return True
    if isinstance(exc, PermanentError):
        return False
    if isinstance(exc, (ConnectionError, TimeoutError)):
        return True
    return any(cls.__name__ in _TRANSIENT_NAMES for cls in type(exc).__mro__)
