"""LLM client: deterministic local answerer (default) + env-gated Azure."""

from __future__ import annotations

import httpx
from urllib.parse import urlparse

from . import config
from .pii import mask_pii
from .retrieval import ScoredClause


class AzureError(RuntimeError):
    """Azure call failed. The API turns this into a 502, never a silent fallback."""


class LocalAnswerer:
    """Extractive template answerer over retrieved clauses only."""

    def answer(self, question: str, clauses: list[ScoredClause]) -> tuple[str, float]:
        parts = [
            f"According to {scored.clause.title} ({scored.clause.doc_id}, "
            f"clause {scored.clause.clause_id}): {scored.clause.text}"
            for scored in clauses
        ]
        confidence = round(min(max(clauses[0].score, 0.0), 1.0), 3) if clauses else 0.0
        return " ".join(parts), confidence


class AzureOpenAIClient:
    """Minimal Azure OpenAI chat client. Only used when the key is set."""

    def __init__(self, transport: httpx.BaseTransport | None = None) -> None:
        self._transport = transport

    def answer(self, question: str, clauses: list[ScoredClause]) -> tuple[str, float]:
        endpoint = config.azure_endpoint()
        parsed = urlparse(endpoint)
        if (parsed.scheme != "https" or not parsed.hostname
                or not parsed.hostname.endswith(".openai.azure.com")):
            raise AzureError(
                "AZURE_OPENAI_ENDPOINT must be an https:// URL on *.openai.azure.com")
        context = "\n".join(
            f"- {s.clause.title} ({s.clause.doc_id}, clause {s.clause.clause_id}): {s.clause.text}"
            for s in clauses
        )
        url = (
            f"{endpoint.rstrip('/')}/openai/deployments/"
            f"{config.azure_deployment()}/chat/completions?api-version=2024-02-01"
        )
        try:
            with httpx.Client(transport=self._transport, timeout=30) as client:
                resp = client.post(
                    url,
                    headers={"api-key": config.azure_api_key()},
                    json={"messages": [
                        {"role": "system",
                         "content": "Answer the employee question using ONLY the policy "
                                    "clauses below. Cite each clause as (doc_id, clause_id).\n\n"
                                    f"Clauses:\n{context}"},
                        {"role": "user", "content": mask_pii(question)},
                    ], "temperature": 0},
                )
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001 - any Azure failure is a loud 502
            # Never echo the endpoint URL (it can appear in the httpx error)
            # or any other request detail into the error.
            raise AzureError(f"Azure OpenAI call failed: {type(exc).__name__}") from exc
        confidence = round(min(max(clauses[0].score, 0.0), 1.0), 3) if clauses else 0.0
        return mask_pii(text), confidence


def get_answerer():
    return AzureOpenAIClient() if config.llm_provider() == "azure" else LocalAnswerer()
