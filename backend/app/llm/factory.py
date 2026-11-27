from langchain_ollama import ChatOllama

from app.core.config import Settings, settings


def create_chat_model(config: Settings | None = None) -> ChatOllama:
    """Create the configured Ollama chat model."""

    config = config or settings

    return ChatOllama(
        model=config.ollama_model,
        base_url=config.ollama_base_url,
        temperature=config.ollama_temperature,
    )