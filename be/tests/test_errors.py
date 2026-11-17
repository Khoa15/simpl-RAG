"""Retry policy: transient provider failures are retried, bad input is not."""
from src.rag.errors import PermanentError, QuotaRateLimit, TransientError, is_transient


class ResourceExhausted(Exception):
    pass


def test_transient_errors_are_retried():
    assert is_transient(TransientError("x"))
    assert is_transient(QuotaRateLimit("x"))
    assert is_transient(ConnectionError("x"))
    assert is_transient(TimeoutError("x"))
    assert is_transient(ResourceExhausted("quota"))


def test_permanent_errors_are_not_retried():
    assert not is_transient(PermanentError("invalid_pdf"))
    assert not is_transient(ValueError("bad input"))
