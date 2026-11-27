from datetime import UTC, datetime

import pytest
import pytest_asyncio
from app.database.base import Base
from app.models import Message
from app.services import ConversationService
from app.services.exceptions import (
    ConversationNotFoundError,
    InvalidConversationDataError,
)
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:"
    )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    SessionLocal = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    async with SessionLocal() as session:
        yield session

    await engine.dispose()


@pytest.fixture
def conversation_service(db_session):
    return ConversationService(db_session)


@pytest.mark.asyncio
async def test_create_conversation(conversation_service):
    conversation = await conversation_service.create_conversation(
        "thread-001"
    )

    assert conversation.thread_id == "thread-001"
    assert conversation.created_at is not None
    assert conversation.updated_at is not None


@pytest.mark.asyncio
async def test_get_conversation(conversation_service):
    created = await conversation_service.create_conversation(
        "thread-001"
    )

    retrieved = await conversation_service.get_conversation(
        created.thread_id
    )

    assert retrieved.thread_id == created.thread_id


@pytest.mark.asyncio
async def test_get_conversation_rejects_missing_thread(
    conversation_service,
):
    with pytest.raises(ConversationNotFoundError):
        await conversation_service.get_conversation("missing-thread")


@pytest.mark.asyncio
async def test_create_conversation_rejects_invalid_thread_id(
    conversation_service,
):
    with pytest.raises(InvalidConversationDataError):
        await conversation_service.create_conversation("")


@pytest.mark.asyncio
async def test_add_user_and_assistant_messages(conversation_service):
    await conversation_service.create_conversation("thread-001")

    user_message = await conversation_service.add_message(
        "thread-001",
        "user",
        "Create a task",
    )

    assistant_message = await conversation_service.add_message(
        "thread-001",
        "assistant",
        "Your task has been created.",
    )

    assert user_message.role == "user"
    assert user_message.content == "Create a task"
    assert assistant_message.role == "assistant"
    assert assistant_message.content == "Your task has been created."


@pytest.mark.asyncio
async def test_add_message_rejects_invalid_role(conversation_service):
    await conversation_service.create_conversation("thread-001")

    with pytest.raises(InvalidConversationDataError):
        await conversation_service.add_message(
            "thread-001",
            "system",
            "Internal message",
        )


@pytest.mark.asyncio
async def test_add_message_rejects_empty_content(conversation_service):
    await conversation_service.create_conversation("thread-001")

    with pytest.raises(InvalidConversationDataError):
        await conversation_service.add_message(
            "thread-001",
            "user",
            "   ",
        )


@pytest.mark.asyncio
async def test_add_message_rejects_missing_conversation(
    conversation_service,
):
    with pytest.raises(ConversationNotFoundError):
        await conversation_service.add_message(
            "missing-thread",
            "user",
            "Hello",
        )


@pytest.mark.asyncio
async def test_get_history_returns_messages(conversation_service):
    await conversation_service.create_conversation("thread-001")

    await conversation_service.add_message(
        "thread-001",
        "user",
        "Hello",
    )
    await conversation_service.add_message(
        "thread-001",
        "assistant",
        "Hi!",
    )

    history = await conversation_service.get_history("thread-001")

    assert history["thread_id"] == "thread-001"
    assert len(history["messages"]) == 2
    assert history["messages"][0]["role"] == "user"
    assert history["messages"][1]["role"] == "assistant"
    assert history["next_cursor"] is None
    assert history["has_more"] is False


@pytest.mark.asyncio
async def test_history_uses_cursor_pagination(
    conversation_service,
    db_session,
):
    await conversation_service.create_conversation("thread-001")

    timestamp = datetime(2026, 11, 26, 10, 0, tzinfo=UTC)

    db_session.add_all(
        [
            Message(
                id=f"msg-00{i}",
                conversation_id="thread-001",
                role="user" if i % 2 else "assistant",
                content=f"Message {i}",
                created_at=timestamp,
            )
            for i in range(1, 4)
        ]
    )
    await db_session.commit()

    first_page = await conversation_service.get_history(
        "thread-001",
        limit=2,
    )

    assert [m["message_id"] for m in first_page["messages"]] == [
        "msg-001",
        "msg-002",
    ]
    assert first_page["has_more"] is True
    assert first_page["next_cursor"] is not None

    second_page = await conversation_service.get_history(
        "thread-001",
        limit=2,
        cursor=first_page["next_cursor"],
    )

    assert [m["message_id"] for m in second_page["messages"]] == [
        "msg-003",
    ]
    assert second_page["has_more"] is False
    assert second_page["next_cursor"] is None


@pytest.mark.asyncio
async def test_history_returns_empty_messages_for_new_conversation(
    conversation_service,
):
    await conversation_service.create_conversation("thread-001")

    history = await conversation_service.get_history("thread-001")

    assert history["messages"] == []
    assert history["next_cursor"] is None
    assert history["has_more"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("limit", [0, -1, 101, "50"])
async def test_history_rejects_invalid_limit(
    conversation_service,
    limit,
):
    await conversation_service.create_conversation("thread-001")

    with pytest.raises(InvalidConversationDataError):
        await conversation_service.get_history(
            "thread-001",
            limit=limit,
        )


@pytest.mark.asyncio
async def test_history_rejects_invalid_cursor(conversation_service):
    await conversation_service.create_conversation("thread-001")

    with pytest.raises(InvalidConversationDataError):
        await conversation_service.get_history(
            "thread-001",
            cursor="invalid-cursor",
        )


@pytest.mark.asyncio
async def test_get_recent_messages_returns_chronological_order(
    conversation_service,
    db_session,
):
    await conversation_service.create_conversation("thread-001")

    timestamp = datetime(2026, 11, 26, 10, 0, tzinfo=UTC)

    db_session.add_all(
        [
            Message(
                id=f"msg-00{i}",
                conversation_id="thread-001",
                role="user",
                content=f"Message {i}",
                created_at=timestamp.replace(minute=i),
            )
            for i in range(1, 4)
        ]
    )
    await db_session.commit()

    messages = await conversation_service.get_recent_messages(
        "thread-001",
        limit=2,
    )

    assert [message.content for message in messages] == [
        "Message 2",
        "Message 3",
    ]


@pytest.mark.asyncio
async def test_add_message_rolls_back_when_commit_fails(
    conversation_service,
    monkeypatch,
):
    await conversation_service.create_conversation("thread-001")

    async def fail_commit():
        raise RuntimeError("Simulated database failure")

    monkeypatch.setattr(
        conversation_service.session,
        "commit",
        fail_commit,
    )

    with pytest.raises(RuntimeError, match="Simulated database failure"):
        await conversation_service.add_message(
            "thread-001",
            "user",
            "Temporary message",
        )

    history = await conversation_service.get_history("thread-001")

    assert history["messages"] == []
