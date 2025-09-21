

# rag_pipeline.py
"""
Enhanced RAG Pipeline - Modular Architecture
Pipeline Stages:
1. Query Processing
2. Metadata Filter Building
3. Document Retrieval
4. Re-ranking with Metadata
5. Context Building
6. LLM Answer Generation
7. Response Formatting
8. Logging & Finalization
Features:
- Metadata filtering
- Chat history integration
- Smart re-ranking
- Graceful error handling
"""
from typing import Any, Dict, List, Optional
from src.data_analysis import DocumentAnalyzer
from prompt.prompt_library import PROMPT_MODEL_REGISTRY
from utils.logger import CustomLogger
from utils.model_loader import ModelLoader
from chat_history.chat_history import (
    log_chat_history,
    ChatHistory,
    log_model_chat_message,
)
# Import QueryProcessor with fallbacks
try:
    from .query_processor import QueryProcessor
except ImportError:
    try:
        from query_processor import QueryProcessor
    except ImportError:
        QueryProcessor = None  # will raise in __init__
from .metadata_enhancer import MetadataFilterEngine, MetadataAwareReranker
from .enhanced_retriever import EnhancedRetriever
from .context_builder import SmartContextBuilder
from .response_formatter import ResponseFormatter
logger = CustomLogger(__name__)

