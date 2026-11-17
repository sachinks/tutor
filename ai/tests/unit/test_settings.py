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


KEY = "test-gemini-key"


@pytest.mark.parametrize(
    "config",
    [
        {"TUTOR_AI_PROVIDER": "gemini"},
        {"TUTOR_AI_PROVIDER": "gateway", "TUTOR_GATEWAY_PRIMARY": "gemini", "TUTOR_GATEWAY_FALLBACK": "none"},
        {"TUTOR_AI_PROVIDER": "gateway", "TUTOR_GATEWAY_PRIMARY": "gemini", "TUTOR_GATEWAY_FALLBACK": "mock"},
    ],
)
def test_gemini_is_refused_in_production_however_it_is_configured(config):
    """D44: Google's Gemini API terms exclude apps for under-18s, so production can never route a student to it."""
    with pytest.raises(ValidationError, match="D44"):
        make_settings(TUTOR_ENV="production", TUTOR_GEMINI_API_KEY=KEY, **config)


def test_gemini_as_gateway_fallback_is_refused_in_production():
    with pytest.raises(ValidationError):
        make_settings(
            TUTOR_ENV="production",
            TUTOR_AI_PROVIDER="gateway",
            TUTOR_GATEWAY_PRIMARY="mock",
            TUTOR_GATEWAY_FALLBACK="gemini",
            TUTOR_GEMINI_API_KEY=KEY,
        )


@pytest.mark.parametrize("environment", ["local", "test", "hosted"])
def test_gemini_is_allowed_for_development_and_demo(environment):
    settings = make_settings(
        TUTOR_ENV=environment,
        TUTOR_AI_PROVIDER="gateway",
        TUTOR_GATEWAY_PRIMARY="gemini",
        TUTOR_GATEWAY_FALLBACK="mock",
        TUTOR_GEMINI_API_KEY=KEY,
    )
    assert settings.providers_in_use == {"gemini", "mock"}


def test_gemini_needs_a_key():
    with pytest.raises(ValidationError, match="TUTOR_GEMINI_API_KEY"):
        make_settings(TUTOR_AI_PROVIDER="gemini")


def test_hosted_gateway_cannot_fall_back_to_a_laptop_ollama():
    with pytest.raises(ValidationError, match="Ollama"):
        make_settings(
            TUTOR_ENV="hosted",
            TUTOR_AI_PROVIDER="gateway",
            TUTOR_GATEWAY_PRIMARY="gemini",
            TUTOR_GATEWAY_FALLBACK="ollama",
            TUTOR_GEMINI_API_KEY=KEY,
        )


def test_hosted_demo_with_mock_is_allowed():
    assert make_settings(TUTOR_ENV="hosted", TUTOR_AI_PROVIDER="mock").provider == "mock"


def test_unknown_provider_is_refused():
    with pytest.raises(ValidationError):
        make_settings(TUTOR_AI_PROVIDER="gpt")
