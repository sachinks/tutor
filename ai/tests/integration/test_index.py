"""Lesson index endpoints against a real PostgreSQL + pgvector: storage, atomic replacement, stale-version guard,
idempotency, deletion, reconciliation status, validation, provider failures and concurrency."""

import asyncio
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient

from tests.conftest import TOKEN, make_settings
from tutor_ai import indexing
from tutor_ai.db import create_engine
from tutor_ai.errors import AppError
from tutor_ai.main import create_app
from tutor_ai.providers.base import ProviderTimeout, ProviderUnavailable
from tutor_ai.providers.mock import MockProvider, hashed_embedding

pytestmark = pytest.mark.db

AUTH = {"Authorization": f"Bearer {TOKEN}"}


class DownProvider(MockProvider):
    async def embed(self, texts, *, kind):
        raise ProviderUnavailable("connection refused", provider=self.name)


class SlowProvider(MockProvider):
    async def embed(self, texts, *, kind):
        raise ProviderTimeout("read timeout after 180s", provider=self.name)


class WrongDimensionsProvider(MockProvider):
    async def embed(self, texts, *, kind):
        return [[1.0] * 10 for _ in texts]


class MissingVectorProvider(MockProvider):
    async def embed(self, texts, *, kind):
        return (await super().embed(texts, kind=kind))[:-1]


class NewModelProvider(MockProvider):
    embedding_model = "mock-hashed-bow-v2"


def client_for(database_url, provider=None):
    return TestClient(create_app(make_settings(AI_DATABASE_URL=database_url), provider=provider))


def connect(database_url):
    return psycopg.connect(database_url.replace("postgresql+psycopg://", "postgresql://", 1), autocommit=True)


def key():
    return f"test-{uuid.uuid4().hex}"


def headers(idempotency_key=None):
    return {**AUTH, "Idempotency-Key": idempotency_key or key()}


def lesson_body(version_no=1, version_id=None, course_id=None, **overrides):
    body = {
        "content_version_id": str(version_id or uuid.uuid4()),
        "version_no": version_no,
        "course_id": str(course_id or uuid.uuid4()),
        "subject": "Science",
        "class_number": 8,
        "title": "Photosynthesis",
        "sections": [
            {
                "heading": "What plants need",
                "blocks": [
                    {"type": "text", "text": "Plants need sunlight, water and carbon dioxide to make food."},
                    {"type": "image", "asset": "a1", "alt": "A leaf in sunlight"},
                ],
            },
            {"heading": "What plants make", "blocks": [{"type": "example", "text": "Leaves make glucose and oxygen."}]},
        ],
    }
    body.update(overrides)
    return body


def chunks_of(database_url, lesson_id):
    with connect(database_url) as conn:
        return conn.execute(
            "SELECT content_version_id, version_no, position, heading, text, embedding_model, vector_dims(embedding) "
            "FROM ai.lesson_chunk WHERE lesson_id = %s ORDER BY position",
            (lesson_id,),
        ).fetchall()


def test_index_stores_one_chunk_per_section_with_vectors(database_url):
    lesson_id, body = uuid.uuid4(), lesson_body()
    with client_for(database_url) as client:
        response = client.put(f"/v1/lessons/{lesson_id}/index", json=body, headers=headers())
    assert response.status_code == 200, response.text
    assert response.json() == {
        "lesson_id": str(lesson_id),
        "content_version_id": body["content_version_id"],
        "version_no": 1,
        "chunks": 2,
        "embedding_model": "mock-hashed-bow-v1",
        "status": "indexed",
    }
    rows = chunks_of(database_url, lesson_id)
    assert [(r[2], r[3]) for r in rows] == [(0, "What plants need"), (1, "What plants make")]
    assert rows[0][4] == "Plants need sunlight, water and carbon dioxide to make food.\n\n[Image: A leaf in sunlight]"
    assert all(r[1] == 1 and r[5] == "mock-hashed-bow-v1" and r[6] == 768 for r in rows)


