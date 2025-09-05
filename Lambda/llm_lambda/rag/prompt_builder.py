
def build_prompt(query: str, retrieved_chunks: list, payload: dict, chat_history: list = None) -> str:
    """
    Build a prompt for the LLM using the user query, retrieved context chunks, and optional chat history.
    Includes both role and content for each message in sequence if chat_history is provided.
    """
    context = "\n\n".join([chunk['text'] for chunk in retrieved_chunks])
    chat_context = ""
    if chat_history:
        chat_context = "\n".join([
            f"{msg.get('role', 'user').capitalize()}: {msg.get('content', '')}"
            for msg in chat_history if 'content' in msg
        ])
    prompt = f"Context:\n{context}\n"
    if chat_context:
        prompt += f"\nRecent Conversation:\n{chat_context}\n"
    prompt += f"\nQuestion: {query}\nAnswer:"
    return prompt
