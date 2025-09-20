
"""context_builder.py
SmartContextBuilder extracted for building enriched context.
"""
from typing import List, Dict
from utils.logger import CustomLogger
from datetime import datetime
logger = CustomLogger(__name__)
class SmartContextBuilder:
    """Build enriched context combining documents + recent relevant chat history."""
    def __init__(self):
        logger.info("📝 SmartContextBuilder initialized")
    def build_enhanced_context(self, results: List[Dict], query: str,
                               chat_history: List[Dict] = None, context_info: dict = None,
                               max_chars: int = 6000) -> str:
        context_parts = []
        length = 0
        if chat_history:
            relevant_history = self._extract_relevant_history(chat_history, query)
            if relevant_history:
                chat_context = self._format_chat_context(relevant_history)
                if chat_context:
                    context_parts.append(f"Conversation Context:\n{chat_context}\n")
                    length += len(chat_context)
        document_context = []
        for i, result in enumerate(results):
            metadata = result.get("metadata", {})
            chunk_text = metadata.get("text") or ""
            if length + len(chunk_text) > max_chars:
                break
            doc_info = self._build_document_info(metadata)
            enriched_chunk = f"[Document {i+1}]{doc_info}\n{chunk_text}"
            document_context.append(enriched_chunk)
            length += len(enriched_chunk)
        if document_context:
            context_parts.append("Relevant Documents:\n" + "\n\n".join(document_context))
        return "\n\n".join(context_parts)
    def _extract_relevant_history(self, chat_history: List[Dict], query: str) -> List[Dict]:
        if not chat_history:
            return []
        recent = chat_history[-5:] if len(chat_history) > 5 else chat_history
        relevant = []
        for msg in recent:
            content = msg.get('content', '').strip()
            role = msg.get('role', 'user')
            if role in ['user', 'assistant'] and 10 < len(content) < 500:
                relevant.append(msg)
        return relevant[-3:]
    def _format_chat_context(self, messages: List[Dict]) -> str:
        lines = []
        for m in messages:
            role = m.get('role', 'user').capitalize()
            content = m.get('content', '').strip()
            if len(content) > 200:
                content = content[:200] + '...'
            lines.append(f"{role}: {content}")
        return "\n".join(lines)
    def _build_document_info(self, metadata: Dict) -> str:
        filename = metadata.get("filename", "Unknown")
        file_type = metadata.get("file_type", "")
        parts = []
        if file_type:
            parts.append(f" ({file_type.upper()})")
        created_at = metadata.get("created_at")
        if created_at:
            try:
                doc_date = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                age_days = (datetime.now(doc_date.tzinfo) - doc_date).days
                if age_days == 0:
                    parts.append(" - Today")
                elif age_days == 1:
                    parts.append(" - Yesterday")
                elif age_days < 7:
                    parts.append(f" - {age_days} days ago")
                elif age_days < 30:
                    parts.append(f" - {age_days//7} weeks ago")
                else:
                    parts.append(f" - {doc_date.strftime('%Y-%m-%d')}")
            except:
                pass
        if metadata.get("user_id") and hasattr(self, 'current_user_id') and metadata["user_id"] != self.current_user_id:
            parts.append(f" - By: {metadata['user_id']}")
        return f" - {filename}{''.join(parts)}" if parts else f" - {filename}"

