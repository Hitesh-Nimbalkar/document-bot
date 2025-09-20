# response_formatter.py
"""
Formats final RAG response with metadata + enhancement features.
"""

# ======================================================
# Imports
# ======================================================
from typing import Any, Dict, List
from utils.logger import CustomLogger

# Logger
logger = CustomLogger(__name__)


# ======================================================
# Response Formatter
# ======================================================
class ResponseFormatter:
    """Formats the final RAG response with enhanced metadata and feature tracking"""

    # --------------------------------------------------
    # Initialization
    # --------------------------------------------------
    def __init__(self):
        logger.info("📋 ResponseFormatter initialized")

    # --------------------------------------------------
    # Format Response
    # --------------------------------------------------
    def format_response(
        self,
        answer: Any,
        results: List[Dict],
        query: str,
        rewritten_query: str,
        intent: str,
        context_info: dict,
        enhancement_features: dict,
        metadata_filters_applied: str,
    ) -> dict:
        """Format the pipeline output into a structured response"""
        sources = []
        for r in results:
            metadata = r.get("metadata", {})
            text_val = metadata.get("text", "")

            preview = text_val[:200] + "..." if len(text_val) > 200 else text_val

            sources.append({
                "doc_id": metadata.get("doc_id"),
                "document_name": metadata.get("filename", "Unknown"),
                "document_type": metadata.get("file_type", ""),
                "score": r.get("score", 0.0),
                "adjusted_score": r.get("adjusted_score"),
                "created_at": metadata.get("created_at"),
                "user_id": metadata.get("user_id"),
                "preview": preview,
            })

        return {
            "answer": answer,
            "sources": sources,
            "query": query,
            "rewritten_query": rewritten_query,
            "intent": intent,
            "context_info": context_info,
            "num_sources": len(sources),
            "metadata_filters_applied": metadata_filters_applied,
            "enhancement_features": enhancement_features,
        }
