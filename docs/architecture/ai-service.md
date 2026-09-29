# AI service (planned, milestone 5)

A separate FastAPI service that Django calls. It owns *how* to answer; Django owns *whether* the student may ask.
Decisions: D23, D27, D30, D31.

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
| `lesson_chunk` | lesson_id, content_version_id, course_id, section heading, text, position, embedding (vector), **embedding_model** (e.g. `nomic-embed-text`, 768 dimensions). Changing the embedding model means re-indexing, so the model is stored with every vector |
| `prompt_version` | name, version, body, active flag |
| `eval_run` | suite, prompt version, model, pass rate, results |

## Model providers (D27, D30)

Every model call goes through one interface (`chat`, `embed`). The provider is chosen by `TUTOR_AI_PROVIDER`:

| Provider | Where | Chat model | Embeddings | Notes |
|---|---|---|---|---|
| `ollama` | Developer machines | `TUTOR_OLLAMA_CHAT_MODEL`, default **`llama3.2`** (3B); `llama3.1:8b` on machines with an NVIDIA GPU | `nomic-embed-text` (768-dim) | Real AI, free, private. For building and debugging only, **not** for judging tutor quality |
| `mock` | CI, automated tests, hosted demo | Scripted replies from fixtures | Deterministic fake vectors | No network, no key; tests never depend on a running model |
| `hosted` | Production (provider chosen before real users) | Decided with evals | Decided with evals | Tutor quality is measured here, against the eval suites |

If the configured provider is unreachable (e.g. Ollama not running), AI endpoints answer `503` with a clear message
("The tutor is unavailable right now"); nothing crashes and the student's message is kept.

## Measured local performance (2026-09-29)

Reference machine: 16 GB RAM laptop, Intel Iris Xe integrated graphics (Ollama uses the **CPU**; it doesn't use Intel
integrated GPUs), Ollama 0.23.2 inside WSL.

| Model | Prompt reading | Writing | Model load | Realistic tutor prompt (1,286 tokens) |
|---|---|---|---|---|
| `llama3.2` (3B) | ~26–29 tokens/s | ~10–14 tokens/s (≈ 8–10 words/s) | 10–16 s | **50 s** to read the prompt, then 9 s to write 90 tokens: **≈ 60 s to the first word** (model already loaded) |
| `llama3.1:8b` | ~9 tokens/s | ~6.5 tokens/s | 9 s | ≈ 2.5 minutes to the first word (estimated from the rates) |

On CPU, **reading the prompt is the bottleneck**, not writing the answer. A machine with an NVIDIA GPU is many times
faster; hosted providers are faster still. The design below keeps the tutor usable on the slowest machine and cheap
on hosted providers.

## Prompt layout: fixed prefix, pinned lesson context (D31)

The prompt is built in this order, so that everything before the student's new message is **identical on every turn
of a chat**:

```
1. Tutor rules and safety instructions      fixed text, versioned in the prompt registry
2. Lesson context for this chat             chosen once when the chat starts, then pinned
3. Conversation so far                       grows by one turn each message
4. The student's new message                 the only new text each turn
```

- **Pinned lesson context.** When a student opens the tutor on a lesson, the service retrieves the passages for that
  lesson once and keeps them fixed for the whole chat. Re-retrieving on every message would change the middle of the
  prompt and force the model to read everything again. New passages are fetched only when a question clearly goes
  beyond the lesson (low similarity to the pinned passages); that turn pays the full reading cost once.
- **Why it matters:** Ollama reuses its work on an unchanged prompt prefix while the model stays loaded, so after the
  first message only the new text is read. Hosted providers offer the same effect as prompt caching, usually at a
  lower price for the cached part.
- **Size limits per provider** (settings, not code): tight locally (rules ≈ 300 tokens, lesson context ≈ 600,
  history ≈ last 6 turns, summarised beyond that); larger for the hosted provider.
- **Keep the model loaded** between messages (Ollama `keep_alive`), so the 10–16 s load happens once per session.
- **Stream** the reply (SSE, D17) so the student sees words as they are written.

## Budgets

These are production targets. Local (`ollama`) timeouts are configurable and much longer, because CPU machines are
slow; see the measurements above.

| Item | Default |
|---|---|
| Tutor timeout | 30 s (streamed); first token target < 3 s |
| Grading timeout | 15 s |
| Daily messages per student | 50 (admin setting) |
| Failure behaviour | "The tutor is unavailable right now"; the student's message is never lost |

## Open decision

The **production** model provider (chat + embeddings) is chosen by the product owner before real users, using the
eval suites. Development uses Ollama (D23, D30); the gateway keeps everything else provider-independent.
