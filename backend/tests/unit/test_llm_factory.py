from app.core.config import Settings
from app.llm import factory


def test_create_chat_model_uses_provided_settings(monkeypatch):
    captured = {}

    class FakeChatOllama:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(factory, "ChatOllama", FakeChatOllama)

    config = Settings(
        _env_file=None,
        ollama_model="gemma4:e4b",
        ollama_base_url="http://127.0.0.1:11434",
        ollama_temperature=0.0,
    )

    model = factory.create_chat_model(config)

    assert isinstance(model, FakeChatOllama)
    assert captured == {
        "model": "gemma4:e4b",
        "base_url": "http://127.0.0.1:11434",
        "temperature": 0.0,
    }


def test_create_chat_model_uses_application_settings(monkeypatch):
    captured = {}

    class FakeChatOllama:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(factory, "ChatOllama", FakeChatOllama)

    config = Settings(
        _env_file=None,
        ollama_model="gemma4:e4b",
        ollama_base_url="http://localhost:11434",
        ollama_temperature=0.0,
    )

    monkeypatch.setattr(factory, "settings", config)

    factory.create_chat_model()

    assert captured == {
        "model": "gemma4:e4b",
        "base_url": "http://localhost:11434",
        "temperature": 0.0,
    }