

# ---------------------------------------------------------------------------
# Query Processing Pipeline
# ---------------------------------------------------------------------------
# Steps:
#   1. Rewrite (optional LLM via ModelLoader)
#   2. Intent classification (keyword heuristics)
#   3. Embedding generation (history-aware prefix)
#   4. Context analysis (recent topics + session info)
# ---------------------------------------------------------------------------
# Standard Library
from __future__ import annotations
import os
import re
import time
from enum import Enum
from typing import Any, Dict, List, Optional
# Third Party
from pydantic import BaseModel, Field, validator
# Local Imports
from utils.embeddings import get_embeddings
from utils.logger import CustomLogger  # assumed path
try:  # optional for __main__ example
    from chat_history.chat_history import ChatHistory
except ImportError:
    ChatHistory = None  # type: ignore
logger = CustomLogger(__name__)
# ---------------------------------------------------------------------------
# Type Aliases
# ---------------------------------------------------------------------------
ChatMessage = Dict[str, Any]
# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class QueryIntent(str, Enum):
    SUMMARIZATION = "summarization"
    COMPARISON = "comparison"
    ANALYSIS = "analysis"
    RAG_QUERY = "rag_query"

class QueryType(str, Enum):
    """Enumeration of query types based on context."""
    FOLLOWUP = "followup"

# ---------------------------------------------------------------------------
# Configuration (kept in-file per user request)
# ---------------------------------------------------------------------------
INTENT_KEYWORDS = {
    QueryIntent.SUMMARIZATION: ["summarize", "summary", "overview", "key points", "tl;dr"],
    QueryIntent.ANALYSIS: ["analyze", "analysis", "insights", "trends", "interpret"],
}
INTENT_DEFAULT = QueryIntent.RAG_QUERY
REWRITE_PREFIX_PATTERNS = [
    r"^updated query:\s*",
]
HISTORY_LIMIT = 5  # Number of recent messages to consider for context
MAX_REWRITTEN_LENGTH = 200
# ---------------------------------------------------------------------------
# Pydantic Request / Response Models
# ---------------------------------------------------------------------------
class QueryRequest(BaseModel):
    """Input model for query processing."""
    event: Optional[Dict[str, Any]] = Field(None, description="Event context information")
    @validator("event", pre=True, always=True)
    def validate_query(cls, v: str) -> str:
        if not v or not str(v).strip():
            raise ValueError("Query cannot be empty or only whitespace")
        return v

class QueryRewriteResponse(BaseModel):
    original_query: str
    rewrite_successful: bool
    error_message: Optional[str] = None

class IntentClassificationResponse(BaseModel):
    query: str
    confidence: float = Field(0.0, ge=0.0, le=1.0)

class EmbeddingResponse(BaseModel):
    query: str
    embedding: List[float]
    model_used: str = "bedrock"

class SessionContext(BaseModel):
    last_query_time: Optional[str] = None
    has_context: bool
    message_count: int = 0
    query_type: QueryType
    user_preferences: Dict[str, Any] = Field(default_factory=dict)

