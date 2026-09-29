"""OllamaProvider against a fake Ollama (httpx.MockTransport): no real model or network needed."""

import asyncio
import json

import httpx
import pytest

from tutor_ai.providers import Message, ProviderError, ProviderTimeout, ProviderUnavailable
from tutor_ai.providers.ollama import MAX_EMBED_BATCH, OllamaProvider


def run(coro):
    return asyncio.run(coro)


def provider(handler, **kwargs):
    defaults = {
        "base_url": "http://ollama.test/",
        "chat_model": "llama3.2",
        "embedding_model": "nomic-embed-text",
        "dimensions": 4,
    }
    defaults.update(kwargs)
    return OllamaProvider(transport=httpx.MockTransport(handler), **defaults)


def ndjson(*events):
    return "\n".join(json.dumps(e) for e in events).encode()


async def chat_text(p, messages=None):
    messages = messages or [Message("user", "hi")]
    try:
        return "".join([part async for part in p.chat(messages, max_tokens=50, temperature=0.3)])
    finally:
        await p.aclose()


def test_chat_streams_fragments_and_sends_the_right_request():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            content=ndjson(
                {"message": {"content": "Hel"}, "done": False},
                {"message": {"content": "lo"}, "done": False},
                {"message": {"content": ""}, "done": True},
            ),
        )

    assert run(chat_text(provider(handler))) == "Hello"
    assert seen["path"] == "/api/chat"
    body = seen["body"]
    assert body["model"] == "llama3.2" and body["stream"] is True
    assert body["keep_alive"] == "30m"
    assert body["options"] == {"num_predict": 50, "temperature": 0.3}
    assert body["messages"] == [{"role": "user", "content": "hi"}]


def test_chat_error_event_becomes_provider_error():
    p = provider(lambda r: httpx.Response(200, content=ndjson({"error": "model not found"})))
    with pytest.raises(ProviderError, match="model not found"):
        run(chat_text(p))


def test_chat_http_error_status():
    with pytest.raises(ProviderError, match="500"):
        run(chat_text(provider(lambda r: httpx.Response(500, text="boom"))))


def test_chat_malformed_stream():
    with pytest.raises(ProviderError):
        run(chat_text(provider(lambda r: httpx.Response(200, content=b"not json\n"))))


def test_unreachable_ollama_is_provider_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderUnavailable, match="ollama serve"):
        run(chat_text(provider(handler)))


def test_timeout_is_provider_timeout():
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    with pytest.raises(ProviderTimeout):
        run(chat_text(provider(handler)))


def embed_handler(seen, dims=4):
    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"embeddings": [[0.5] * dims for _ in body["input"]]})

    return handler


def test_embed_uses_nomic_prefixes_and_batches():
    seen = []
    p = provider(embed_handler(seen))
    texts = [f"text {i}" for i in range(MAX_EMBED_BATCH + 3)]
    vectors = run(p.embed(texts, kind="document"))
    run(p.aclose())
    assert len(vectors) == len(texts)
    assert [len(b["input"]) for b in seen] == [MAX_EMBED_BATCH, 3]
    assert seen[0]["input"][0] == "search_document: text 0"
    seen.clear()
    p = provider(embed_handler(seen))
    run(p.embed(["q"], kind="query"))
    assert seen[0]["input"] == ["search_query: q"]


def test_other_embedding_models_get_no_prefix():
    seen = []
    run(provider(embed_handler(seen), embedding_model="mxbai-embed-large").embed(["q"], kind="query"))
    assert seen[0]["input"] == ["q"]


def test_wrong_dimensions_or_count_are_errors():
    with pytest.raises(ProviderError, match="dimensions"):
        run(provider(embed_handler([], dims=3)).embed(["a"], kind="document"))

    def short(request):
        return httpx.Response(200, json={"embeddings": []})

    with pytest.raises(ProviderError, match="number"):
        run(provider(short).embed(["a"], kind="document"))
    with pytest.raises(ProviderError):
        run(provider(lambda r: httpx.Response(404)).embed(["a"], kind="document"))

    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ProviderUnavailable):
        run(provider(refused).embed(["a"], kind="document"))


@pytest.mark.parametrize(
    ("installed", "healthy"),
    [
        (["llama3.2:latest", "nomic-embed-text:latest"], True),
        (["llama3.2:latest"], False),
        (["llama3.2:3b", "nomic-embed-text:latest"], False),  # untagged name means :latest
        ([], False),
    ],
)
def test_health_checks_both_models_are_pulled(installed, healthy):
    def handler(request):
        return httpx.Response(200, json={"models": [{"name": n} for n in installed]})

    assert run(provider(handler).health()) is healthy


def test_health_false_when_unreachable_or_broken():
    def refused(request):
        raise httpx.ConnectError("refused", request=request)

    assert run(provider(refused).health()) is False
    assert run(provider(lambda r: httpx.Response(500)).health()) is False
    assert run(provider(lambda r: httpx.Response(200, text="not json")).health()) is False


def test_explicitly_tagged_model_must_match_exactly():
    def handler(request):
        return httpx.Response(200, json={"models": [{"name": "llama3.1:8b"}, {"name": "nomic-embed-text:latest"}]})

    assert run(provider(handler, chat_model="llama3.1:8b").health()) is True
