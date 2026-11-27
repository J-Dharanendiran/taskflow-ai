class TaskServiceError(Exception):
    """Base exception for task service operations."""


class TaskNotFoundError(TaskServiceError):
    """Raised when a requested task does not exist."""


class InvalidTaskDataError(TaskServiceError):
    """Raised when task data violates business rules."""


class ApprovalError(Exception):
    """Base exception for deletion approval lifecycle failures."""


class ApprovalNotFoundError(ApprovalError):
    """Raised when an approval is missing or belongs to another thread."""


class ApprovalConflictError(ApprovalError):
    """Raised when a conflicting decision is submitted for a resolved approval."""


class InvalidApprovalStateError(ApprovalError):
    """Raised when a deletion request is not in a state that permits the operation."""


class UncertainExecutionOutcomeError(Exception):
    """Raised when a side effect may have committed and must be reconciled first."""

class ConversationNotFoundError(Exception):
    """Raised when a conversation does not exist."""


class InvalidConversationDataError(Exception):
    """Raised when conversation data or pagination parameters are invalid."""