# AI service (planned)

A separate FastAPI service that Django calls. It owns *how* to answer; Django owns *whether* the student may ask.

## Responsibilities

| Capability | Design |
|---|---|
| **Tutor** | Modes: *Explain* (answer from the lesson, one example), *Socratic* (never state the final answer; ask one guiding question), *Hint* (one small step; never reveals the correct option). After 2–3 failed Socratic turns, move to a hint, then a worked example |
| **Grounding (RAG)** | Always include the current lesson; retrieve related chunks from the rest of the course by meaning (pgvector, HNSW). Only **published** versions are indexed. Every answer returns the sections it used |
| **Off-topic and safety** | Low retrieval similarity → polite redirect to the lesson. Every student message and every model reply passes a safety check; high-severity flags go to Operations under the written escalation procedure |
| **Short-answer marking** | Marks against the teacher's rubric; returns marks, feedback and confidence; low confidence → teacher review |
| **Author assist** | Lesson outline, question variants, reading-level check. Output is always saved as an **AI draft** that needs human review |
| **Weekly parent summary** | Wording only; every fact comes from the learner record |
| **LLM gateway** | One place to call models: provider switch, routing (cheaper models for simple tasks), timeouts, retries, token and cost logging |
| **Prompt registry** | Prompts are versioned files; every response records `model` and `prompt_version` |
| **Evals** | Golden question sets per lesson; run on every prompt or model change; track groundedness, "didn't give away the answer", safety, latency, cost |

## Privacy boundary

The service receives a pseudonymous `learner_ref`, class, lesson and course IDs, recent turns, weak skills and interests.
It **never** receives names, contacts, payments or parent data.

## Storage (schema `ai`)

| Table | Contents |
|---|---|
| `lesson_chunk` | lesson_id, content_version_id, course_id, section heading, text, position, embedding (vector) |
| `prompt_version` | name, version, body, active flag |
| `eval_run` | suite, prompt version, model, pass rate, results |

## Budgets

| Item | Default |
|---|---|
| Tutor timeout | 30 s (streamed); first token target < 3 s |
| Grading timeout | 15 s |
| Daily messages per student | 50 (admin setting) |
| Failure behaviour | "The tutor is unavailable right now"; the student's message is never lost |

## Open decision

The model provider (chat + embeddings) is chosen by the product owner. The gateway keeps the rest of the design
provider-independent.
