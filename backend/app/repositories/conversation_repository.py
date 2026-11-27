from datetime import UTC, datetime

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Conversation, Message


class ConversationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, conversation: Conversation) -> Conversation:
        """Insert a new conversation."""
        self.session.add(conversation)

        await self.session.flush()
        await self.session.refresh(conversation)

        return conversation

    async def get_by_thread_id(
        self,
        thread_id: str,
    ) -> Conversation | None:
        """Retrieve a conversation using its thread ID."""
        return await self.session.get(Conversation, thread_id)

    async def add_message(self, message: Message) -> Message:
        """Persist a user-visible conversation message."""
        self.session.add(message)

        await self.session.execute(
            update(Conversation)
            .where(Conversation.thread_id == message.conversation_id)
            .values(updated_at=datetime.now(UTC))
        )

        await self.session.flush()
        await self.session.refresh(message)

        return message

    async def get_history_page(
        self,
        thread_id: str,
        limit: int,
        cursor: tuple[datetime, str] | None = None,
    ) -> list[Message]:
        """Retrieve a chronological page of messages after the cursor.

        The caller supplies limit + 1 as needed to determine whether
        another page exists.
        """
        statement = select(Message).where(
            Message.conversation_id == thread_id
        )

        if cursor is not None:
            cursor_created_at, cursor_message_id = cursor

            statement = statement.where(
                or_(
                    Message.created_at > cursor_created_at,
                    and_(
                        Message.created_at == cursor_created_at,
                        Message.id > cursor_message_id,
                    ),
                )
            )

        statement = (
            statement
            .order_by(Message.created_at.asc(), Message.id.asc())
            .limit(limit)
        )

        result = await self.session.execute(statement)

        return list(result.scalars().all())

    async def get_recent_messages(
        self,
        thread_id: str,
        limit: int,
    ) -> list[Message]:
        """Retrieve the most recent messages in chronological order."""
        statement = (
            select(Message)
            .where(Message.conversation_id == thread_id)
            .order_by(Message.created_at.desc(), Message.id.desc())
            .limit(limit)
        )

        result = await self.session.execute(statement)
        messages = list(result.scalars().all())

        return list(reversed(messages))
