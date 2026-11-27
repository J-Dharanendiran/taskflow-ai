
from datetime import UTC

from sqlalchemy import DateTime
from sqlalchemy.types import TypeDecorator


class UTCDateTime(TypeDecorator):
    """Store datetimes as UTC and return timezone-aware UTC values."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None

        if value.tzinfo is None:
            raise ValueError("Datetime must be timezone-aware.")

        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value, dialect):
        if value is None:
            return None

        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)

        return value.astimezone(UTC)
