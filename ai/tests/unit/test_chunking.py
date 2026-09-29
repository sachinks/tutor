"""The chunker: section boundaries, size limits, overlap, verbatim text, and determinism."""

import random
from itertools import pairwise

import pytest

from tutor_ai.chunking import MAX_TOKENS, OVERLAP_TOKENS, block_text, chunk_sections, count_tokens


def section(heading, *texts, blocks=None):
    return {"heading": heading, "blocks": blocks or [{"type": "text", "text": t} for t in texts]}


def paragraph(label, sentences=12):
    return " ".join(f"Sentence {label}-{i} explains how leaves use light energy." for i in range(sentences))


def test_count_tokens_counts_words_and_punctuation():
    assert count_tokens("Hello, world!") == 4
    assert count_tokens("") == 0
    assert count_tokens("x = 3.5") == 5  # x, =, 3, ., 5


@pytest.mark.parametrize(
    ("block", "expected"),
    [
        ({"type": "text", "text": "  Plain text.  "}, "Plain text."),
        ({"type": "example", "text": "Worked example."}, "Worked example."),
        ({"type": "image", "alt": "A leaf under a lens"}, "[Image: A leaf under a lens]"),
        ({"type": "image", "asset": "abc"}, ""),
        ({"type": "video"}, ""),
        ({"type": "callout", "text": None}, ""),
    ],
)
def test_block_text(block, expected):
    assert block_text(block) == expected


def test_one_chunk_per_short_section_in_order():
    chunks = chunk_sections(
        "Photosynthesis",
        [section("What plants need", "Light, water and carbon dioxide."), section("What they make", "Sugar.")],
    )
    assert [(c.position, c.heading, c.text) for c in chunks] == [
        (0, "What plants need", "Light, water and carbon dioxide."),
        (1, "What they make", "Sugar."),
    ]
    assert chunks[0].token_count == count_tokens(chunks[0].text)


def test_blocks_are_joined_with_blank_lines_and_images_contribute_alt_text():
    chunks = chunk_sections(
        "Leaves",
        [
            section(
                "Look closely",
                blocks=[
                    {"type": "text", "text": "Leaves have tiny pores."},
                    {"type": "image", "alt": "Stomata under a microscope"},
                    {"type": "image"},
                    {"type": "example", "text": "Count the pores in the picture."},
                ],
            )
        ],
    )
    assert len(chunks) == 1
    assert chunks[0].text == (
        "Leaves have tiny pores.\n\n[Image: Stomata under a microscope]\n\nCount the pores in the picture."
    )


def test_sections_without_text_are_skipped_and_positions_stay_contiguous():
    chunks = chunk_sections(
        "Lesson",
        [
            section("Empty", blocks=[{"type": "image"}]),
            section("First", "One."),
            {"heading": "No blocks"},
            section("Second", "Two."),
        ],
    )
    assert [(c.position, c.heading) for c in chunks] == [(0, "First"), (1, "Second")]


def test_embed_text_carries_title_and_heading_but_text_stays_verbatim():
    [chunk] = chunk_sections("Data", [section("What is data?", "Data is recorded facts.")])
    assert chunk.text == "Data is recorded facts."
    assert chunk.embed_text == "Data — What is data?\n\nData is recorded facts."
    [untitled] = chunk_sections("Data", [section("", "Facts.")])
    assert untitled.embed_text == "Data\n\nFacts."


def test_long_section_splits_on_paragraphs_within_the_limit():
    text = "\n\n".join(paragraph(p) for p in range(6))  # 6 paragraphs of ~120 tokens
    chunks = chunk_sections("Leaves", [section("Long", text)])
    assert len(chunks) > 1
    assert all(c.token_count <= MAX_TOKENS for c in chunks)
    assert all(c.heading == "Long" for c in chunks)
    for p in range(6):  # every paragraph's content survives
        assert any(f"Sentence {p}-5 " in c.text for c in chunks)


def test_consecutive_chunks_overlap_by_closing_sentences():
    text = "\n\n".join(paragraph(p) for p in range(6))
    chunks = chunk_sections("Leaves", [section("Long", text)])
    for before, after in pairwise(chunks):
        first_sentence = after.text.split(". ")[0] + "."
        assert first_sentence in before.text  # the next chunk starts with text the previous one ended with
        shared = count_tokens(first_sentence)
        assert shared <= OVERLAP_TOKENS


def test_overlap_is_dropped_when_it_would_not_fit_with_the_next_paragraph():
    near_limit = " ".join(f"word{i}" for i in range(MAX_TOKENS - 5))
    first = "A short first paragraph with exactly ten plain words here."  # 11 tokens: fits the overlap budget
    chunks = chunk_sections("T", [section("S", f"{first}\n\n{near_limit}")])
    assert [c.text for c in chunks] == [first, near_limit]  # 11 + 295 > 300, so the overlap is dropped


def test_overlong_paragraph_splits_on_sentences():
    long_paragraph = paragraph("x", sentences=60)  # ~600 tokens in one paragraph
    chunks = chunk_sections("T", [section("S", long_paragraph)])
    assert len(chunks) >= 2
    assert all(c.token_count <= MAX_TOKENS for c in chunks)
    assert all(c.text.endswith(".") for c in chunks)  # never cut mid-sentence


def test_overlong_sentence_splits_on_words():
    run_on = " ".join(f"item{i}" for i in range(2 * MAX_TOKENS + 10))
    chunks = chunk_sections("T", [section("S", run_on)])
    assert len(chunks) >= 3
    assert all(c.token_count <= MAX_TOKENS for c in chunks)
    words = set(run_on.split())
    assert words == set(" ".join(c.text for c in chunks).split())  # nothing lost


def test_the_same_lesson_always_gives_the_same_chunks():
    sections = [section("A", "\n\n".join(paragraph(p) for p in range(5))), section("B", "Short.")]
    assert chunk_sections("T", sections) == chunk_sections("T", sections)


def test_random_lessons_respect_the_invariants():
    rng = random.Random(20260929)  # noqa: S311 - test data from a fixed seed, not cryptography
    vocabulary = "light water leaf root energy sugar cell carbon oxygen stem soil".split()
    for _ in range(40):
        sections = []
        for s in range(rng.randint(1, 5)):
            paragraphs = []
            for _ in range(rng.randint(1, 8)):
                sentences = [
                    " ".join(rng.choice(vocabulary) for _ in range(rng.randint(3, 40))).capitalize() + "."
                    for _ in range(rng.randint(1, 15))
                ]
                paragraphs.append(" ".join(sentences))
            sections.append(section(f"Section {s}", "\n\n".join(paragraphs)))
        chunks = chunk_sections("Random", sections)
        assert [c.position for c in chunks] == list(range(len(chunks)))
        assert all(0 < c.token_count <= MAX_TOKENS for c in chunks)
        for sec in sections:  # every paragraph appears somewhere, unchanged, when it fits in one chunk
            for para in sec["blocks"][0]["text"].split("\n\n"):
                if count_tokens(para) <= MAX_TOKENS:
                    assert any(para in c.text for c in chunks if c.heading == sec["heading"])