def test_replaying_a_request_returns_the_original_result_without_redoing_it(database_url):
    lesson_id, body, k = uuid.uuid4(), lesson_body(), key()
    with client_for(database_url) as client:
        first = client.put(f"/v1/lessons/{lesson_id}/index", json=body, headers=headers(k))
        replay = client.put(f"/v1/lessons/{lesson_id}/index", json=body, headers=headers(k))
        other_body = client.put(f"/v1/lessons/{lesson_id}/index", json=lesson_body(version_no=2), headers=headers(k))
        other_lesson = client.put(f"/v1/lessons/{uuid.uuid4()}/index", json=body, headers=headers(k))
    assert first.json()["status"] == "indexed"
    assert replay.status_code == 200 and replay.json() == {**first.json(), "status": "unchanged"}
    for conflict in (other_body, other_lesson):
        assert conflict.status_code == 409 and conflict.json()["error"]["code"] == "idempotency_conflict"


def test_same_version_again_is_unchanged_and_keeps_the_rows(database_url):
    lesson_id, body = uuid.uuid4(), lesson_body()
    with client_for(database_url) as client:
        client.put(f"/v1/lessons/{lesson_id}/index", json=body, headers=headers())
        with connect(database_url) as conn:
            before = conn.execute("SELECT id FROM ai.lesson_chunk WHERE lesson_id = %s", (lesson_id,)).fetchall()
        again = client.put(f"/v1/lessons/{lesson_id}/index", json=body, headers=headers())
    assert again.status_code == 200 and again.json()["status"] == "unchanged" and again.json()["chunks"] == 2
    with connect(database_url) as conn:
        after = conn.execute("SELECT id FROM ai.lesson_chunk WHERE lesson_id = %s", (lesson_id,)).fetchall()
    assert before == after


def test_a_newer_version_replaces_the_old_one_completely(database_url):
    lesson_id, course_id = uuid.uuid4(), uuid.uuid4()
    v2 = lesson_body(
        version_no=2,
        course_id=course_id,
        sections=[{"heading": "Rewritten", "blocks": [{"type": "text", "text": "Chlorophyll captures light."}]}],
    )
    with client_for(database_url) as client:
        client.put(f"/v1/lessons/{lesson_id}/index", json=lesson_body(course_id=course_id), headers=headers())
        response = client.put(f"/v1/lessons/{lesson_id}/index", json=v2, headers=headers())
    assert response.json()["status"] == "indexed" and response.json()["chunks"] == 1
    rows = chunks_of(database_url, lesson_id)
    assert [(str(r[0]), r[1], r[3]) for r in rows] == [(v2["content_version_id"], 2, "Rewritten")]


def test_an_older_version_never_replaces_a_newer_one(database_url):
    lesson_id = uuid.uuid4()
    v3 = lesson_body(version_no=3)
    with client_for(database_url) as client:
        client.put(f"/v1/lessons/{lesson_id}/index", json=v3, headers=headers())
        late = client.put(f"/v1/lessons/{lesson_id}/index", json=lesson_body(version_no=2), headers=headers())
        same_number = client.put(f"/v1/lessons/{lesson_id}/index", json=lesson_body(version_no=3), headers=headers())
    for response in (late, same_number):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "stale_version"
        assert response.json()["error"]["fields"] == {"indexed_version_no": "3"}
    assert {str(r[0]) for r in chunks_of(database_url, lesson_id)} == {v3["content_version_id"]}


def test_a_new_embedding_model_reindexes_the_same_version(database_url):
    lesson_id, body = uuid.uuid4(), lesson_body()
    with client_for(database_url) as client:
        client.put(f"/v1/lessons/{lesson_id}/index", json=body, headers=headers())
    with client_for(database_url, provider=NewModelProvider()) as client:
        response = client.put(f"/v1/lessons/{lesson_id}/index", json=body, headers=headers())
    assert response.json()["status"] == "indexed"
    assert {r[5] for r in chunks_of(database_url, lesson_id)} == {"mock-hashed-bow-v2"}


