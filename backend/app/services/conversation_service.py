import base64
import binascii
import json
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message
from app.repositories import ConversationRepository
from app.services.exceptions import (
    ConversationNotFoundError,
    InvalidConversationDataError,
)


class ConversationService:
    DEFAULT_PAGE_SIZE = 50
    MAX_PAGE_SIZE = 100

    VALID_ROLES = {"user", "assistant"}

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repository = ConversationRepository(session)

    # -------------------------
    # Validation
    # -------------------------

    def _validate_thread_id(self, thread_id: str) -> None:
        if (
            not isinstance(thread_id, str)
            or not thread_id.strip()
            or len(thread_id) > 36
        ):
            raise InvalidConversationDataError(
                "Thread ID must be a non-empty string of at most 36 characters."
            )

    def _validate_message(self, role: str, content: str) -> None:
        if role not in self.VALID_ROLES:
            raise InvalidConversationDataError(
                "Message role must be user or assistant."
            )

        if not isinstance(content, str) or not content.strip():
            raise InvalidConversationDataError(
                "Message content cannot be empty."
            )

    def _validate_limit(self, limit: int) -> None:
        if type(limit) is not int or not 1 <= limit <= self.MAX_PAGE_SIZE:
            raise InvalidConversationDataError(
                f"Limit must be between 1 and {self.MAX_PAGE_SIZE}."
            )

    # -------------------------
    # Cursor handling
    # -------------------------

    def _encode_cursor(self, message: Message) -> str:
        payload = {
            "created_at": message.created_at.isoformat(),
            "id": message.id,
        }

        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":")).encode("utf-8")
        )

        return encoded.decode("ascii").rstrip("=")

    def _decode_cursor(
        self,
        cursor: str | None,
    ) -> tuple[datetime, str] | None:
        if cursor is None:
            return None

        if not isinstance(cursor, str) or not cursor:
            raise InvalidConversationDataError("Invalid pagination cursor.")

        try:
            padded_cursor = cursor + "=" * (-len(cursor) % 4)

            decoded = base64.b64decode(
                padded_cursor,
                altchars=b"-_",
                validate=True,
            )

            payload = json.loads(decoded)

            created_at = datetime.fromisoformat(payload["created_at"])
            message_id = payload["id"]

            if created_at.tzinfo is None or not isinstance(message_id, str):
                raise ValueError("Invalid cursor values.")

            return created_at.astimezone(UTC), message_id

        except (
            ValueError,
            TypeError,
            KeyError,
            binascii.Error,
            json.JSONDecodeError,
        ) as exc:
            raise InvalidConversationDataError(
                "Invalid pagination cursor."
            ) from exc

    # -------------------------
    # Conversation creation
    # -------------------------

    async def create_conversation(
        self,
        thread_id: str,
    ) -> Conversation:
        self._validate_thread_id(thread_id)

        try:
            conversation = Conversation(thread_id=thread_id)

            created = await self.repository.create(conversation)
            await self.session.commit()

            return created

        except Exception:
            await self.session.rollback()
            raise

    # -------------------------
    # Conversation retrieval
    # -------------------------

    async def get_conversation(
        self,
        thread_id: str,
    ) -> Conversation:
        self._validate_thread_id(thread_id)

        conversation = await self.repository.get_by_thread_id(thread_id)

        if conversation is None:
            raise ConversationNotFoundError(
                f"Conversation '{thread_id}' was not found."
            )

        return conversation

    # -------------------------
    # Message creation
    # -------------------------

    async def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
    ) -> Message:
        self._validate_thread_id(thread_id)
        self._validate_message(role, content)

        try:
            await self.get_conversation(thread_id)

            message = Message(
                conversation_id=thread_id,
                role=role,
                content=content,
            )

            created = await self.repository.add_message(message)
            await self.session.commit()

            return created

        except Exception:
            await self.session.rollback()
            raise

    # -------------------------
    # Paginated history
    # -------------------------

    async def get_history(
        self,
        thread_id: str,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> dict:
        self._validate_thread_id(thread_id)
        self._validate_limit(limit)

        await self.get_conversation(thread_id)

        decoded_cursor = self._decode_cursor(cursor)

        messages = await self.repository.get_history_page(
            thread_id=thread_id,
            limit=limit + 1,
            cursor=decoded_cursor,
        )

        has_more = len(messages) > limit
        messages = messages[:limit]

        next_cursor = (
            self._encode_cursor(messages[-1])
            if has_more and messages
            else None
        )

        return {
            "thread_id": thread_id,
            "messages": [
                {
                    "message_id": message.id,
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at,
                }
                for message in messages
            ],
            "next_cursor": next_cursor,
            "has_more": has_more,
        }

    # -------------------------
    # Recent messages for context
    # -------------------------

    async def get_recent_messages(
        self,
        thread_id: str,
        limit: int,
    ) -> list[Message]:
        self._validate_thread_id(thread_id)
        self._validate_limit(limit)

        await self.get_conversation(thread_id)

        return await self.repository.get_recent_messages(
            thread_id=thread_id,
            limit=limit,
        )
