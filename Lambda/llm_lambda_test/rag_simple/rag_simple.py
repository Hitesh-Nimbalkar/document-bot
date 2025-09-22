

# rag_simple.py
"""
Intent-Aware RAG Pipeline for Testing
====================================
⚡ Complete Workflow:
User Query → Query Processor → Vector DB → Context Builder → LLM → Clean Response
"""
from typing import Any, Dict, List, Optional
import time
from utils.logger import CustomLogger
from utils.model_loader import ModelLoader
from vector_db.vector_db import QdrantVectorDB
from rag_simple.query_processor import SimpleQueryProcessor, Intent
from rag_simple.context_builder import ContextBuilder
from rag_simple.helper import clean_llm_response
logger = CustomLogger(__name__)
class SimpleRAGPipeline:
    """Simple RAG Pipeline for testing semantic search functionality"""
    
    def __init__(self, project_name: str, model_loader: Optional[ModelLoader] = None):
        """Initialize simple RAG pipeline"""
        self.project_name = project_name
        self.model_loader = model_loader
        
        # Components
        self.vector_db = QdrantVectorDB()
        self.query_processor = SimpleQueryProcessor()
        self.context_builder = ContextBuilder()
        
        # Performance tracking
        self._performance_stats = {
            "intent_detection_time": 0.0,
            "embedding_time": 0.0,
            "search_time": 0.0, 
            "context_time": 0.0,
            "generation_time": 0.0
        }
        
        logger.info(f"🚀 Simple RAG Pipeline initialized for '{project_name}'")
    def run(self, query: str, top_k: int = 5, event: Optional[dict] = None, payload: Optional[dict] = None) -> dict:
        """Run simple RAG pipeline"""
        
        try:
            # Basic validation
            if not query or not query.strip():
                return self._create_error_response("Empty query provided")
            
            logger.info(f"🔎 Query: {query}")
            
            # Step 1: Intent Detection
            intent_start = time.time()
            try:
                clean_query, detected_intent = self.query_processor.detect_intent_and_clean(query)
                self._performance_stats["intent_detection_time"] = time.time() - intent_start
                logger.info(f"✅ Intent: {detected_intent.name} | Query: '{clean_query}'")
            except Exception as e:
                self._performance_stats["intent_detection_time"] = time.time() - intent_start
                logger.error(f"❌ Intent detection failed: {e}")
                clean_query, detected_intent = query, Intent.ANSWER
            # Step 2: Get Embedding
            embed_start = time.time()
            try:
                if not self.model_loader:
                    return self._create_error_response("Model loader not available")
                
                embedding_result = self.model_loader.embed(clean_query, model_id="amazon.titan-embed-text-v2:0")
                query_embedding = embedding_result[0] if isinstance(embedding_result, tuple) else embedding_result
                
                if not query_embedding:
                    return self._create_error_response("Empty embedding")
                
                self._performance_stats["embedding_time"] = time.time() - embed_start
                logger.info(f"✅ Embedding: dim={len(query_embedding)}")
            except Exception as e:
                self._performance_stats["embedding_time"] = time.time() - embed_start
                logger.error(f"❌ Embedding failed: {e}")
                return self._create_error_response(f"Embedding failed: {e}")
            # Step 3: Vector Search
            search_start = time.time()
            try:
                search_results = self.vector_db.search(query_vector=query_embedding, top_k=top_k)
                
                if not search_results:
                    self._performance_stats["search_time"] = time.time() - search_start
                    return self._create_no_results_response(query)
                
                self._performance_stats["search_time"] = time.time() - search_start
                logger.info(f"📄 Found {len(search_results)} results")
            except Exception as e:
                self._performance_stats["search_time"] = time.time() - search_start
                logger.error(f"❌ Search failed: {e}")
                return self._create_error_response(f"Search failed: {e}")
            # Step 4: Build Context
            context_text, sources, context_time = self.context_builder.build_context(search_results)
            self._performance_stats["context_time"] = context_time
            # Step 5: Generate Answer
            gen_start = time.time()
            try:
                _, _, prompt_text = self.query_processor.process_query_and_get_prompt(query=query, context=context_text)
                
                if self.model_loader:
                    max_tokens = payload.get("max_tokens", 1024) if payload else 1024
                    temperature = payload.get("temperature", 0.7) if payload else 0.7
                    
                    raw_answer, model_meta = self.model_loader.generate(prompt_text, max_tokens=max_tokens, temperature=temperature)
                    
                    # Use helper function for cleaning
                    clean_answer = clean_llm_response(raw_answer) if raw_answer else "No response generated"
                    answer = {"summary": clean_answer}
                    
                    if raw_answer != clean_answer:
                        logger.info(f"🧹 Cleaned response")
                else:
                    answer = {"summary": "Model loader not available"}
                    model_meta = {}
                
                self._performance_stats["generation_time"] = time.time() - gen_start
                logger.info(f"✅ Answer generated")
                
            except Exception as e:
                self._performance_stats["generation_time"] = time.time() - gen_start
                logger.error(f"❌ Generation failed: {e}")
                answer = {"summary": f"Error generating answer: {e}"}
                model_meta = {}
            # Calculate total time AFTER all steps are complete
            total_time = sum(self._performance_stats.values())
            
            # Return raw data - let lambda handler format the response
            return {
                "answer": answer,
                "sources": sources,
                "query": query,
                "clean_query": clean_query,
                "detected_intent": detected_intent.name,
                "total_sources": len(sources),
                "pipeline_mode": "simple_with_intent",
                "performance": {
                    "total_time": round(total_time, 3),
                    **{k: round(v, 3) for k, v in self._performance_stats.items()}
                },
                "cost_usd": model_meta.get("cost") if model_meta else None
            }
            
        except Exception as e:
            logger.error(f"💥 Pipeline failed: {e}")
            return self._create_error_response(f"Pipeline failed: {e}")
    def _create_error_response(self, error_message: str) -> dict:
        """Create standardized error response"""
        user_friendly_message = "I encountered an issue processing your request. Please try again."
        
        if "embedding" in error_message.lower():
            user_friendly_message = "I had trouble understanding your question. Please rephrase it."
        elif "search" in error_message.lower():
            user_friendly_message = "I couldn't find relevant documents. Try different keywords."
        elif "model loader" in error_message.lower():
            user_friendly_message = "The AI service is temporarily unavailable. Please try again later."
            
        return {
            "answer": {"summary": user_friendly_message},
            "sources": [],
            "query": "",
            "clean_query": "",
            "detected_intent": "UNKNOWN",
            "total_sources": 0,
            "pipeline_mode": "simple_with_intent",
            "success": False,
            "error": error_message,
            "user_message": user_friendly_message
        }
    def _create_no_results_response(self, query: str) -> dict:
        """Create response when no results found"""
        return {
            "answer": {"summary": "I couldn't find any relevant documents that answer your question. Try using different keywords or asking about a different topic."},
            "sources": [],
            "query": query,
            "clean_query": query,
            "detected_intent": "ANSWER",
            "total_sources": 0,
            "pipeline_mode": "simple_with_intent", 
            "success": False,
            "error": "No relevant documents found",
            "user_message": "No relevant documents found. Try different keywords."
        }
    def _remove_repetitive_content(self, text: str) -> str:
        """Remove repetitive content from LLM responses"""
        try:
            # Split into sentences
            sentences = [s.strip() for s in text.split('.') if s.strip()]
            
            # Track seen sentences and their variations
            seen_sentences = set()
            unique_sentences = []
            repetition_threshold = 0.8  # 80% similarity threshold
            
            for sentence in sentences:
                # Clean sentence for comparison
                clean_sentence = sentence.lower().strip()
                
                # Skip very short sentences
                if len(clean_sentence) < 10:
                    continue
                
                # Check for exact duplicates
                if clean_sentence in seen_sentences:
                    logger.info(f"🔄 Removed exact duplicate: '{sentence[:50]}...'")
                    continue
                
                # Check for similar sentences (fuzzy matching)
                is_similar = False
                for seen in seen_sentences:
                    # Simple similarity check: count common words
                    seen_words = set(seen.split())
                    current_words = set(clean_sentence.split())
                    
                    # Skip if either sentence is too short
                    if len(seen_words) < 3 or len(current_words) < 3:
                        continue
                    
                    # Calculate Jaccard similarity
                    intersection = len(seen_words.intersection(current_words))
                    union = len(seen_words.union(current_words))
                    similarity = intersection / union if union > 0 else 0
                    
                    if similarity > repetition_threshold:
                        logger.info(f"🔄 Removed similar sentence (similarity: {similarity:.2f}): '{sentence[:50]}...'")
                        is_similar = True
                        break
                
                if not is_similar:
                    seen_sentences.add(clean_sentence)
                    unique_sentences.append(sentence)
                
                # Limit to prevent extremely long responses
                if len(unique_sentences) >= 15:  # Max 15 unique sentences
                    logger.info("✂️ Truncated response to prevent excessive length")
                    break
            
            # Reconstruct the text
            result = '. '.join(unique_sentences)
            
            # Add final period if needed
            if result and not result.endswith('.'):
                result += '.'
            
            # Additional cleanup for common repetitive patterns
            result = self._clean_repetitive_patterns(result)
            
            logger.info(f"🧹 Repetition removal: {len(sentences)} → {len(unique_sentences)} sentences")
            return result
            
        except Exception as e:
            logger.error(f"❌ Error removing repetitive content: {e}")
            # Return truncated version as fallback
            return text[:1000] + "..." if len(text) > 1000 else text
    
    def _clean_repetitive_patterns(self, text: str) -> str:
        """Clean common repetitive patterns in text"""
        import re
        
        # Remove repeated phrases (same phrase appearing multiple times)
        lines = text.split('\n')
        unique_lines = []
        seen_lines = set()
        
        for line in lines:
            clean_line = re.sub(r'\s+', ' ', line.strip().lower())
            if clean_line and clean_line not in seen_lines and len(clean_line) > 5:
                seen_lines.add(clean_line)
                unique_lines.append(line.strip())
        
        result = '\n'.join(unique_lines)
        result = re.sub(r'(\d+\.[^0-9]+?)(\1){2,}', r'\1', result)  # Remove repeated numbered items        result = re.sub(r'(●[^●]+?)(\1){2,}', r'\1', result)  # Remove repeated bullet points        # Remove repeated bullet points or numbered lists        # Remove repeated parenthetical citations
        result = re.sub(r'(\([^)]+\)\s*)(\1){2,}', r'\1', result)
        
        return result.strip()