def test_delete_removes_the_lesson_and_is_safe_to_repeat(database_url):
    lesson_id = uuid.uuid4()
    with client_for(database_url) as client:
        client.put(f"/v1/lessons/{lesson_id}/index", json=lesson_body(), headers=headers())
        k = key()
        first = client.delete(f"/v1/lessons/{lesson_id}/index", headers=headers(k))
        replay = client.delete(f"/v1/lessons/{lesson_id}/index", headers=headers(k))
        again = client.delete(f"/v1/lessons/{lesson_id}/index", headers=headers())
        never_indexed = client.delete(f"/v1/lessons/{uuid.uuid4()}/index", headers=headers())
    assert [r.status_code for r in (first, replay, again, never_indexed)] == [204, 204, 204, 204]
    assert first.content == b""
    assert chunks_of(database_url, lesson_id) == []


def test_a_delayed_delete_cannot_remove_a_newer_version(database_url):
    lesson_id = uuid.uuid4()
    with client_for(database_url) as client:
        client.put(f"/v1/lessons/{lesson_id}/index", json=lesson_body(version_no=4), headers=headers())
        stale = client.delete(f"/v1/lessons/{lesson_id}/index?up_to_version=3", headers=headers())
        current = client.delete(f"/v1/lessons/{lesson_id}/index?up_to_version=4", headers=headers())
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "stale_version"
    assert current.status_code == 204
    assert chunks_of(database_url, lesson_id) == []


def test_a_delete_key_cannot_be_reused_for_another_lesson(database_url):
    k = key()
    with client_for(database_url) as client:
        client.delete(f"/v1/lessons/{uuid.uuid4()}/index", headers=headers(k))
        reused = client.delete(f"/v1/lessons/{uuid.uuid4()}/index", headers=headers(k))
    assert reused.status_code == 409 and reused.json()["error"]["code"] == "idempotency_conflict"


def test_status_lists_every_indexed_lesson(database_url):
    first, second = uuid.uuid4(), uuid.uuid4()
    body = lesson_body(version_no=5)
    with client_for(database_url) as client:
        client.put(f"/v1/lessons/{first}/index", json=body, headers=headers())
        client.put(f"/v1/lessons/{second}/index", json=lesson_body(), headers=headers())
        client.delete(f"/v1/lessons/{second}/index", headers=headers())
        response = client.get("/v1/index/status", headers=AUTH)
    assert response.status_code == 200
    data = response.json()
    assert data["embedding_model"] == "mock-hashed-bow-v1"
    listed = {row["lesson_id"]: row for row in data["lessons"]}
    assert str(second) not in listed
    row = listed[str(first)]
    assert row["content_version_id"] == body["content_version_id"]
    assert (row["version_no"], row["chunks"], row["embedding_model"]) == (5, 2, "mock-hashed-bow-v1")
    assert row["indexed_at"]


@pytest.mark.parametrize(
    ("mutate", "field"),
    [
        (lambda b: b.update(sections=[]), "sections"),
        (lambda b: b.update(version_no=0), "version_no"),
        (lambda b: b.update(class_number=13), "class_number"),
        (lambda b: b.update(subject=""), "subject"),
        (lambda b: b.update(title="x" * 151), "title"),
        (lambda b: b.update(course_id="not-a-uuid"), "course_id"),
        (lambda b: b.update(unexpected=True), "unexpected"),
        (lambda b: b.pop("content_version_id"), "content_version_id"),
        (lambda b: b["sections"][0].update(heading="h" * 201), "sections.0.heading"),
        (lambda b: b["sections"][0]["blocks"][0].update(text="x" * 20_001), "sections.0.blocks.0.text"),
        (lambda b: b.update(sections=[{"heading": "s", "blocks": []}] * 201), "sections"),
    ],
)
def test_invalid_bodies_are_refused_with_the_field_named(database_url, mutate, field):
    body = lesson_body()
    mutate(body)
    with client_for(database_url) as client:
        response = client.put(f"/v1/lessons/{uuid.uuid4()}/index", json=body, headers=headers())
    assert response.status_code == 400, response.text
    assert response.json()["error"]["code"] == "validation_error"
    assert field in response.json()["error"]["fields"]


