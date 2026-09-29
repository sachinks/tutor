"""Deterministic provider for tests, CI and the hosted demo: no network, no key, instant (design §4).

Embeddings are *hashed bag-of-words* vectors: each word is hashed to a position (and a sign) in the vector, and the
result is normalised to unit length. Texts that share words therefore get similar vectors, so retrieval, off-topic
detection and citations behave realistically without a model. The same text always gives the same vector.

Chat is rule-based: it finds the context sentence that shares the most words with the student's message, quotes it,
and asks a guiding question. Replies are clearly marked as demo replies.
"""

import hashlib
import math
import re
from collections.abc import AsyncIterator

from .base import EmbeddingKind, Message

_WORD = re.compile(r"[^\W_]+", re.UNICODE)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
STOPWORDS = frozenset(
    "a an and are as at be by for from has have how i in is it its of on or that the this to was what when where which "
    "who why will with you your do does did can".split()
)
DEMO_PREFIX = "(Demo tutor) "


def tokens(text: str) -> list[str]:
    return [w for w in (m.group(0).lower() for m in _WORD.finditer(text)) if w not in STOPWORDS and len(w) > 1]


def hashed_embedding(text: str, dimensions: int) -> list[float]:
    vector = [0.0] * dimensions
    for word in tokens(text):
        digest = hashlib.blake2b(word.encode(), digest_size=8).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:  # no content words: a fixed unit vector keeps the maths well-defined
        vector[0] = 1.0
        return vector
    return [v / norm for v in vector]


def best_sentence(question: str, context: str) -> str | None:
    wanted = set(tokens(question))
    best, best_score = None, 0
    for sentence in (s.strip() for s in _SENTENCE.split(context) if s.strip()):
        score = len(wanted & set(tokens(sentence)))
        if score > best_score:
            best, best_score = sentence, score
    return best


class MockProvider:
    name = "mock"
    chat_model = "mock-tutor-v1"
    embedding_model = "mock-hashed-bow-v1"

    def __init__(self, dimensions: int = 768) -> None:
        self.dimensions = dimensions

    async def chat(self, messages: list[Message], *, max_tokens: int, temperature: float) -> AsyncIterator[str]:
        question = next((m.content for m in reversed(messages) if m.role == "user"), "")
        context = "\n".join(m.content for m in messages if m.role == "system")
        found = best_sentence(question, context)
        if found:
            reply = f'{DEMO_PREFIX}The lesson says: "{found}" What do you think that means for your question?'
        else:
            reply = f"{DEMO_PREFIX}That isn't covered in this lesson. Shall we go back to what the lesson is about?"
        words = reply.split(" ")
        for i, word in enumerate(words[: max(max_tokens, 1)]):
            yield word if i == 0 else " " + word

    async def embed(self, texts: list[str], *, kind: EmbeddingKind) -> list[list[float]]:
        return [hashed_embedding(t, self.dimensions) for t in texts]

    async def health(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None
