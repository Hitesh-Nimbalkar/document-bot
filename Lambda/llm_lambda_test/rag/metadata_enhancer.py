


"""metadata_enhancer.py
Unified metadata filtering + re-ranking utilities.
Contains:
  - MetadataFilterEngine
  - MetadataAwareReranker
(Logic copied verbatim from former metadata_filter.py and metadata_reranker.py)
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List
from utils.metadata import MetadataManager
from .models import (
    FiltersInput,
    FiltersOutput,
    RerankInput,
    RerankOutput,
)
import re
from utils.logger import CustomLogger
from src.data_analysis import DocumentAnalyzer
logger = CustomLogger(__name__)
class MetadataFilterEngine:
    """MetadataFilterEngine
    Purpose:
        Builds structured metadata filter objects used by the retriever layer.
        Converts user query text + conversational context + payload (e.g. user_id)
        into three buckets of filters:
            must   -> strict constraints (documents MUST satisfy all)
            should -> soft preference signals (boost scoring if matched)
            not    -> exclusion constraints
    """
    DOC_TYPE_KEYWORDS = {
        "policy": ["policy", "policies", "guideline", "rule"],
        "manual": ["manual", "guide", "instruction", "handbook"],
        "report": ["report", "analysis", "summary", "findings"],
        "specification": ["spec", "specification", "requirement"],
        "procedure": ["procedure", "process", "workflow", "sop", "step"],
    }
    NEGATION_TOKENS = {"not", "except", "without", "exclude"}
    RECENCY_PATTERNS = {
        "recent": 30,
        "latest": 30,
        "last 7 days": 7,
        "last week": 7,
        "last 30 days": 30,
        "last month": 30,
        "last quarter": 90,
    }
    QUARTER_REGEX = re.compile(r"\bq([1-4])[\s\-]*(20\d{2})\b", re.I)
    def __init__(self, project_name: str):
        self.project_name = project_name
        self.metadata_manager = MetadataManager()
        logger.info("🔍 MetadataFilterEngine initialized (refactored logic)")
    def build_metadata_filters(
        self,
        query: str,
        context_info: dict,
        event: dict = None,
        payload: dict = None
    ) -> Dict[str, List[dict]]:
        filters = {"must": [], "should": [], "not": []}
        ql = query.lower()
        # --- Always constrain to project ---
        if self.project_name:
            filters["must"].append(
                {"key": "project_name", "match": {"value": self.project_name}}
            )
        # --- Personalization ---
        if payload and payload.get("user_id"):
            filters["should"].append(
                {"key": "user_id", "match": {"value": payload["user_id"]}}
            )
        # --- Temporal: relative recency ---
        for phrase, days in self.RECENCY_PATTERNS.items():
            if phrase in ql:
                since = datetime.now() - timedelta(days=days)
                filters["should"].append(
                    {"key": "created_at", "range": {"gte": since.isoformat()}}
                )
                break
        # --- Temporal: absolute quarters (Q1 2024, Q2-2023) ---
        m = self.QUARTER_REGEX.search(ql)
        if m:
            qnum = int(m.group(1))
            year = int(m.group(2))
            start_month = (qnum - 1) * 3 + 1
            start = datetime(year, start_month, 1)
            end = datetime(year, start_month + 3, 1) - timedelta(seconds=1)
            filters["must"].append(
                {
                    "key": "created_at",
                    "range": {"gte": start.isoformat(), "lte": end.isoformat()},
                }
            )
        # --- Document types (with negatives) ---
        tokens = ql.split()
        for dtype, keywords in self.DOC_TYPE_KEYWORDS.items():
            if any(k in ql for k in keywords):
                # check if negation word appears in query
                if any(neg in tokens for neg in self.NEGATION_TOKENS):
                    filters["not"].append(
                        {"key": "file_type", "match": {"value": dtype}}
                    )
                else:
                    filters["should"].append(
                        {"key": "file_type", "match": {"value": dtype}}
                    )
        # --- Topics from conversation context ---
        if context_info.get("recent_topics"):
            for topic in context_info["recent_topics"]:
                filters["should"].append(
                    {"key": "content_tags", "match": {"value": topic}}
                )
        # --- Deduplicate each bucket ---
        for bucket in filters:
            seen, unique = set(), []
            for f in filters[bucket]:
                key = (f["key"], str(f.get("match")), str(f.get("range")))
                if key not in seen:
                    unique.append(f)
                    seen.add(key)
            filters[bucket] = unique
        return filters
    def build_metadata_filters_io(self, data: FiltersInput) -> FiltersOutput:
        fdict = self.build_metadata_filters(
            query=data.query,
            context_info=data.context_info,
            payload=data.payload,
        )
        # Ensure FiltersOutput has must/should/not
        return FiltersOutput(
            must=fdict.get("must", []),
            should=fdict.get("should", []),
            not_=fdict.get("not", []),
        )
class MetadataAwareReranker:
    """Enhanced re-ranking that considers both relevance and metadata factors"""
    def __init__(self, model_loader=None):
        self.analyzer = DocumentAnalyzer(loader=model_loader)
        self.current_user_id: str | None = None  # can be injected at runtime
        logger.info("📊 MetadataAwareReranker initialized (improved logic)")
    def rerank_basic(self, query: str, results: List[Dict], top_k: int = 5,
                     event: dict = None, payload: dict = None) -> List[Dict]:
        if len(results) <= top_k:
            return results
        # Build compact prompt for LLM
        chunks_text = ""
        for i, result in enumerate(results):
            chunk_text = result.get("metadata", {}).get("text", "")[:200] + "..."
            chunks_text += f"Chunk {i+1}: {chunk_text}\n"
        rerank_prompt = f"""
        Rank these document chunks by relevance to the query: "{query}"
        {chunks_text}
        Return the ranking as a comma-separated list of chunk numbers (e.g., "3,1,5,2,4"):
        """
        response = self.analyzer.analyze_document(rerank_prompt)
        ranking_text = response.get("summary", "") if isinstance(response, dict) else str(response)
        ranking = [int(x.strip()) - 1 for x in ranking_text.strip().split(",") if x.strip().isdigit()]
        reranked_results = []
        for rank in ranking:
            if 0 <= rank < len(results):
                reranked_results.append(results[rank])
        # add any unranked items until top_k
        for i, result in enumerate(results):
            if i not in ranking and len(reranked_results) < top_k:
                reranked_results.append(result)
        return reranked_results[:top_k]
    def rerank_with_metadata(self, query: str, results: List[Dict], context_info: dict,
                             top_k: int = 5) -> RerankOutput:
        # Step 1: LLM-based reranking
        llm_reranked = self.rerank_basic(query, results, top_k * 2)
        enriched: List[Dict[str, Any]] = []
        now = datetime.now()
        for result in llm_reranked:
            metadata = result.get("metadata", {})
            base_score = float(result.get("score", 0.5))
            # --- Recency boost ---
            created_at = metadata.get("created_at")
            if created_at:
                try:
                    doc_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    age_days = (now - doc_time).days
                    if age_days < 7:
                        base_score += 0.25
                    elif age_days < 30:
                        base_score += 0.15
                    elif age_days < 90:
                        base_score += 0.1
                except Exception:
                    pass
            # --- File type / topic alignment ---
            file_type = metadata.get("file_type", "").lower()
            if file_type and context_info.get("recent_topics"):
                if any(file_type in t.lower() for t in context_info["recent_topics"]):
                    base_score += 0.2
            # --- Personalization boost ---
            if self.current_user_id and metadata.get("user_id") == self.current_user_id:
                base_score += 0.1
            # --- Source credibility ---
            ingest_source = metadata.get("ingest_source", "").lower()
            if ingest_source in {"upload", "api"}:
                base_score += 0.05
            # Normalize score between 0–1
            adjusted = min(max(base_score, 0.0), 1.0)
            result["adjusted_score"] = adjusted
            enriched.append(result)
        # Sort by adjusted_score, fallback to original score
        enriched.sort(key=lambda x: x.get("adjusted_score") or x.get("score") or 0, reverse=True)
        trimmed = enriched[:top_k]
        return RerankOutput(query=query, top_k=top_k, results=trimmed)
    def rerank_with_metadata_io(self, data: RerankInput) -> RerankOutput:
        return self.rerank_with_metadata(
            query=data.query,
            results=data.results,
            context_info=data.context_info,
            top_k=data.top_k,
        )

