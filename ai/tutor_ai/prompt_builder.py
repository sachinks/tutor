"""Assemble the messages for one tutor turn (design §6, D31).

Layout, in this order:
1. system: rules + mode instructions (+ quiz guard) + the pinned lesson context  — identical on every turn of a chat
   as long as the mode doesn't change, so Ollama reuses its work and hosted providers can cache it
2. the conversation so far: the last `history_turns` turns, oldest dropped first to stay within `history_tokens`
3. the student's new message

Passages are labelled [P1], [P2], … in pinned order; the labels map back to chunk ids for citations. While a quiz is
open the mode is always "hint" (design §6 quiz guard), whatever the student chose.

Pure functions: no I/O, same input → same output.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from .chunking import count_tokens
from .prompts import PromptVersion
from .providers.base import Message
from .retrieval import Passage

Mode = Literal["explain", "socratic", "hint"]
Role = Literal["student", "tutor"]

WORDS_PER_TOKEN = 0.75  # rough English average; only used to tell the model a word limit


@dataclass(frozen=True)
class Turn:
    role: Role
    text: str


@dataclass(frozen=True)
class PromptLimits:
    context_tokens: int
    history_turns: int
    history_tokens: int
    reply_tokens: int


@dataclass(frozen=True)
class BuiltPrompt:
    messages: list[Message]
    prompt_ref: str
    mode: Mode  # the mode actually used (hint while a quiz is open)
    passage_ids: dict[str, uuid.UUID]  # "P1" -> chunk id
    history_used: int  # turns included
    history_dropped: int  # turns left out to respect the limits
    estimated_tokens: int


def student_label(class_number: int | None) -> str:
    return f"a Class {class_number} student" if class_number else "a school student"


def format_passages(passages: Sequence[Passage], budget_tokens: int) -> tuple[str, dict[str, uuid.UUID]]:
    """Label passages in order, stopping before the context budget is exceeded."""
    blocks: list[str] = []
    labels: dict[str, uuid.UUID] = {}
    used = 0
    for passage in passages:
        if used + passage.token_count > budget_tokens:
            break
        label = f"P{len(labels) + 1}"
        heading = f" {passage.heading}" if passage.heading else ""
        blocks.append(f"[{label}]{heading}\n{passage.text}")
        labels[label] = passage.chunk_id
        used += passage.token_count
    return "\n\n".join(blocks), labels


def select_history(history: Sequence[Turn], max_turns: int, max_tokens: int) -> list[Turn]:
    """The most recent turns within both limits, in their original order."""
    chosen: list[Turn] = []
    used = 0
    for turn in reversed(history[-max_turns:] if max_turns else []):
        tokens = count_tokens(turn.text)
        if used + tokens > max_tokens:
            break
        chosen.insert(0, turn)
        used += tokens
    return chosen


def build_prompt(
    prompt: PromptVersion,
    *,
    mode: Mode,
    class_number: int | None,
    lesson_title: str,
    passages: Sequence[Passage],
    history: Sequence[Turn],
    message: str,
    limits: PromptLimits,
    open_quiz: bool = False,
) -> BuiltPrompt:
    effective: Mode = "hint" if open_quiz else mode
    passages_text, labels = format_passages(passages, limits.context_tokens)
    parts = [
        prompt.render(
            "system",
            student=student_label(class_number),
            reply_words=str(max(10, int(limits.reply_tokens * WORDS_PER_TOKEN))),
        ),
        prompt.render(effective),
    ]
    if open_quiz:
        parts.append(prompt.render("quiz_guard"))
    parts.append(
        prompt.render("context", lesson_title=lesson_title, passages=passages_text or "(no passages available)")
    )
    system = "\n\n".join(parts)

    turns = select_history(history, limits.history_turns, limits.history_tokens)
    messages = [Message("system", system)]
    messages += [Message("user" if t.role == "student" else "assistant", t.text) for t in turns]
    messages.append(Message("user", message))
    return BuiltPrompt(
        messages=messages,
        prompt_ref=prompt.ref,
        mode=effective,
        passage_ids=labels,
        history_used=len(turns),
        history_dropped=len(history) - len(turns),
        estimated_tokens=sum(count_tokens(m.content) for m in messages),
    )
