"""The running app against a real PostgreSQL: health, service-token security, request IDs, error shapes."""

import pytest
from fastapi.testclient import TestClient

from tests.conftest import PREVIOUS_TOKEN, TOKEN, make_settings
from tutor_ai.main import create_app
from tutor_ai.providers.mock import MockProvider

pytestmark = pytest.mark.db


class SickProvider(MockProvider):
    async def health(self) -> bool:
        return False


def client_for(database_url, provider=None, **settings):
    app = create_app(make_settings(AI_DATABASE_URL=database_url, **settings), provider=provider)

    @app.get("/boom", include_in_schema=False)
    async def boom() -> None:
        raise RuntimeError("secret internal detail")

    return TestClient(app, raise_server_exceptions=False)


def auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_health_ok_with_database_and_provider(database_url):
    with client_for(database_url) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"ok": True, "db": True, "provider": "mock", "provider_ok": True}


def test_health_503_when_the_provider_is_down(database_url):
    with client_for(database_url, provider=SickProvider()) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["provider_ok"] is False and response.json()["db"] is True


def test_health_503_when_the_database_is_down(database_url):
    unreachable = "postgresql://nobody:nothing@127.0.0.1:1/none"
    with client_for(unreachable) as client:
        response = client.get("/health")
    assert response.status_code == 503
    assert response.json()["db"] is False


def test_v1_needs_the_service_token(database_url):
    with client_for(database_url) as client:
        for headers in ({}, auth("x" * 40), {"Authorization": TOKEN}, {"Authorization": f"Basic {TOKEN}"}):
            response = client.get("/v1/whoami", headers=headers)
            assert response.status_code == 401, headers
            assert response.json()["error"]["code"] == "not_authenticated"
        ok = client.get("/v1/whoami", headers=auth())
    assert ok.status_code == 200
    assert ok.json() == {
        "service": "tutor-ai",
        "provider": "mock",
        "chat_model": "mock-tutor-v1",
        "embedding_model": "mock-hashed-bow-v1",
        "dimensions": 768,
        "prompts": {"tutor": "v1"},
    }


def test_previous_token_works_during_rotation(database_url):
    with client_for(database_url, TUTOR_AI_SERVICE_TOKEN_PREVIOUS=PREVIOUS_TOKEN) as client:
        assert client.get("/v1/whoami", headers=auth(PREVIOUS_TOKEN)).status_code == 200


def test_request_id_is_returned_and_in_errors(database_url):
    with client_for(database_url) as client:
        generated = client.get("/v1/whoami")
        kept = client.get("/v1/whoami", headers={"X-Request-ID": "django-req-12345"})
    assert len(generated.headers["X-Request-ID"]) == 32
    assert generated.json()["error"]["request_id"] == generated.headers["X-Request-ID"]
    assert kept.headers["X-Request-ID"] == "django-req-12345"


def test_unknown_path_and_wrong_method_use_the_error_shape(database_url):
    with client_for(database_url) as client:
        missing = client.get("/v1/nope", headers=auth())
        wrong = client.post("/health")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"
    assert wrong.status_code == 405 and wrong.json()["error"]["code"] == "method_not_allowed"


def test_unexpected_error_is_a_clean_500(database_url, caplog):
    with client_for(database_url) as client:
        response = client.get("/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "server_error"
    assert "secret internal detail" not in response.text
    assert any(r.exc_info for r in caplog.records if r.name == "tutor_ai.errors")


def test_docs_only_outside_hosted_environments(database_url):
    with client_for(database_url) as client:
        assert client.get("/docs").status_code == 200
    with client_for(database_url, TUTOR_ENV="hosted") as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