def test_a_lesson_over_the_total_size_limit_is_refused(database_url):
    big = [{"type": "text", "text": "word " * 3_999} for _ in range(30)]  # 30 × 19,995 characters ≈ 600k
    body = lesson_body(sections=[{"heading": f"s{i}", "blocks": big[:10]} for i in range(3)])
    with client_for(database_url) as client:
        response = client.put(f"/v1/lessons/{uuid.uuid4()}/index", json=body, headers=headers())
    assert response.status_code == 400
    assert "limit" in response.json()["error"]["fields"]["non_field"]


def test_the_idempotency_key_is_required_and_checked(database_url):
    url = f"/v1/lessons/{uuid.uuid4()}/index"
    with client_for(database_url) as client:
        missing = client.put(url, json=lesson_body(), headers=AUTH)
        short = client.put(url, json=lesson_body(), headers={**AUTH, "Idempotency-Key": "abc"})
        spaces = client.delete(url, headers={**AUTH, "Idempotency-Key": "has spaces in it"})
        bad_path = client.put("/v1/lessons/not-a-uuid/index", json=lesson_body(), headers=headers())
    for response in (missing, short, spaces):
        assert response.status_code == 400
        assert "Idempotency-Key" in response.json()["error"]["fields"]
    assert bad_path.status_code == 400 and "lesson_id" in bad_path.json()["error"]["fields"]


def test_a_lesson_without_text_is_refused(database_url):
    body = lesson_body(sections=[{"heading": "Pictures only", "blocks": [{"type": "image", "asset": "x"}]}])
    with client_for(database_url) as client:
        response = client.put(f"/v1/lessons/{uuid.uuid4()}/index", json=body, headers=headers())
    assert response.status_code == 400 and response.json()["error"]["code"] == "empty_lesson"


def test_provider_outage_is_a_503_and_leaves_the_index_untouched(database_url):
    lesson_id, k, v2 = uuid.uuid4(), key(), lesson_body(version_no=2)
    with client_for(database_url) as client:
        client.put(f"/v1/lessons/{lesson_id}/index", json=lesson_body(), headers=headers())
    before = chunks_of(database_url, lesson_id)
    with client_for(database_url, provider=DownProvider()) as client:
        response = client.put(f"/v1/lessons/{lesson_id}/index", json=v2, headers=headers(k))
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "provider_unavailable"
    assert "connection refused" not in response.text  # details stay in the log
    assert chunks_of(database_url, lesson_id) == before
    with connect(database_url) as conn:
        event = conn.execute("SELECT status, error FROM ai.index_event WHERE idempotency_key = %s", (k,)).fetchone()
    assert event == ("failed", "connection refused")
    # The same request retried once the provider is back succeeds with the same key.
    with client_for(database_url) as client:
        retried = client.put(f"/v1/lessons/{lesson_id}/index", json=v2, headers=headers(k))
    assert retried.status_code == 200 and retried.json()["status"] == "indexed"


def test_wrong_sized_embeddings_are_refused(database_url):
    with client_for(database_url, provider=WrongDimensionsProvider()) as client:
        response = client.put(f"/v1/lessons/{uuid.uuid4()}/index", json=lesson_body(), headers=headers())
    assert response.status_code == 502 and response.json()["error"]["code"] == "provider_error"


def test_a_missing_embedding_is_refused(database_url):
    with client_for(database_url, provider=MissingVectorProvider()) as client:
        response = client.put(f"/v1/lessons/{uuid.uuid4()}/index", json=lesson_body(), headers=headers())
    assert response.status_code == 502 and response.json()["error"]["code"] == "provider_error"


def run(database_url, operation):
    """Run one indexing coroutine against its own engine (for cases the HTTP layer can't reach)."""

    async def main():
        engine = create_engine(database_url)
        try:
            return await operation(engine)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def document(sections, version_no=1):
    return indexing.LessonDocument(
        lesson_id=uuid.uuid4(),
        content_version_id=uuid.uuid4(),
        version_no=version_no,
        course_id=uuid.uuid4(),
        subject="Science",
        class_number=8,
        title="Long lesson",
        sections=sections,
    )


