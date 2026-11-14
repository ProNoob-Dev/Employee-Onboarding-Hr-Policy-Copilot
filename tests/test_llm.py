import pytest

from app.llm import AzureError, AzureOpenAIClient, LocalAnswerer

def test_local_answerer_is_deterministic(copilot):
    scored = copilot.retriever.retrieve("How many days of annual leave do I get?", k=3)
    answerer = LocalAnswerer()
    first = answerer.answer("How many days of annual leave do I get?", scored)
    second = answerer.answer("How many days of annual leave do I get?", scored)
    assert first == second
    assert "24 days of annual leave" in first[0]  # quotes clause text only


def test_azure_stub_transport_success(monkeypatch, copilot):
    import httpx

    captured = {}

    def handler(request):
        captured["json"] = request.content
        return httpx.Response(200, json={"choices": [{"message": {"content": "stub answer"}}]})

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    client = AzureOpenAIClient(transport=httpx.MockTransport(handler))
    scored = copilot.retriever.retrieve("annual leave", k=1)
    text, confidence = client.answer("annual leave?", scored)
    assert text == "stub answer"
    assert 0.0 <= confidence <= 1.0
    # Instructions go in a system message, the question in a user message.
    import json

    messages = json.loads(captured["json"])["messages"]
    assert messages[0]["role"] == "system"
    assert "Clauses:" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "annual leave?"}


def test_azure_response_is_pii_masked(monkeypatch, copilot):
    import httpx

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {
            "content": "Contact jane@example.com or call 9876543210."}}]})

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    client = AzureOpenAIClient(transport=httpx.MockTransport(handler))
    scored = copilot.retriever.retrieve("annual leave", k=1)
    text, _ = client.answer("annual leave?", scored)
    assert text == "Contact [EMAIL] or call [PHONE]."


def test_azure_rejects_non_azure_endpoint(monkeypatch, copilot):
    import httpx

    def handler(request):
        return httpx.Response(200, json={"choices": [{"message": {"content": "x"}}]})

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://evil.example.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    client = AzureOpenAIClient(transport=httpx.MockTransport(handler))
    scored = copilot.retriever.retrieve("annual leave", k=1)
    with pytest.raises(AzureError):
        client.answer("annual leave?", scored)


def test_azure_error_hides_endpoint_url(monkeypatch, copilot):
    import httpx

    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    client = AzureOpenAIClient(transport=httpx.MockTransport(handler))
    scored = copilot.retriever.retrieve("annual leave", k=1)
    with pytest.raises(AzureError) as excinfo:
        client.answer("annual leave?", scored)
    assert "example.openai.azure.com" not in str(excinfo.value)


def test_azure_failure_raises(monkeypatch, copilot):
    import httpx

    def handler(request):
        return httpx.Response(500, json={"error": "boom"})

    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "fake")
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com/")
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")
    client = AzureOpenAIClient(transport=httpx.MockTransport(handler))
    scored = copilot.retriever.retrieve("annual leave", k=1)
    with pytest.raises(AzureError):
        client.answer("annual leave?", scored)
