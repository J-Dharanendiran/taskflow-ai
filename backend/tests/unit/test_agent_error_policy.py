import pytest
from app.agent.error_policy import ErrorCategory, classify_error, should_retry
from app.services.exceptions import (
    InvalidTaskDataError,
    TaskNotFoundError,
    UncertainExecutionOutcomeError,
)
from sqlalchemy.exc import OperationalError


def test_validation_errors_are_not_retryable():
    error = InvalidTaskDataError("bad input")
    assert classify_error(error) == ErrorCategory.VALIDATION
    assert should_retry(error, retries_used=0) is False


def test_missing_resource_errors_are_not_retryable():
    error = TaskNotFoundError("missing")
    assert classify_error(error) == ErrorCategory.MISSING_RESOURCE
    assert should_retry(error, retries_used=0) is False


def test_transient_errors_allow_two_retries_only():
    error = TimeoutError("temporary timeout")
    assert classify_error(error) == ErrorCategory.TRANSIENT
    assert should_retry(error, retries_used=0) is True
    assert should_retry(error, retries_used=1) is True
    assert should_retry(error, retries_used=2) is False


def test_database_operational_error_is_transient():
    error = OperationalError("select 1", {}, RuntimeError("db unavailable"))
    assert classify_error(error) == ErrorCategory.TRANSIENT


def test_uncertain_side_effect_outcome_is_never_blindly_retried():
    error = UncertainExecutionOutcomeError("commit outcome unknown")
    assert classify_error(error) == ErrorCategory.UNCERTAIN_OUTCOME
    assert should_retry(error, retries_used=0) is False


def test_unknown_error_fails_closed_as_permanent():
    error = RuntimeError("unexpected")
    assert classify_error(error) == ErrorCategory.PERMANENT
    assert should_retry(error, retries_used=0) is False



def test_operational_error_with_permanent_database_message_is_not_retryable():
    error = OperationalError("select * from missing_table", {}, RuntimeError("no such table"))
    assert classify_error(error) == ErrorCategory.PERMANENT
    assert should_retry(error, retries_used=0) is False


def test_retry_ceiling_can_be_configured():
    error = TimeoutError("temporary timeout")
    assert should_retry(error, retries_used=2, max_retries=3) is True
    assert should_retry(error, retries_used=3, max_retries=3) is False


def test_negative_retry_configuration_is_rejected():
    error = TimeoutError("temporary timeout")
    with pytest.raises(ValueError, match="non-negative"):
        should_retry(error, retries_used=-1)
    with pytest.raises(ValueError, match="non-negative"):
        should_retry(error, retries_used=0, max_retries=-1)
