import os
import json
import boto3
import logging
from typing import Any, Dict, List, Optional, Protocol
import time  # added for retry backoff


# =============================================================================
# Configuration
# =============================================================================
DEFAULT_EMBEDDING_MODEL = os.getenv("DEFAULT_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
DEFAULT_LLM_MODEL = os.getenv("DEFAULT_LLM_MODEL", "anthropic.claude-3-sonnet-20240229-v1:0")
DEFAULT_RERANK_MODEL = os.getenv("DEFAULT_RERANK_MODEL", "cohere.rerank-v1")
BEDROCK_REGION_DEFAULT = os.getenv("BEDROCK_REGION", "us-east-1")

# Cost configuration (replace with real pricing as needed)
MODEL_COSTS: Dict[str, Dict[str, float]] = {
    "amazon.titan-embed-text-v2:0": {"per_1k_tokens_in": 0.0001},
    "anthropic.claude-3-sonnet-20240229-v1:0": {
        "per_1k_tokens_in": 0.0030,
        "per_1k_tokens_out": 0.0150,
    },
    "cohere.rerank-v1": {"per_document": 0.0001},
}

# Allow JSON override via env (silently ignore errors)
_override = os.getenv("MODEL_COSTS_JSON")
if _override:
    try:
        MODEL_COSTS.update(json.loads(_override))
    except Exception:
        pass


def calculate_cost(model_id: str, usage: Dict[str, int]) -> float:
    """
    Compute approximate cost based on MODEL_COSTS and usage.
    Supported usage keys: tokens_in, tokens_out, chars, documents.
    """
    cfg = MODEL_COSTS.get(model_id, {})
    cost = 0.0
    if "tokens_in" in usage and "per_1k_tokens_in" in cfg:
        cost += (usage["tokens_in"] / 1000.0) * cfg["per_1k_tokens_in"]
    if "tokens_out" in usage and "per_1k_tokens_out" in cfg:
        cost += (usage["tokens_out"] / 1000.0) * cfg["per_1k_tokens_out"]
    if "chars" in usage and "per_1k_chars" in cfg:
        cost += (usage["chars"] / 1000.0) * cfg["per_1k_chars"]
    if "documents" in usage and "per_document" in cfg:
        cost += usage["documents"] * cfg["per_document"]
    return round(cost, 8)


# =============================================================================
# Exceptions
# =============================================================================
class ProviderError(Exception):
    """Base exception for all provider errors."""


class EmbeddingError(ProviderError):
    """Raised when embedding fails."""


class GenerationError(ProviderError):
    """Raised when generation fails."""


class RerankError(ProviderError):
    """Raised when rerank fails."""


# =============================================================================
# Provider Interface
# =============================================================================
class Provider(Protocol):
    """All providers must implement these methods."""

    def embed(self, text: str, **kwargs) -> tuple[List[float], Dict[str, Any]]: ...

    def generate(
        self, prompt: str, max_tokens: int = 512, temperature: float = 0.7, **kwargs
    ) -> tuple[str, Dict[str, Any]]: ...

    def rerank(
        self, query: str, documents: List[str], top_n: Optional[int] = None, **kwargs
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]: ...


# =============================================================================
# Bedrock Provider
# =============================================================================
class BedrockProvider:
    """AWS Bedrock implementation for embeddings, LLM generation, and reranking."""

    def __init__(
        self,
        region: str = BEDROCK_REGION_DEFAULT,
        embedding_model: Optional[str] = None,
        llm_model: Optional[str] = None,
        rerank_model: Optional[str] = None,
        logger: Optional[logging.Logger] = None,
        token_counter=None,              # added: custom token counter hook
        max_retries: int = 2,            # added
        backoff_base: float = 0.5,       # added
    ):
        self.region = region
        self._client = None  # lazy init
        self.embedding_model = embedding_model or DEFAULT_EMBEDDING_MODEL
        self.llm_model = llm_model or DEFAULT_LLM_MODEL
        self.rerank_model = rerank_model or DEFAULT_RERANK_MODEL
        self._logger = logger or logging.getLogger(__name__)
        self._token_counter = token_counter or (lambda s: len(s.split()))
        self._max_retries = max_retries
        self._backoff_base = backoff_base

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    def _log(self, level: int, msg: str, **extra):
        """Helper for safe logging (never raises)."""
        if not self._logger:
            return
        try:
            self._logger.log(level, msg, extra=extra or None)
        except Exception:
            pass

    def _ensure_client(self):
        if self._client is None:
            self._client = boto3.client("bedrock-runtime", region_name=self.region)
        return self._client

    def _tokens(self, text: str) -> int:
        try:
            return self._token_counter(text)
        except Exception:
            return len(text.split())

    def _invoke_model(self, *, model_id: str, payload: Dict[str, Any], op: str) -> Dict[str, Any]:
        """Unified invoke with simple retry/backoff."""
        for attempt in range(self._max_retries + 1):
            try:
                resp = self._ensure_client().invoke_model(
                    modelId=model_id,
                    body=json.dumps(payload),
                    accept="application/json",
                    contentType="application/json",
                )
                return json.loads(resp["body"].read())
            except Exception as e:
                if attempt >= self._max_retries:
                    self._log(logging.ERROR, f"{op} invoke failed", model=model_id, error=str(e), attempt=attempt)
                    raise
                delay = self._backoff_base * (2 ** attempt)
                time.sleep(delay)

    # -------------------------------------------------------------------------
    # Embeddings
    # -------------------------------------------------------------------------
    def embed(
        self, text: str, model_id: Optional[str] = None, max_length: int = 8000
    ) -> tuple[List[float], Dict[str, Any]]:
        if not isinstance(text, str) or not text.strip():
            raise EmbeddingError("Text must be a non-empty string")

        model_id = model_id or self.embedding_model
        payload = {"inputText": text[:max_length]}
        try:
            body = self._invoke_model(model_id=model_id, payload=payload, op="embed")
            embedding = body.get("embedding")
            if not embedding:
                raise EmbeddingError(f"No embedding returned from {model_id}")

            usage = {
                "tokens_in": self._tokens(text),
                "tokens_out": 0,
                "chars": len(text),
            }
            meta = {"model": model_id, "usage": usage, "cost": calculate_cost(model_id, usage)}
            return embedding, meta
        except ProviderError:
            raise
        except Exception as e:
            self._log(logging.ERROR, "Embedding failed", model=model_id, error=str(e))
            raise EmbeddingError(f"Embedding failed (model={model_id}): {e}") from e

    # -------------------------------------------------------------------------
    # LLM Generation
    # -------------------------------------------------------------------------
    def generate(
        self,
        prompt: str,
        model_id: Optional[str] = None,
        max_tokens: int = 512,
        temperature: float = 0.7,
        **params: Any,
    ) -> tuple[str, Dict[str, Any]]:
        if not isinstance(prompt, str) or not prompt.strip():
            raise GenerationError("Prompt must be a non-empty string")

        model_id = model_id or self.llm_model
        if "anthropic" in model_id:
            payload = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": max_tokens,
                "temperature": temperature,
                "messages": [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
                **params,
            }
        else:
            payload = {"inputText": prompt, "maxTokens": max_tokens, "temperature": temperature, **params}

        try:
            body = self._invoke_model(model_id=model_id, payload=payload, op="generate")

            # Normalize output
            if "outputText" in body:
                output = body["outputText"]
            elif "completion" in body:
                output = body["completion"]
            elif "content" in body and isinstance(body["content"], list):
                output = "\n".join(c.get("text", "") for c in body["content"] if isinstance(c, dict))
            elif "results" in body and isinstance(body["results"], list):
                output = "".join(r.get("outputText", "") for r in body["results"] if isinstance(r, dict))
            elif "output" in body and isinstance(body["output"], dict) and "text" in body["output"]:
                output = body["output"]["text"]
            else:
                raise GenerationError(f"Unrecognized response format: {body}")

            usage = {
                "tokens_in": self._tokens(prompt),
                "tokens_out": self._tokens(str(output)),
                "chars": len(prompt) + len(str(output)),
            }
            meta = {"model": model_id, "usage": usage, "cost": calculate_cost(model_id, usage)}
            return output, meta
        except ProviderError:
            raise
        except Exception as e:
            self._log(logging.ERROR, "Generation failed", model=model_id, error=str(e))
            raise GenerationError(f"Generation failed (model={model_id}): {e}") from e

    # -------------------------------------------------------------------------
    # Rerank
    # -------------------------------------------------------------------------
    def rerank(
        self,
        query: str,
        documents: List[str],
        model_id: Optional[str] = None,
        top_n: Optional[int] = None,
        **params: Any,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        if not isinstance(query, str) or not query.strip():
            raise RerankError("Query must be a non-empty string")
        if not documents:
            return [], {
                "model": model_id or self.rerank_model,
                "usage": {"tokens_in": 0, "documents": 0},
                "cost": 0.0,
            }

        model_id = model_id or self.rerank_model
        payload = {"query": query, "documents": documents, **params}
        if top_n:
            payload["top_n"] = min(top_n, len(documents))

        try:
            body = self._invoke_model(model_id=model_id, payload=payload, op="rerank")
        except Exception as e:
            self._log(logging.ERROR, "Rerank failed", model=model_id, error=str(e))
            raise RerankError(f"Rerank failed (model={model_id}): {e}") from e

        results = body.get("results") or body.get("reranked_documents") or []
        ranked: List[Dict[str, Any]] = []

        for item in results:
            if not isinstance(item, dict):
                continue
            idx = item.get("index") or item.get("id")
            if isinstance(idx, int) and 0 <= idx < len(documents):
                ranked.append({
                    "index": idx,
                    "document": documents[idx],
                    "score": float(item.get("relevance_score") or item.get("score") or 0.0),
                    "original_score": float(item.get("original_score", 0.0)),
                })

        # Fallback if no ranking provided
        if not ranked:
            ranked = [
                {"index": i, "document": d, "score": 0.0, "original_score": 0.0, "fallback": True}
                for i, d in enumerate(documents)
            ]

        ranked.sort(key=lambda r: r["score"], reverse=True)
        trimmed = ranked[:top_n] if top_n else ranked

        usage = {
            "tokens_in": self._tokens(query) + sum(self._tokens(d) for d in documents),
            "tokens_out": 0,
            "documents": len(documents),
            "chars": len(query) + sum(len(d) for d in documents),
        }
        meta = {"model": model_id, "usage": usage, "cost": calculate_cost(model_id, usage)}
        return trimmed, meta


# =============================================================================
# Model Loader
# =============================================================================
class ModelLoader:
    """
    Manages providers with a unified API. Each method returns (result, meta).
    First provider registered (with select=None) is auto-selected.
    Call use(name) only when you have multiple providers and want to switch.
    """

    def __init__(self):
        self._providers: Dict[str, Provider] = {}
        self._current: Optional[str] = None

    # -- Registration & selection --
    def register(self, name: str, provider: Provider, select: Optional[bool] = None):
        """
        Register a provider.
        select:
          None (default): auto-select ONLY if no provider is currently active.
          True: force select this provider.
          False: do not select (leave current unchanged).
        """
        self._providers[name] = provider
        if select is True or (select is None and self._current is None):
            self._current = name
        return self  # chaining

    def use(self, name: str):
        """Switch active provider. Only needed if multiple providers are registered."""
        if name not in self._providers:
            raise ValueError(f"Provider '{name}' not registered")
        self._current = name

    def current(self) -> Provider:
        if not self._current:
            raise RuntimeError("No provider selected. Call use('<provider_name>') first.")
        return self._providers[self._current]

    # -- Delegated operations --
    def embed(self, *args, **kwargs):
        return self.current().embed(*args, **kwargs)

    def generate(self, *args, **kwargs):
        return self.current().generate(*args, **kwargs)

    def rerank(self, *args, **kwargs):
        return self.current().rerank(*args, **kwargs)

    def generate_json(self, prompt: str, **kwargs) -> Dict[str, Any]:
        """Generate expecting JSON; returns parsed dict (meta discarded)."""
        text, _meta = self.generate(prompt, **kwargs)
        if isinstance(text, dict):
            return text
        if not isinstance(text, str):
            raise ValueError("Model output not string or dict; cannot parse JSON")

        try:
            return json.loads(text)
        except Exception:
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1 and end > start:
                fragment = text[start:end + 1]
                try:
                    return json.loads(fragment)
                except Exception:
                    pass
        raise ValueError("Failed to parse model output as JSON")


# =============================================================================
# Example Usage
# =============================================================================
if __name__ == "__main__":
    from utils.split import split_into_chunks

    print("=== Example (concise) ===")
    try:
        provider = BedrockProvider(region="us-east-1")
        loader = ModelLoader().register("bedrock", provider)  # auto-selected
        emb, emb_meta = loader.embed("Example embedding text")
        print("Embedding dims:", len(emb), "| cost:", emb_meta.get("cost"))

        gen_txt, gen_meta = loader.generate("Write one short sentence about loaders.", max_tokens=32)
        print("Generation:", gen_txt[:80], "| cost:", gen_meta.get("cost"))

        docs = ["Doc about AWS.", "Another text on loaders.", "Irrelevant line."]
        reranked, rerank_meta = loader.rerank("loaders", docs)
        print("Top rerank idx:", reranked[0]["index"] if reranked else None, "| cost:", rerank_meta.get("cost"))

        chunks = split_into_chunks("Short text to chunk for demo", chunk_size=3)
        print("Chunks:", chunks)
    except Exception as e:
        print("Example error:", e)

    print("=== End Example ===")