def test_a_lesson_with_too_many_passages_is_refused(database_url):
    sections = [{"heading": f"s{i}", "blocks": [{"type": "text", "text": "Fact."}]} for i in range(401)]
    with pytest.raises(AppError) as refused:
        run(database_url, lambda engine: indexing.index_lesson(engine, MockProvider(), document(sections), key()))
    assert refused.value.code == "lesson_too_large"


def test_a_failure_to_record_a_failure_keeps_the_provider_error(database_url, caplog):
    too_long_key = "k" * 150  # longer than the column, so recording the failed event fails too
    doc = document([{"heading": "h", "blocks": [{"type": "text", "text": "Fact."}]}])
    with pytest.raises(ProviderUnavailable):
        run(database_url, lambda engine: indexing.index_lesson(engine, DownProvider(), doc, too_long_key))
    assert any("could not record a failed index event" in r.getMessage() for r in caplog.records)


def test_provider_timeout_is_a_504(database_url):
    with client_for(database_url, provider=SlowProvider()) as client:
        response = client.put(f"/v1/lessons/{uuid.uuid4()}/index", json=lesson_body(), headers=headers())
    assert response.status_code == 504 and response.json()["error"]["code"] == "provider_timeout"


def test_index_endpoints_need_the_service_token(database_url):
    lesson = f"/v1/lessons/{uuid.uuid4()}/index"
    with client_for(database_url) as client:
        responses = [
            client.put(lesson, json=lesson_body(), headers={"Idempotency-Key": key()}),
            client.delete(lesson, headers={"Idempotency-Key": key()}),
            client.get("/v1/index/status"),
        ]
    assert [r.status_code for r in responses] == [401, 401, 401]


def test_indexed_passages_are_retrievable_by_similarity(database_url):
    course_id = uuid.uuid4()
    plants = lesson_body(course_id=course_id)
    fractions = lesson_body(
        course_id=course_id,
        title="Fractions",
        sections=[{"heading": "Halves", "blocks": [{"type": "text", "text": "A half is one of two equal parts."}]}],
    )
    with client_for(database_url) as client:
        client.put(f"/v1/lessons/{uuid.uuid4()}/index", json=plants, headers=headers())
        client.put(f"/v1/lessons/{uuid.uuid4()}/index", json=fractions, headers=headers())
    query = "[" + ",".join(str(v) for v in hashed_embedding("what gas do leaves make, oxygen?", 768)) + "]"
    with connect(database_url) as conn:
        best = conn.execute(
            "SELECT heading FROM ai.lesson_chunk WHERE course_id = %s ORDER BY embedding <=> %s::vector LIMIT 1",
            (course_id, query),
        ).fetchone()
    assert best == ("What plants make",)


def test_concurrent_versions_of_one_lesson_end_with_the_newest(database_url):
    lesson_id = uuid.uuid4()
    provider = MockProvider()

    def doc(version_no):
        body = lesson_body(version_no=version_no)
        return indexing.LessonDocument(
            lesson_id=lesson_id,
            content_version_id=uuid.UUID(body["content_version_id"]),
            version_no=version_no,
            course_id=uuid.UUID(body["course_id"]),
            subject="Science",
            class_number=8,
            title=f"Version {version_no}",
            sections=body["sections"],
        )

    async def race():
        engine = create_engine(database_url)
        try:
            docs = [doc(n) for n in (2, 5, 3, 4, 1)]
            results = await asyncio.gather(
                *(indexing.index_lesson(engine, provider, d, key()) for d in docs), return_exceptions=True
            )
            return results, await indexing.indexed_lessons(engine)
        finally:
            await engine.dispose()

    results, indexed = asyncio.run(race())
    for result in results:  # each call either indexed its version or was refused as stale; nothing else
        assert not isinstance(result, BaseException) or (
            isinstance(result, AppError) and result.code == "stale_version"
        )
    mine = [lesson for lesson in indexed if lesson.lesson_id == lesson_id]
    assert len(mine) == 1 and mine[0].version_no == 5
    assert {r[1] for r in chunks_of(database_url, lesson_id)} == {5}
