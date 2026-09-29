"""Retrieval against real pgvector: course and model filters, thresholds, pinned passages and the context budget."""

import asyncio
import uuid

import pytest

from tutor_ai import indexing, retrieval
from tutor_ai.db import create_engine
from tutor_ai.providers.mock import MockProvider, hashed_embedding

pytestmark = pytest.mark.db

MOCK = MockProvider()


class OtherModelProvider(MockProvider):
    embedding_model = "mock-hashed-bow-v2"


def run(database_url, operation):
    async def main():
        engine = create_engine(database_url)
        try:
            return await operation(engine)
        finally:
            await engine.dispose()

    return asyncio.run(main())


def doc(course_id, title, *sections, lesson_id=None):
    return indexing.LessonDocument(
        lesson_id=lesson_id or uuid.uuid4(),
        content_version_id=uuid.uuid4(),
        version_no=1,
        course_id=course_id,
        subject="Science",
        class_number=8,
        title=title,
        sections=[{"heading": h, "blocks": [{"type": "text", "text": t}]} for h, t in sections],
    )


@pytest.fixture(scope="module")
def world(database_url):
    """Two courses. Course A: a photosynthesis lesson (3 sections), a respiration lesson, and a lesson indexed with
    another embedding model. Course B: a maths lesson that also mentions oxygen."""
    course_a, course_b = uuid.uuid4(), uuid.uuid4()
    photo = doc(
        course_a,
        "Photosynthesis",
        ("What plants need", "Plants need sunlight, water and carbon dioxide from the air."),
        ("Roots", "Roots take in water and minerals from the soil."),
        ("What leaves make", "Leaves make glucose and release oxygen into the air."),
    )
    breathing = doc(course_a, "Respiration", ("Breathing", "Animals breathe in oxygen and breathe out carbon dioxide."))
    other_model = doc(course_a, "Flowers", ("Petals", "Petals attract bees that carry pollen and oxygen."))
    maths = doc(course_b, "Ratios", ("Mixtures", "Air is about one fifth oxygen by volume."))

    async def index(engine):
        for d in (photo, breathing, maths):
            await indexing.index_lesson(engine, MOCK, d, f"t-{uuid.uuid4().hex}")
        await indexing.index_lesson(engine, OtherModelProvider(), other_model, f"t-{uuid.uuid4().hex}")

    run(database_url, index)
    return {"a": course_a, "b": course_b, "photo": photo, "breathing": breathing, "other": other_model, "maths": maths}


def query_vector(text):
    """What MockProvider.embed returns for a query, computed synchronously so it can be used inside coroutines."""
    return hashed_embedding(text, MOCK.dimensions)


def test_min_similarity_defaults_per_provider():
    assert retrieval.min_similarity(None, "mock") == 0.10
    assert retrieval.min_similarity(None, "ollama") == 0.45
    assert retrieval.min_similarity(None, "hosted") == retrieval.FALLBACK_MIN_SIMILARITY
    assert retrieval.min_similarity(0.3, "mock") == 0.3


def test_lesson_passages_come_in_lesson_order(database_url, world):
    async def op(engine):
        async with engine.connect() as conn:
            return await retrieval.lesson_passages(conn, world["photo"].lesson_id, MOCK.embedding_model)

    passages = run(database_url, op)
    assert [p.heading for p in passages] == ["What plants need", "Roots", "What leaves make"]
    assert [p.position for p in passages] == [0, 1, 2]
    assert all(p.similarity is None and p.token_count > 0 for p in passages)


def test_search_stays_in_the_course_and_embedding_model(database_url, world):
    vector = query_vector("oxygen")

    async def op(engine):
        async with engine.connect() as conn:
            return await retrieval.search(conn, vector, course_id=world["a"], model=MOCK.embedding_model, k=10)

    found = run(database_url, op)
    lessons = {p.lesson_id for p in found}
    assert world["maths"].lesson_id not in lessons  # other course
    assert world["other"].lesson_id not in lessons  # other embedding model
    assert {world["photo"].lesson_id, world["breathing"].lesson_id} <= lessons
    similarities = [p.similarity for p in found]
    assert similarities == sorted(similarities, reverse=True)
    assert found[0].heading in ("Breathing", "What leaves make")


