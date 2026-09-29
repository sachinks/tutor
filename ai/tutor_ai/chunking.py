"""Split a published lesson into passages for retrieval (design §5).

Rules:
- One chunk per lesson section when it fits in MAX_TOKENS.
- Longer sections are split on paragraph boundaries; a paragraph that is itself too long is split on sentences, and
  a sentence that is still too long (rare: tables pasted as one line) on words.
- Consecutive chunks of the same section overlap by up to OVERLAP_TOKENS (whole paragraphs or sentences, never
  half a sentence), so an idea that straddles a boundary is still found.
- Chunk text is the published text, unchanged, so the tutor can quote it verbatim. Images contribute their alt text
  as "[Image: …]"; blocks without text are skipped.
- `embed_text` (what is embedded) adds the lesson title and section heading in front of the text, which makes
  short passages much easier to retrieve; it is never shown to students.

Token counts are an estimate (words plus punctuation marks). The limits exist for retrieval precision, not because
of a model limit (nomic-embed-text accepts far longer inputs), so an estimate that is off by 20% is harmless and
keeps the chunker independent of any one model's tokenizer.

Pure functions, no I/O: the same lesson always gives the same chunks.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

MAX_TOKENS = 300
OVERLAP_TOKENS = 40

_TOKEN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
_PARAGRAPH = re.compile(r"\n\s*\n")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Chunk:
    position: int  # 0-based order within the lesson
    heading: str
    text: str
    token_count: int
    embed_text: str


@dataclass(frozen=True)
class _Unit:
    """A piece that fits in a chunk: a whole paragraph, a sentence, or a run of words."""

    text: str
    tokens: int
    paragraph: int  # units from the same paragraph are joined with a space, others with a blank line


def count_tokens(text: str) -> int:
    return len(_TOKEN.findall(text))


def block_text(block: Mapping[str, Any]) -> str:
    """The student-visible text of one content block ('' when it has none)."""
    if block.get("type") == "image":
        alt = str(block.get("alt") or "").strip()
        return f"[Image: {alt}]" if alt else ""
    return str(block.get("text") or "").strip()


def _split_words(text: str, limit: int) -> list[str]:
    words = text.split()
    pieces: list[str] = []
    current: list[str] = []
    for word in words:
        if current and count_tokens(" ".join([*current, word])) > limit:
            pieces.append(" ".join(current))
            current = []
        current.append(word)
    if current:
        pieces.append(" ".join(current))
    return pieces


def _units(section_text: str) -> list[_Unit]:
    units: list[_Unit] = []
    paragraphs = [p.strip() for p in _PARAGRAPH.split(section_text) if p.strip()]
    for index, paragraph in enumerate(paragraphs):
        tokens = count_tokens(paragraph)
        if tokens <= MAX_TOKENS:
            units.append(_Unit(paragraph, tokens, index))
            continue
        for sentence in (s.strip() for s in _SENTENCE.split(paragraph) if s.strip()):
            sentence_tokens = count_tokens(sentence)
            if sentence_tokens <= MAX_TOKENS:
                units.append(_Unit(sentence, sentence_tokens, index))
            else:
                units.extend(_Unit(piece, count_tokens(piece), index) for piece in _split_words(sentence, MAX_TOKENS))
    return units


def _join(units: Sequence[_Unit]) -> str:
    parts: list[str] = []
    for i, unit in enumerate(units):
        if i:
            parts.append(" " if unit.paragraph == units[i - 1].paragraph else "\n\n")
        parts.append(unit.text)
    return "".join(parts)


def _overlap(units: Sequence[_Unit]) -> list[_Unit]:
    """The longest tail of `units` (whole units, or else closing sentences of the last one) that fits in
    OVERLAP_TOKENS. Possibly empty."""
    tail: list[_Unit] = []
    total = 0
    for unit in reversed(units):
        if total + unit.tokens > OVERLAP_TOKENS:
            break
        tail.insert(0, unit)
        total += unit.tokens
    if tail or not units:
        return tail
    # The last unit is a whole paragraph longer than the overlap: carry its closing sentences instead.
    last = units[-1]
    sentences = [s.strip() for s in _SENTENCE.split(last.text) if s.strip()]
    for sentence in reversed(sentences[1:]):  # never the whole paragraph again
        tokens = count_tokens(sentence)
        if total + tokens > OVERLAP_TOKENS:
            break
        tail.insert(0, _Unit(sentence, tokens, last.paragraph))
        total += tokens
    return tail


def _pack(units: Sequence[_Unit]) -> list[list[_Unit]]:
    groups: list[list[_Unit]] = []
    current: list[_Unit] = []
    total = 0
    for unit in units:
        if current and total + unit.tokens > MAX_TOKENS:
            groups.append(current)
            current = _overlap(current)
            total = sum(u.tokens for u in current)
            if total + unit.tokens > MAX_TOKENS:  # overlap and the next unit don't fit together: drop the overlap
                current, total = [], 0
        current.append(unit)
        total += unit.tokens
    if current:  # always holds at least the last unit, which no earlier chunk contains
        groups.append(current)
    return groups


def chunk_sections(title: str, sections: Iterable[Mapping[str, Any]]) -> list[Chunk]:
    chunks: list[Chunk] = []
    for section in sections:
        heading = str(section.get("heading") or "").strip()
        blocks = section.get("blocks") or []
        text = "\n\n".join(t for t in (block_text(b) for b in blocks if isinstance(b, Mapping)) if t)
        if not text:
            continue
        for group in _pack(_units(text)):
            body = _join(group)
            chunks.append(
                Chunk(
                    position=len(chunks),
                    heading=heading,
                    text=body,
                    token_count=count_tokens(body),
                    embed_text=f"{title} — {heading}\n\n{body}" if heading else f"{title}\n\n{body}",
                )
            )
    return chunks
