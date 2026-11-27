
import pytest
from app.core.config import Settings
from pydantic import ValidationError


def test_default_ollama_configuration():
    settings = Settings(_env_file=None)

    assert settings.ollama_base_url == "http://localhost:11434"
    assert settings.ollama_model == "gemma4:e4b"
    assert settings.ollama_temperature == 0.0


def test_ollama_model_can_be_overridden_by_environment(monkeypatch):
    monkeypatch.setenv("OLLAMA_MODEL", "another-model")

    settings = Settings(_env_file=None)

    assert settings.ollama_model == "another-model"


def test_ollama_model_rejects_empty_value():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ollama_model="")


def test_ollama_model_rejects_whitespace():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ollama_model="   ")


@pytest.mark.parametrize("temperature", [-0.1, 2.1])
def test_ollama_temperature_rejects_invalid_values(temperature):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, ollama_temperature=temperature)


def test_ollama_temperature_accepts_valid_value():
    settings = Settings(_env_file=None, ollama_temperature=0.5)

    assert settings.ollama_temperature == 0.5
