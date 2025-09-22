


# Import output models at the top
from models.models import DataAnalysisMetadata, DocumentComparisonResult
from pydantic import BaseModel
from typing import Dict, Any
# =============================================================================
# OUTPUT MODELS
# =============================================================================
class RAGOutput(BaseModel):
    answer: Dict[str, Any]  # could be structured like {"summary": str, ...}
    sources: list[Dict[str, Any]]
class QueryIntent(BaseModel):
    intent: str 
class RewrittenQuery(BaseModel):
    rewritten_query: str
    
class RerankedResults(BaseModel):
    ranked_chunks: list[Dict[str, Any]]
    
    """
1. Rewrite query (LLM) → rewritten_query
2. Classify query intent (LLM) → rag_query / rag_summary / rag_factcheck
3. Retrieve top 20 chunks from Qdrant
4. Re-rank chunks (LLM) → return top 5
5. Build context → fill chosen prompt → final LLM answer
"""
# =============================================================================
# PROMPTS
# =============================================================================

DOCUMENT_ANALYSIS_PROMPT = """
You are an expert document analyst. Analyze the following document and extract key insights, summary, and metadata.
Return your analysis as a JSON object with the following structure:
{
  "title": "Document title (if available)",
  "author": "Author name (if available)",
  "date_created": "Creation date (if available)",
  "document_type": "Type of document (e.g., report, manual, article)",
  "language": "Document language",
  "num_pages": number_of_pages,
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "summary": "Concise summary of the document",
  "additional_metadata": {"key": "value"}
}
Document:
{document_text}
"""
DOCUMENT_COMPARATOR_PROMPT = """
You are an expert at comparing documents.
Compare the following two documents and provide:
- A summary of similarities
- A summary of differences
- Key points unique to each document
- Any relevant metadata or insights
Document 1:
{document_1}
Document 2:
{document_2}
"""
# === RAG Prompts ===
RAG_QA_PROMPT = """
You are a helpful assistant.
Answer the following question using the context.
If the answer is not in the context, say "I don't know".
Context:
{context}
Question:
{query}
Answer:
"""
RAG_SUMMARY_PROMPT = """
You are a summarization assistant.
Summarize the following context into key points and a short summary.
Context:
{context}
Summary:
"""
RAG_FACTCHECK_PROMPT = """
You are a fact-checking assistant.
Given the context, determine if the following statement is supported or not.
Context:
{context}
Statement:
{query}
Answer with "Supported", "Not Supported", or "Insufficient Information".
"""
# === Query Classification Prompt ===
QUERY_CLASSIFICATION_PROMPT = """
You are a classifier. Categorize the following user query into one of the types:
- rag_query: A question answering request based on context.
- rag_summary: A summarization request.
- rag_factcheck: A fact-checking or verification request.
User Query:
{query}
Answer with only one label: rag_query, rag_summary, or rag_factcheck.
"""
QUERY_REWRITE_PROMPT = """
You are a query rewriting assistant.
Rewrite the following user query into a clear, detailed version that is optimized for document retrieval.
Original Query:
{query}
Rewritten Query:
"""
RERANK_PROMPT = """
You are a re-ranking assistant.
Given a query and a list of document chunks, rank the chunks by their relevance to the query.
Query:
{query}
Chunks:
{chunks}
Instructions:
- Return the chunks in order of most relevant to least relevant.
- Keep the original chunk text and metadata.
"""
# =============================================================================
# PROMPT-MODEL MAPPING REGISTRY
# =============================================================================
# =============================================================================
# PROMPT-MODEL MAPPING
# =============================================================================
PROMPT_MODEL_REGISTRY = {
    "query_rewrite": {
        "prompt": QUERY_REWRITE_PROMPT,
        "output_model": RewrittenQuery,
    },
    "query_classification": {
        "prompt": QUERY_CLASSIFICATION_PROMPT,
        "output_model": QueryIntent,
    },
    "rag_query": {
        "prompt": RAG_QA_PROMPT,
        "output_model": RAGOutput,
    },
    "rag_summary": {
        "prompt": RAG_SUMMARY_PROMPT,
        "output_model": RAGOutput,
    },
    "rag_factcheck": {
        "prompt": RAG_FACTCHECK_PROMPT,
        "output_model": RAGOutput,
    },
    "document_analysis": {
        "prompt": DOCUMENT_ANALYSIS_PROMPT,
        "output_model": DataAnalysisMetadata,
    },
    "document_comparator": {
        "prompt": DOCUMENT_COMPARATOR_PROMPT,
        "output_model": DocumentComparisonResult,
    },
    "rerank": {
    "prompt": RERANK_PROMPT,
    "output_model": RerankedResults
    },
}