def test_search_threshold_limit_and_exclusion(database_url, world):
    vector = query_vector("leaves glucose oxygen")

    async def op(engine):
        async with engine.connect() as conn:
            top = await retrieval.search(conn, vector, course_id=world["a"], model=MOCK.embedding_model, k=1)
            strict = await retrieval.search(
                conn, vector, course_id=world["a"], model=MOCK.embedding_model, k=10, minimum=0.99
            )
            others = await retrieval.search(
                conn,
                vector,
                course_id=world["a"],
                model=MOCK.embedding_model,
                k=10,
                exclude_lesson=world["photo"].lesson_id,
            )
            return top, strict, others

    top, strict, others = run(database_url, op)
    assert [p.heading for p in top] == ["What leaves make"]
    assert strict == []
    assert {p.lesson_id for p in others} == {world["breathing"].lesson_id}


def test_passages_by_id_keep_the_pinned_order_and_skip_missing_ones(database_url, world):
    async def op(engine):
        async with engine.connect() as conn:
            lesson = await retrieval.lesson_passages(conn, world["photo"].lesson_id, MOCK.embedding_model)
            ids = [lesson[2].chunk_id, uuid.uuid4(), lesson[0].chunk_id]
            plain = await retrieval.passages_by_id(conn, ids, MOCK.embedding_model)
            scored = await retrieval.passages_by_id(conn, ids, MOCK.embedding_model, query_vector("glucose"))
            wrong_model = await retrieval.passages_by_id(conn, ids, "another-model")
            empty = await retrieval.passages_by_id(conn, [], MOCK.embedding_model)
            return plain, scored, wrong_model, empty

    plain, scored, wrong_model, empty = run(database_url, op)
    assert [p.heading for p in plain] == ["What leaves make", "What plants need"]
    assert all(p.similarity is None for p in plain)
    assert scored[0].similarity > scored[1].similarity
    assert wrong_model == [] and empty == []


def test_best_similarity_tells_on_topic_from_off_topic(database_url, world):
    async def op(engine):
        async with engine.connect() as conn:
            ids = [
                p.chunk_id
                for p in await retrieval.lesson_passages(conn, world["photo"].lesson_id, MOCK.embedding_model)
            ]
            on = await retrieval.best_similarity(
                conn, ids, query_vector("why do roots take water"), MOCK.embedding_model
            )
            off = await retrieval.best_similarity(
                conn, ids, query_vector("who won the cricket match"), MOCK.embedding_model
            )
            none = await retrieval.best_similarity(conn, [uuid.uuid4()], query_vector("roots"), MOCK.embedding_model)
            empty = await retrieval.best_similarity(conn, [], query_vector("roots"), MOCK.embedding_model)
            return on, off, none, empty

    on, off, none, empty = run(database_url, op)
    threshold = retrieval.min_similarity(None, "mock")
    assert on >= threshold > off
    assert none is None and empty is None


def pin(database_url, world, *, query, budget, related_k=3, lesson="photo", minimum=0.10):
    return run(
        database_url,
        lambda engine: retrieval.pin_context(
            engine,
            MOCK,
            lesson_id=world[lesson].lesson_id,
            course_id=world["a"],
            query=query,
            budget_tokens=budget,
            related_k=related_k,
            minimum=minimum,
        ),
    )


def test_the_whole_lesson_is_pinned_when_it_fits_plus_related_passages(database_url, world):
    pinned = pin(database_url, world, query="what do leaves release, oxygen?", budget=1000)
    assert [p.heading for p in pinned[:3]] == ["What plants need", "Roots", "What leaves make"]
    assert all(p.similarity is None for p in pinned[:3])
    related = pinned[3:]
    assert [p.heading for p in related] == ["Breathing"]  # same course, other lesson, relevant enough
    assert related[0].similarity >= 0.10


def test_over_budget_keeps_the_most_relevant_passages_in_lesson_order(database_url, world):
    pinned = pin(database_url, world, query="roots water soil minerals", budget=14, related_k=0)
    assert [p.heading for p in pinned] == ["Roots"]
    both = pin(database_url, world, query="roots and leaves glucose", budget=24, related_k=0)
    assert [p.heading for p in both] == ["Roots", "What leaves make"]  # lesson order, not score order


def test_without_a_question_the_lesson_opening_is_pinned_and_nothing_else(database_url, world):
    pinned = pin(database_url, world, query=None, budget=14)
    assert [p.heading for p in pinned] == ["What plants need"]
    assert pin(database_url, world, query="   ", budget=1000)[3:] == []  # blank: no related search


def test_irrelevant_related_passages_are_left_out(database_url, world):
    pinned = pin(database_url, world, query="petals and bees", budget=1000, minimum=0.99)
    assert [p.heading for p in pinned] == ["What plants need", "Roots", "What leaves make"]


def test_an_unindexed_lesson_pins_nothing(database_url, world):
    world_with_missing = {**world, "missing": doc(world["a"], "Not indexed", ("x", "y"))}
    assert pin(database_url, world_with_missing, query="anything", budget=1000, lesson="missing") == []
