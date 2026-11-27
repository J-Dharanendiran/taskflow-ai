"""Deterministic error classification and bounded retry policy for the graph."""

from enum import StrEnum

from pydantic import ValidationError
from sqlalchemy.exc import DBAPIError, OperationalError

from app.services.exceptions import (
    InvalidTaskDataError,
    TaskNotFoundError,
    UncertainExecutionOutcomeError,
)


class ErrorCategory(StrEnum):
    VALIDATION = "validation"
    MISSING_RESOURCE = "missing_resource"
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    UNCERTAIN_OUTCOME = "uncertain_outcome"


MAX_TRANSIENT_RETRIES = 2


def classify_error(error: Exception) -> ErrorCategory:
    """Classify known failures; unknown exceptions fail closed as permanent."""
    if isinstance(error, (ValidationError, InvalidTaskDataError, ValueError, TypeError)):
        return ErrorCategory.VALIDATION
    if isinstance(error, TaskNotFoundError):
        return ErrorCategory.MISSING_RESOURCE
    if isinstance(error, UncertainExecutionOutcomeError):
        return ErrorCategory.UNCERTAIN_OUTCOME
    if isinstance(error, (TimeoutError, ConnectionError)):
        return ErrorCategory.TRANSIENT
    if isinstance(error, DBAPIError) and error.connection_invalidated:
        return ErrorCategory.TRANSIENT
    if isinstance(error, OperationalError):
        message = str(error.orig).lower()
        transient_markers = (
            "locked",
            "busy",
            "timeout",
            "timed out",
            "connection",
            "unavailable",
            "temporarily",
            "disk i/o",
        )
        if any(marker in message for marker in transient_markers):
            return ErrorCategory.TRANSIENT
    return ErrorCategory.PERMANENT


def should_retry(
    error: Exception,
    *,
    retries_used: int,
    max_retries: int = MAX_TRANSIENT_RETRIES,
) -> bool:
    """Apply a configurable retry ceiling; retries_used excludes the first attempt."""
    if retries_used < 0 or max_retries < 0:
        raise ValueError("Retry counts must be non-negative.")
    return classify_error(error) == ErrorCategory.TRANSIENT and retries_used < max_retries
