# rag/rag_pipeline.py
from src.data_analysis import DocumentAnalyzer
from vector_db.vector_db import QdrantVectorDB
from prompt.prompt_library import PROMPT_MODEL_REGISTRY, QueryIntent, RewrittenQuery


class RAGPipeline:
    """Handles RAG query rewriting + classification + retrieval + generation."""

    def __init__(self, retriever=None, analyzer=None):
        self.retriever = retriever or QdrantVectorDB()
        self.analyzer = analyzer or DocumentAnalyzer()

    # -----------------------
    # Stage 1: Query Rewriting
    # -----------------------
    def rewrite_query(self, query: str) -> str:
        """Use LLM to rewrite the query for better retrieval"""
        try:
            rewrite_prompt = PROMPT_MODEL_REGISTRY["query_rewrite"]["prompt"]
            output_model = PROMPT_MODEL_REGISTRY["query_rewrite"]["output_model"]

            response = self.analyzer.analyze_document(
                rewrite_prompt.format(query=query)
            )
            rewritten = output_model(**response)
            return rewritten.rewritten_query
        except Exception:
            return query  # fallback: use original

    # -----------------------
    # Stage 2: Intent Classification
    # -----------------------
    def classify_intent(self, query: str) -> str:
        """Use LLM to classify query intent into a prompt type"""
        try:
            classification_prompt = PROMPT_MODEL_REGISTRY["query_classification"]["prompt"]
            output_model = PROMPT_MODEL_REGISTRY["query_classification"]["output_model"]

            response = self.analyzer.analyze_document(
                classification_prompt.format(query=query)
            )
            intent_obj = output_model(**response)
            return intent_obj.intent
        except Exception:
            return "rag_query"  # fallback default

    # -----------------------
    # Helper: Build Context
    # -----------------------
    def _build_context(self, results, max_chars=6000) -> str:
        context = []
        length = 0
        for r in results:
            chunk = r["metadata"].get("text") or ""
            if length + len(chunk) > max_chars:
                break
            context.append(chunk)
            length += len(chunk)
        return "\n\n".join(context)

    # -----------------------
    # Stage 3: Full RAG Run
    # -----------------------
    def run(self, query: str, top_k: int = 5) -> dict:
        # Step 1: rewrite query
        rewritten_query = self.rewrite_query(query)

        # Step 2: classify intent
        prompt_type = self.classify_intent(rewritten_query)

        # Step 3: load prompt + model
        prompt = PROMPT_MODEL_REGISTRY[prompt_type]["prompt"]
        output_model = PROMPT_MODEL_REGISTRY[prompt_type]["output_model"]

        # Step 4: retrieve relevant chunks
        results = self.retriever.search(query_vector=self._embed_query(rewritten_query), top_k=top_k)
        if not results:
            return {"answer": "No relevant documents found.", "sources": []}

        # Step 5: build context + final prompt
        context_text = self._build_context(results)
        prompt_text = prompt.format(context=context_text, query=rewritten_query)

        # Step 6: call LLM for final answer
        try:
            answer = self.analyzer.analyze_document(prompt_text)
        except Exception:
            answer = {"summary": "LLM failed, here is the retrieved context.", "context": context_text}

        # Step 7: prepare sources
        sources = [
            {"doc_id": r["metadata"].get("doc_id"), "score": r["score"]}
            for r in results
        ]

        # Step 8: return structured response
        return output_model(answer=answer, sources=sources).dict()

    # -----------------------
    # Placeholder: Embedding Generator
    # -----------------------
    def _embed_query(self, query: str) -> list[float]:
        """Generate embedding for the query. Replace with actual embedding model."""
        raise NotImplementedError("Implement query embedding generation here")
