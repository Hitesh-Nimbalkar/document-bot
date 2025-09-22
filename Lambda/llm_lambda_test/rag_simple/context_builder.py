

"""
Context Builder for RAG Pipeline
===============================
Builds clean, deduplicated context from search results.
"""
import time
from typing import List, Dict, Tuple
from utils.logger import CustomLogger
logger = CustomLogger(__name__)
class ContextBuilder:
    """Builds context from search results with deduplication"""
    
    def __init__(self, max_context_length: int = 7500, max_source_length: int = 500):
        self.max_context_length = max_context_length
        self.max_source_length = max_source_length
        logger.info(f"📝 ContextBuilder initialized: max_context={max_context_length}, max_source={max_source_length}")
    
    def build_context(self, search_results: List[Dict]) -> Tuple[str, List[Dict], float]:
        """Build context from search results with deduplication"""
        start_time = time.time()
        
        try:
            context_parts = []
            sources = []
            current_length = 0
            seen_hashes = set()
            
            for i, result in enumerate(search_results):
                metadata = result.get("metadata", {})
                content = metadata.get("text", "")
                filename = metadata.get("filename", f"Source_{i+1}")
                
                # Skip empty or duplicate content
                if not content.strip():
                    continue
                    
                content_hash = hash(content.lower().strip())
                if content_hash in seen_hashes:
                    logger.info(f"🔄 Skipping duplicate from {filename}")
                    continue
                seen_hashes.add(content_hash)
                
                # Truncate if too long
                if len(content) > self.max_source_length:
                    content = content[:self.max_source_length] + "..."
                
                # Check length limit
                source_text = f"--- Source {len(sources)+1}: {filename} ---\n{content}"
                if current_length + len(source_text) > self.max_context_length:
                    logger.info(f"📏 Context truncated at {len(sources)+1} sources")
                    break
                
                # Add to context and sources
                context_parts.append(source_text)
                current_length += len(source_text)
                
                sources.append({
                    "filename": filename,
                    "content": content[:200] + "..." if len(content) > 200 else content,
                    "score": result.get("score", 0.0),
                    "metadata": metadata
                })
            
            context_text = "\n\n".join(context_parts)
            build_time = time.time() - start_time
            
            logger.info(f"📝 Built context: {len(sources)} sources, {len(context_text)} chars ({build_time:.3f}s)")
            return context_text, sources, build_time
            
        except Exception as e:
            build_time = time.time() - start_time
            logger.error(f"❌ Context build failed: {e}")
            return "Error building context.", [], build_time
 
