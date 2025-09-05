
from rag.retriever import retrieve_relevant_chunks
from rag.prompt_builder import build_prompt
from rag.llm_client import call_llm
def run_rag_pipeline(query: str, payload: dict, chat_history: list = None) -> dict:
    """
    Main RAG pipeline: retrieves relevant chunks, builds prompt, calls LLM, returns answer.
    Args:
        query: User's question
        payload: Additional context (user/project/session info, filters, etc)
        chat_history: List of previous messages for context (optional)
    Returns:
        dict with answer and supporting context
    """
    # 1. Retrieve relevant chunks from vector DB
    retrieved_chunks = retrieve_relevant_chunks(query, payload)
    # 2. Build prompt for LLM, include chat_history if available
    prompt = build_prompt(query, retrieved_chunks, payload, chat_history=chat_history)
    # 3. Call LLM
    answer = call_llm(prompt, payload)
    # 4. Return answer and context
    return {
        'answer': answer,
        'context': retrieved_chunks,
        'prompt': prompt
    }