# ---------------------------------------------------------------------------
# Query Processor
# ---------------------------------------------------------------------------
class QueryProcessor:
    """Lightweight query preprocessing pipeline.
    Steps:
      1. Rewrite (optional LLM via ModelLoader) - never raises.
      2. Intent classification (fast, deterministic).
      3. Embedding generation (may raise on backend failure).
      4. Context analysis (heuristic).
      5. process(): orchestrates above.
    """
    def __init__(self, model_loader: "ModelLoader" | None = None, llm_model_id: str = None):
        self.model_loader = model_loader
        self.llm_model_id = llm_model_id
        logger.info(
            "QueryProcessor initialized" + (" with ModelLoader" if self.model_loader else "")
        )
    # ------------------------------------------------------------------
    def rewrite_query(
        self,
        query: str,
        chat_history: Optional[List[ChatMessage]] = None,
        event: dict = None,
        payload: dict = None,
    ) -> str:
        """Produce a retrieval-friendly variant of the user query.
        No fallbacks - fails fast if model_loader doesn't work.
        """
        start = time.time()
        base = query or ""
        
        logger.info(f"Rewriting query: {base[:80]} ...")
        # Concatenate last 2 user messages as lightweight context
        history_section = ""
        if chat_history:
            recent_user_msgs = [m["content"] for m in chat_history if m.get("role") == "user"]
            if recent_user_msgs:
                condensed_prior = " | ".join(recent_user_msgs[-2:])
                history_section = f"UserContext: {condensed_prior[:200]}\n"
        rewrite_prompt = (
            "Rewrite this user query to be more effective for document retrieval. "
            "Focus on key terms and concepts, remove conversational words. "
            "Make it concise and keyword-focused for semantic search.\n\n"
            + history_section
            + f"User query: {base}\n\n"
            + "Rewritten query (keywords only):"
        )
        # Only use model_loader - no fallbacks
        if not self.model_loader:
            raise ValueError("model_loader is required for query rewriting")
        
        # Use model_loader with the provided LLM model ID
        gen = self.model_loader.generate(
            rewrite_prompt, 
            max_tokens=80,
            model_id=self.llm_model_id
        )
        # Handle tuple return (text, metadata)
        if isinstance(gen, tuple):
            rewritten_raw = gen[0].strip()
        else:
            rewritten_raw = gen.strip()
        rewritten = rewritten_raw.strip()
        # Cleanup markdown fences
        rewritten = re.sub(r"^```[a-zA-Z0-9]*", "", rewritten)
        lowered = rewritten.lower()
        # If instructions echoed, grab last meaningful line
        if "original query:" in lowered and len(rewritten.splitlines()) > 1:
            candidate_lines = [
                l for l in rewritten.splitlines()
                if l.strip() and not l.lower().startswith("original query:")
            ]
            if candidate_lines:
                rewritten = candidate_lines[-1]
        if len(rewritten) > MAX_REWRITTEN_LENGTH:
            rewritten = rewritten[:MAX_REWRITTEN_LENGTH].rstrip()
        # Minimal validity check
        if not rewritten or rewritten.count(" ") <= 1:
            logger.info("Rewriter produced too short output; falling back to original query")
            rewritten = base
        logger.info(
            f"Rewrite complete in {round((time.time()-start)*1000)} ms: {rewritten[:100]}"
        )
        return rewritten
    # ------------------------------------------------------------------
    def classify_intent(
        self, query: str, event: dict = None, payload: dict = None
    ) -> QueryIntent:
        """Heuristic keyword-based intent classification (fast, deterministic)."""
        try:
            text = (query or "").lower()
            for intent, keywords in INTENT_KEYWORDS.items():
                if any(k in text for k in keywords):
                    return intent
            return INTENT_DEFAULT
        except Exception as e:  # pragma: no cover
            logger.warning(f"Intent classification failed: {e}; defaulting to {INTENT_DEFAULT.value}")
            return INTENT_DEFAULT
    # ------------------------------------------------------------------
    def embed_query(
        self,
        query: str,
        chat_history: Optional[List[ChatMessage]] = None,
    ) -> List[float]:
        """Generate an embedding for the (possibly rewritten) query.
        May raise if the backend fails.
        """
        try:
            embed_input = query
            if chat_history:
                recent_user_msgs = [m.get("content") for m in chat_history if m.get("role") == "user"]
                if recent_user_msgs:
                    snippet = " | ".join(recent_user_msgs[-2:])
                    embed_input = (snippet + " || " + query)[:1000]
            # Only use model_loader - no fallbacks
            if not self.model_loader:
                raise ValueError("model_loader is required for query processing")
            
            # Use model_loader.embed with explicit model_id to ensure consistency
            embedding_result = self.model_loader.embed(embed_input, model_id="amazon.titan-embed-text-v2:0")
            # Handle tuple return (embedding, metadata)
            if isinstance(embedding_result, tuple):
                embedding = embedding_result[0]
            else:
                embedding = embedding_result
            if not embedding:
                raise ValueError("Empty embedding generated")
            logger.info(f"Generated embedding dim={len(embedding)}")
            return embedding
        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise
    # ------------------------------------------------------------------
    def analyze_query_context(
        self,
        query: str,
        chat_history: Optional[List[ChatMessage]] = None,
        payload: dict = None,
    ) -> dict:
        """Derive lightweight conversational context and recent topics.
        Current heuristic only scans last HISTORY_LIMIT messages for coarse topic terms.
        """
        history = chat_history or []
        context_info: Dict[str, Any] = {
            "has_context": bool(history),
            "user_preferences": {},
            "recent_topics": [],
        }
        if not history:
            return context_info
        recent_messages = history[-HISTORY_LIMIT:]
        topic_terms = {
            "manual": ["manual", "guide"],
            "report": ["report", "analysis"],
        }
        recent_topics: List[str] = []
        for msg in recent_messages:
            content = (msg.get("content") or "").lower()
            for topic, terms in topic_terms.items():
                if any(term in content for term in terms):
                    recent_topics.append(topic)
        context_info["recent_topics"] = list(set(recent_topics))
        context_info["session_context"] = {
            "last_query_time": recent_messages[-1].get("timestamp") if recent_messages else None,
        }
        return context_info
    # ------------------------------------------------------------------
    def process(
        self,
        query: str,
        chat_history: Optional[List[ChatMessage]] = None,
    ) -> Dict[str, Any]:
        """Full pipeline execution:
        - Rewrite query
        - Classify intent
        - Generate embeddings
        - Analyze context
        """
        start = time.time()
        try:
            rewritten = self.rewrite_query(query, chat_history=chat_history)
            intent = self.classify_intent(rewritten)
            embedding = self.embed_query(rewritten, chat_history=chat_history)
            context_info = self.analyze_query_context(rewritten, chat_history=chat_history)
            return {
                "original_query": query,
                "rewritten_query": rewritten,
                "intent": intent.value,
                "embedding": embedding,
                "embedding_dim": len(embedding),
                "context": context_info,  # alias for backward compatibility
                "success": True,
                "error_details": None,
                "processing_time_ms": round((time.time() - start) * 1000),
            }
        except Exception as e:
            logger.error(f"Process pipeline failed: {e}")
            return {
                "original_query": query,
                "rewritten_query": query,
                "intent": QueryIntent.RAG_QUERY.value,
                "embedding": [],
                "embedding_dim": 0,
                "context": {},
                "success": False,
                "error_details": {"message": str(e)},
                "processing_time_ms": round((time.time() - start) * 1000),
            }

# ---------------------------------------------------------------------------
# Standalone Usage Example
# ---------------------------------------------------------------------------
if __name__ == "__main__":  # pragma: no cover
    qp = QueryProcessor()
    user_query = "Summarize the new policy changes"
    history_messages: List[ChatMessage] = []
    try:
        if ChatHistory:
            stored = ChatHistory().get_recent_history(session_id="demo", limit=HISTORY_LIMIT)
            history_messages = [
                {"role": m.get("role"), "content": m.get("content"), "timestamp": m.get("timestamp")}
                for m in stored.get("messages", [])
            ]
    except Exception:
        pass
    if not history_messages:
        history_messages = [
            {
                "role": "user",
                "content": "Summarize the new policy changes",
                "timestamp": "2025-09-18T10:00:00Z",
            },
            {
                "role": "assistant",
                "content": "They add escalation tiers and reporting rules.",
                "timestamp": "2025-09-18T10:00:05Z",
            },
        ]
    result = qp.process(user_query, history_messages)
    print("Recent topics:", result["context"].get("recent_topics"))