# ======================================================
# Master RAG Pipeline Orchestrator
# ======================================================
class RAGPipeline:
    """Master RAG Pipeline Orchestrator"""
    def __init__(self, project_name: str, model_loader: Optional[ModelLoader] = None , llm_model_id : str = None):
        """Initialize all pipeline components"""
        if QueryProcessor is None:
            raise ImportError(
                "QueryProcessor could not be imported. "
                "Ensure rag/query_processor.py is available and import paths are correct."
            )
        self.project_name = project_name
        self.model_loader = model_loader
        # Core pipeline components
        self.query_processor = QueryProcessor(model_loader=model_loader ,llm_model_id = llm_model_id )
        self.filter_engine = MetadataFilterEngine(project_name)
        self.retriever = EnhancedRetriever()
        self.reranker = MetadataAwareReranker(model_loader=model_loader)
        self.context_builder = SmartContextBuilder()
        self.formatter = ResponseFormatter()
        self.analyzer = DocumentAnalyzer(loader=model_loader)
        # Chat history manager
        self.chat_history_manager = ChatHistory()
        self.current_user_id: Optional[str] = None
        # Holds last generation metadata
        self._last_model_meta: Optional[Dict[str, Any]] = None
        logger.info(
            f"🚀 Enhanced RAG Pipeline initialized for project '{project_name}' "
            f"with {len([x for x in [self.query_processor, self.filter_engine, self.retriever, self.reranker, self.context_builder, self.formatter, self.analyzer] if x])} components"
        )
    # ==================================================
    # Main Execution
    # ==================================================
    def run(
        self,
        query: str,
        top_k: int = 5,
        chat_history: Optional[List[Dict]] = None,
        event: Optional[dict] = None,
        payload: Optional[dict] = None,
        enable_reranking: bool = True,
    ) -> dict:
        """Run the complete enhanced RAG pipeline"""
        try:
            # ----------------------------
            # Basic validation
            # ----------------------------
            if not query or not query.strip():
                return self._handle_pipeline_error(
                    query or "",
                    "Empty query provided",
                    event,
                    payload,
                )
            logger.info(f"\n🚀 Starting Enhanced RAG Pipeline\n🔎 Query: {query[:100]}...")
            # ----------------------------
            # User context
            # ----------------------------
            if payload and payload.get("user_id"):
                self.current_user_id = payload["user_id"]
                if hasattr(self.reranker, "current_user_id"):
                    self.reranker.current_user_id = payload["user_id"]
            # Initial chat logging
            if event and payload:
                try:
                    log_chat_history(
                        event=event,
                        payload=payload,
                        role="user",
                        content=query,
                        metadata={"action": "rag_query_start"},
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to log initial query: {e}")
            # ==================================================
            # Stage 1: Query Processing
            # ==================================================
            logger.info("🔤 Stage 1: Query Processing")
            qp_result = self.query_processor.process(query, chat_history=chat_history)
            rewritten_query = qp_result.get("rewritten_query", query)
            intent = qp_result.get("intent", "rag_query")
            query_embedding = qp_result.get("embedding")
            context_info = qp_result.get("context_info", {})
            logger.info(
                f"   ✏️ Rewritten Query: {rewritten_query}\n"
                f"   🎯 Intent: {intent}\n"
                f"   📋 Context: {context_info.get('query_type')} "
                f"with {context_info.get('message_count')} history messages"
            )
            # ==================================================
            # Stage 2: Metadata Filters
            # ==================================================
            logger.info("🔍 Stage 2: Building Metadata Filters")
            metadata_filters = self.filter_engine.build_metadata_filters(
                rewritten_query, context_info, event, payload
            )
            must_count = len(metadata_filters.get("must", []))
            should_count = len(metadata_filters.get("should", []))
            not_count = len(metadata_filters.get("not", []))
            filter_summary = (
                f"{must_count} must, {should_count} should, {not_count} not"
                if not_count
                else f"{must_count} must, {should_count} should"
            )
            logger.info(f"📊 Filters Applied: {filter_summary}")
            context_info.setdefault(
                "metadata_filter_buckets",
                {"must": must_count, "should": should_count, "not": not_count},
            )
            # ==================================================
            # Stage 3: Retrieval
            # ==================================================
            logger.info("📚 Stage 3: Enhanced Retrieval")
            initial_top_k = top_k * 4 if enable_reranking else top_k
            results = self.retriever.retrieve_with_metadata(
                query_embedding, metadata_filters, initial_top_k
            )
            if not results:
                logger.warning("❌ No relevant documents found after retrieval")
                return self._handle_no_results(
                    query,
                    rewritten_query,
                    intent,
                    context_info,
                    event,
                    payload,
                    filter_summary,
                )
            logger.info(f"📄 Retrieved {len(results)} document chunks")
            # ==================================================
            # Stage 4: Re-ranking
            # ==================================================
            if enable_reranking and len(results) > top_k:
                logger.info("📊 Stage 4: Smart Re-ranking")
                rerank_output = self.reranker.rerank_with_metadata(
                    rewritten_query, results, context_info, top_k
                )
                results = rerank_output.results
                logger.info(f"✨ Re-ranked to top {len(results)} results")
            else:
                results = results[:top_k]
            # ==================================================
            # Stage 5: Context Building
            # ==================================================
            logger.info("📝 Stage 5: Building Enhanced Context")
            context_text = self.context_builder.build_enhanced_context(
                results, rewritten_query, chat_history, context_info
            )
            # ==================================================
            # Stage 6: Answer Generation
            # ==================================================
            logger.info(f"🧠 Stage 6: Answer Generation (intent: {intent})")
            try:
                prompt_text = self._build_prompt(intent, context_text, rewritten_query)
                
                # Extract generation parameters from payload if available
                generation_params = {}
                if payload:
                    if "temperature" in payload:
                        generation_params["temperature"] = float(payload["temperature"])
                    if "max_tokens" in payload:
                        generation_params["max_tokens"] = int(payload["max_tokens"])
                    if "top_p" in payload:
                        generation_params["top_p"] = float(payload["top_p"])
                
                answer = self._generate_answer(prompt_text, **generation_params)  # sets self._last_model_meta
                model_meta = self._last_model_meta
                logger.info("✅ Answer generated successfully")
            except Exception as e:
                logger.error(f"💥 Answer generation failed: {e}")
                model_meta = None
                answer = {
                    "summary": (
                        "Sorry, I encountered an error generating the answer. "
                        "Here’s the relevant context I found:"
                    ),
                    "context": (
                        context_text[:1000] + "..."
                        if len(context_text) > 1000
                        else context_text
                    ),
                    "error": str(e),
                }
            # ==================================================
            # Stage 7: Response Formatting
            # ==================================================
            logger.info("📋 Stage 7: Formatting Response")
            enhancement_features = {
                "metadata_filtering": True,
                "smart_chat_history": bool(chat_history),
                "enhanced_context": True,
                "metadata_scoring": enable_reranking,
                "negation_filters": bool(metadata_filters.get("not")),
            }
            response = self.formatter.format_response(
                answer=answer,
                results=results,
                query=query,
                rewritten_query=rewritten_query,
                intent=intent,
                context_info=context_info,
                enhancement_features=enhancement_features,
                metadata_filters_applied=filter_summary,
            )
            # Final chat logging
            if event and payload:
                try:
                    answer_summary = (
                        answer.get("summary", str(answer)[:200])
                        if isinstance(answer, dict)
                        else str(answer)[:200]
                    )
                    if model_meta:
                        enriched_meta = dict(model_meta)
                        enriched_meta.setdefault("action", "rag_query_complete")
                        enriched_meta.setdefault("intent", intent)
                        enriched_meta.setdefault("sources_count", len(results))
                        enriched_meta.setdefault("enhanced_features", True)
                        log_model_chat_message(
                            event=event,
                            payload=payload,
                            content=answer_summary,
                            model_meta=enriched_meta,
                        )
                    else:
                        log_chat_history(
                            event=event,
                            payload=payload,
                            role="assistant",
                            content=answer_summary,
                            metadata={
                                "action": "rag_query_complete",
                                "sources_count": len(results),
                                "intent": intent,
                                "enhanced_features": True,
                            },
                        )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to log completion: {e}")
            logger.info(
                f"\n🎉 Enhanced RAG Pipeline completed successfully with {len(results)} sources\n"
            )
            return response
        except Exception as e:
            logger.error(f"💥 Pipeline execution failed: {e}")
            return self._handle_pipeline_error(query, str(e), event, payload)
    # ==================================================
    # Error / No-Results Handling
    # ==================================================
    def _handle_no_results(
        self,
        query: str,
        rewritten_query: str,
        intent: str,
        context_info: dict,
        event: dict,
        payload: dict,
        filter_summary: str,
    ) -> dict:
        """Handle case when no results are found"""
        response = {
            "answer": {
                "summary": (
                    "No relevant documents found. Try rephrasing or "
                    "check if documents are available in your project."
                )
            },
            "sources": [],
            "query": query,
            "rewritten_query": rewritten_query,
            "intent": intent,
            "context_info": context_info,
            "enhancement_features": {"no_results": True},
        }
        if event and payload:
            try:
                log_chat_history(
                    event=event,
                    payload=payload,
                    role="assistant",
                    content="No relevant documents found for your query.",
                    metadata={"action": "rag_no_results", "filters_applied": filter_summary},
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to log no-results event: {e}")
        return response
    def _handle_pipeline_error(
        self,
        query: str,
        error: str,
        event: dict,
        payload: dict,
    ) -> dict:
        """Handle pipeline errors gracefully"""
        if event and payload:
            try:
                log_chat_history(
                    event=event,
                    payload=payload,
                    role="system",
                    content=f"Enhanced RAG pipeline error: {error}",
                    metadata={
                        "action": "rag_error",
                        "error": error,
                        "enhanced_pipeline": True,
                    },
                )
            except Exception as log_e:
                logger.warning(f"⚠️ Failed to log error event: {log_e}")
        return {
            "answer": {"summary": f"I encountered an error processing your query: {error}"},
            "sources": [],
            "query": query,
            "error": error,
            "pipeline_version": "enhanced_modular",
        }
    # ==================================================
    # Chat History Helper
    # ==================================================
    def get_enhanced_chat_history(
        self, session_id: str, limit: int = 10
    ) -> List[Dict]:
        """Retrieve formatted chat history for pipeline integration"""
        try:
            history_data = self.chat_history_manager.get_recent_history(session_id, limit)
            return history_data.get("messages", [])
        except Exception as e:
            logger.error(f"💥 Failed to retrieve chat history: {e}")
            return []
    # ==================================================
    # Prompt / Answer Helpers
    # ==================================================
    def _build_prompt(self, intent: str, context_text: str, rewritten_query: str) -> str:
        """Resolve prompt template for intent with fallback and format it."""
        registry_entry = PROMPT_MODEL_REGISTRY.get(intent)
        if not registry_entry:
            fallback_entry = PROMPT_MODEL_REGISTRY.get("rag_query") or next(
                iter(PROMPT_MODEL_REGISTRY.values())
            )
            prompt_template = fallback_entry["prompt"]
        else:
            prompt_template = registry_entry["prompt"]
        return prompt_template.format(context=context_text, query=rewritten_query)
    def _generate_answer(self, prompt_text: str, **generation_params) -> Dict[str, Any]:
        """Generate answer using model_loader if available; fallback to analyzer.
        Sets self._last_model_meta.
        
        Args:
            prompt_text: The prompt to send to the LLM
            **generation_params: Additional parameters like max_tokens, temperature, etc.
        """
        self._last_model_meta = None
        if self.model_loader:
            try:
                # Default parameters with user overrides
                default_params = {
                    "max_tokens": 900,
                    "temperature": 0.7
                }
                default_params.update(generation_params)
                
                logger.info(f"🧠 Generating answer with params: {default_params}")
                llm_raw, meta = self.model_loader.generate(prompt_text, **default_params)
                self._last_model_meta = meta
                return {"summary": llm_raw}
            except Exception as e:
                logger.warning(f"⚠️ ModelLoader generation failed ({e}); using fallback analyzer")
        # Fallback path
        return self.analyzer.analyze_document(prompt_text)

