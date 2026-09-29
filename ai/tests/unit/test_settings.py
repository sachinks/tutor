import pytest
from pydantic import ValidationError

from tests.conftest import PREVIOUS_TOKEN, TOKEN, make_settings


def test_defaults_are_safe_for_tests_and_ci():
    settings = make_settings()
    assert settings.provider == "mock"
    assert settings.embedding_dimensions == 768
    assert settings.ollama_chat_model == "llama3.2"


@pytest.mark.parametrize(
    "given",
    ["postgres://u:p@h:5432/db", "postgresql://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"],
)
def test_database_url_uses_the_async_psycopg_driver(given):
    assert make_settings(AI_DATABASE_URL=given).database_url.get_secret_value() == "postgresql+psycopg://u:p@h:5432/db"


def test_non_postgres_url_is_refused():
    with pytest.raises(ValidationError):
        make_settings(AI_DATABASE_URL="mysql://u:p@h/db")


def test_short_tokens_are_refused():
    with pytest.raises(ValidationError):
        make_settings(TUTOR_AI_SERVICE_TOKEN="short")
    with pytest.raises(ValidationError):
        make_settings(TUTOR_AI_SERVICE_TOKEN_PREVIOUS="short")


def test_token_rotation_accepts_both_tokens():
    assert make_settings().accepted_tokens == [TOKEN]
    assert make_settings(TUTOR_AI_SERVICE_TOKEN_PREVIOUS=PREVIOUS_TOKEN).accepted_tokens == [TOKEN, PREVIOUS_TOKEN]


def test_secrets_are_not_printed():
    text = repr(make_settings())
    assert TOKEN not in text
    assert "pass@" not in text


@pytest.mark.parametrize(
    ("environment", "provider"), [("hosted", "ollama"), ("production", "ollama"), ("production", "mock")]
)
def test_unsafe_provider_for_environment_is_refused(environment, provider):
    with pytest.raises(ValidationError):
        make_settings(TUTOR_ENV=environment, TUTOR_AI_PROVIDER=provider)


def test_hosted_demo_with_mock_is_allowed():
    assert make_settings(TUTOR_ENV="hosted", TUTOR_AI_PROVIDER="mock").provider == "mock"


def test_unknown_provider_is_refused():
    with pytest.raises(ValidationError):
        make_settings(TUTOR_AI_PROVIDER="gpt")
