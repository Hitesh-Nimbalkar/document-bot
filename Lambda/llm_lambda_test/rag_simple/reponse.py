


# rag_simple.py
"""
Intent-Aware RAG Pipeline for Testing
====================================
⚡ Complete Workflow:
User Query → "Summarize the last 3 reports."
Intent Classifier → ("last 3 reports", SUMMARIZE)
Vector DB Retrieval → fetch relevant chunks.
Prompt Registry Lookup → find SUMMARIZE template.
Fill Template → "Summarize the following retrieved text…" + chunks.
Send to LLM → Get nice structured output.
Features:
1. Intent detection and query cleaning
2. Vector search with cleaned queries  
3. Intent-specific prompt templates
4. Structured output generation
5. Performance tracking with timing
"""
from typing import Any, Dict, List, Optional
import time
from utils.logger import CustomLogger
from utils.model_loader import ModelLoader
# Remove get_embeddings import since it's broken
# from utils.embeddings import get_embeddings
from vector_db.vector_db import QdrantVectorDB
from rag_simple.query_processor import SimpleQueryProcessor, Intent
logger = CustomLogger(__name__)
class SimpleRAGPipeline:
    """Simple RAG Pipeline for testing semantic search functionality"""
    def __init__(self, project_name: str, model_loader: Optional[ModelLoader] = None):
        """Initialize simple RAG pipeline with performance optimizations"""
        self.project_name = project_name
        self.model_loader = model_loader
        
        # Vector DB manager - now uses connection pooling for better performance
        self.vector_db = QdrantVectorDB()
        
        # Query processor for intent detection and query cleaning
        self.query_processor = SimpleQueryProcessor()
        
        # Query processor now handles prompt selection logic - no need for separate registry
        
        # Performance tracking
        self._performance_stats = {
            "intent_detection_time": 0.0,
            "embedding_time": 0.0,
            "search_time": 0.0, 
            "context_time": 0.0,
            "generation_time": 0.0
        }
        
        logger.info(f"🚀 Intent-Aware RAG Pipeline initialized for project '{project_name}' using collection '{self.vector_db.config.COLLECTION}'")
        logger.info("⚡ Workflow enabled: User Query → Query Processor (Intent + Prompt Selection) → Vector DB → LLM → Structured Output")
    def run(
        self,
        query: str,
        top_k: int = 5,
        event: Optional[dict] = None,
        payload: Optional[dict] = None,
    ) -> dict:
        """Run simple RAG pipeline - just semantic search + LLM answer"""
        
        try:
            # Basic validation
            if not query or not query.strip():
                return self._create_error_response("Empty query provided")
            logger.info(f"🔎 Simple RAG Query: {query}")
            # ==================================================
            # Step 1: Intent Detection & Query Processing (NEW!)
            # ==================================================
            logger.info("🎯 Step 1: Intent detection and query processing")
            intent_start = time.time()
            try:
                clean_query, detected_intent = self.query_processor.detect_intent_and_clean(query)
                intent_time = time.time() - intent_start
                self._performance_stats["intent_detection_time"] = intent_time
                
                logger.info(f"✅ Intent detection completed in {intent_time:.3f}s")
                logger.info(f"   Original: '{query}'")
                logger.info(f"   Cleaned: '{clean_query}'")
                logger.info(f"   Intent: {detected_intent.name}")
                
            except Exception as e:
                intent_time = time.time() - intent_start
                logger.error(f"❌ Intent detection failed in {intent_time:.3f}s: {e}")
                # Fallback to original query if intent detection fails
                clean_query = query
                detected_intent = Intent.ANSWER
                self._performance_stats["intent_detection_time"] = intent_time
            # ==================================================
            # Step 2: Get Query Embedding (with timing)
            # ==================================================
            logger.info("📊 Step 2: Getting query embedding")
            embed_start = time.time()
            try:
                # Use model loader embed method directly with the CLEANED query
                if not self.model_loader:
                    return self._create_error_response("Model loader not available for embedding generation")
                
                # Get embedding using model loader's embed method with clean query
                embedding_result = self.model_loader.embed(clean_query, model_id="amazon.titan-embed-text-v2:0")
                
                # Handle tuple return (embedding, metadata) - same as query processor
                if isinstance(embedding_result, tuple):
                    query_embedding = embedding_result[0]
                else:
                    query_embedding = embedding_result
                
                if not query_embedding:
                    return self._create_error_response("Empty embedding generated")
                
                embed_time = time.time() - embed_start
                self._performance_stats["embedding_time"] = embed_time
                logger.info(f"✅ Query embedding generated in {embed_time:.2f}s (dim={len(query_embedding)})")
            except Exception as e:
                embed_time = time.time() - embed_start
                logger.error(f"❌ Embedding generation failed in {embed_time:.2f}s: {e}")
                return self._create_error_response(f"Embedding generation failed: {e}")
            # ==================================================
            # Step 3: Simple Vector Search (with timing)
            # ==================================================
            logger.info(f"📚 Step 3: Searching vector database (top_k={top_k})")
            search_start = time.time()
            try:
                # Simple search - QdrantVectorDB uses its own collection config
                search_results = self.vector_db.search(
                    query_vector=query_embedding,
                    top_k=top_k
                )
                
                if not search_results:
                    search_time = time.time() - search_start
                    logger.warning(f"❌ No relevant documents found in {search_time:.2f}s")
                    return self._create_no_results_response(query)
                
                search_time = time.time() - search_start
                self._performance_stats["search_time"] = search_time
                logger.info(f"📄 Found {len(search_results)} relevant chunks in {search_time:.2f}s")
                
            except Exception as e:
                search_time = time.time() - search_start
                logger.error(f"❌ Vector search failed in {search_time:.2f}s: {e}")
                return self._create_error_response(f"Vector search failed: {e}")
            # ==================================================
            # Step 4: Build Simple Context (with timing)
            # ==================================================
            logger.info("📝 Step 4: Building context")
            context_start = time.time()
            context_parts = []
            sources = []
            
            # Much more conservative token limits: Keep total context under 2500 tokens
            # This leaves room for prompt structure and answer generation
            MAX_CONTEXT_LENGTH = 2500 * 3  # Conservative: 3 chars per token instead of 4
            current_length = 0
            
            for i, result in enumerate(search_results):
                # Extract content and metadata - QdrantVectorDB returns {id, score, metadata}
                metadata = result.get("metadata", {})
                content = metadata.get("text", "")
                filename = metadata.get("filename", f"Source_{i+1}")
                
                # Much more aggressive truncation - limit each source to 500 chars
                if len(content) > 500:
                    content = content[:500] + "..."
                
                # Check if adding this content would exceed our limit
                source_text = f"--- Source {i+1}: {filename} ---\n{content}"
                if current_length + len(source_text) > MAX_CONTEXT_LENGTH:
                    logger.info(f"📏 Context truncated at source {i+1} to stay within token limits")
                    break
                
                # Add to context
                context_parts.append(source_text)
                current_length += len(source_text)
                
                # Add to sources list
                sources.append({
                    "filename": filename,
                    "content": content[:200] + "..." if len(content) > 200 else content,
                    "score": result.get("score", 0.0),
                    "metadata": metadata
                })
            
            context_text = "\n\n".join(context_parts)
            context_time = time.time() - context_start
            self._performance_stats["context_time"] = context_time
            logger.info(f"📝 Built context from {len(sources)} sources in {context_time:.3f}s (approx {len(context_text)} chars, ~{len(context_text)//3} tokens)")
            # ==================================================
            # Step 5: Complete Query Processing & Prompt Generation
            # ==================================================
            logger.info("🎯 Step 5: Complete query processing and prompt generation")  
            gen_start = time.time()
            try:
                # ⚡ New Simplified Workflow: Query processor handles everything!
                # Just pass query + context, get back filled prompt ready for LLM
                _, detected_intent_check, prompt_text = self.query_processor.process_query_and_get_prompt(
                    query=query,
                    context=context_text
                )
                
                # Verify intent consistency (should match what we detected earlier)
                if detected_intent_check != detected_intent:
                    logger.warning(f"⚠️ Intent mismatch: {detected_intent} vs {detected_intent_check}")
                
                logger.info(f"✅ Query processor generated {detected_intent.name} prompt")
                
                # Log prompt length for debugging
                prompt_length = len(prompt_text)
                estimated_tokens = prompt_length // 3  # More conservative estimate
                logger.info(f"📏 Prompt length: {prompt_length} chars (~{estimated_tokens} tokens)")
                
                # If prompt is still too long, use fewer sources (fallback handling)
                if estimated_tokens > 3000:  # Much more conservative limit
                    logger.warning("⚠️ Prompt too long, reducing context and regenerating")
                    # Rebuild with just first source, heavily truncated
                    if sources:
                        first_source = sources[0]
                        content = first_source["metadata"].get("text", "")[:300]  # Very short
                        filename = first_source["filename"]
                        reduced_context = f"--- Source: {filename} ---\n{content}"
                        
                        # Regenerate prompt with reduced context
                        _, _, prompt_text = self.query_processor.process_query_and_get_prompt(
                            query=query,
                            context=reduced_context
                        )
                        logger.info(f"📏 Reduced prompt length: {len(prompt_text)} chars (~{len(prompt_text)//3} tokens)")
                    else:
                        # Last resort - no context at all
                        logger.warning("⚠️ Using minimal context due to token limits")
                        minimal_context = "Limited context available due to token constraints."
                        _, _, prompt_text = self.query_processor.process_query_and_get_prompt(
                            query=query,
                            context=minimal_context
                        )
                
                logger.info(f"🚀 Sending to LLM: Ready for {detected_intent.name.lower()} generation")
                
                # Generate answer using model loader
                if self.model_loader:
                    # Use parameters from UI payload instead of hardcoded values
                    max_tokens = payload.get("max_tokens", 2048) if payload else 2048
                    temperature = payload.get("temperature", 0.7) if payload else 0.7
                    
                    logger.info(f"🎯 Using UI parameters: max_tokens={max_tokens}, temperature={temperature}")
                    
                    raw_answer, model_meta = self.model_loader.generate(
                        prompt_text,
                        max_tokens=max_tokens,
                        temperature=temperature
                    )
                    
                    # Clean up the raw answer to make it user-friendly
                    if raw_answer:
                        # Remove extra whitespace and clean up formatting
                        clean_answer = raw_answer.strip()
                        
                        # Remove common model artifacts
                        clean_answer = clean_answer.replace('\n\n\n', '\n\n')  # Remove triple newlines
                        clean_answer = clean_answer.replace('  ', ' ')  # Remove double spaces
                        
                        # If answer is too short or looks like gibberish, provide fallback
                        if len(clean_answer) < 10 or not any(word in clean_answer.lower() for word in ['the', 'a', 'an', 'is', 'are', 'was', 'were', 'to', 'of', 'in', 'for']):
                            clean_answer = "I found some relevant information but couldn't generate a clear answer. Please check the sources below for details."
                        
                        # Simple answer format with clean text
                        answer = {"summary": clean_answer}
                        
                        gen_time = time.time() - gen_start
                        self._performance_stats["generation_time"] = gen_time
                        
                        # Log the raw vs clean answer for debugging
                        if raw_answer != clean_answer:
                            logger.info(f"🧹 Cleaned answer: '{raw_answer[:100]}...' → '{clean_answer[:100]}...'")
                    else:
                        # Handle empty response
                        answer = {"summary": "I couldn't generate a response. Please try rephrasing your question or check the sources below."}
                        gen_time = time.time() - gen_start
                        self._performance_stats["generation_time"] = gen_time
                        
                else:
                    # Fallback if no model loader
                    answer = {"summary": "Model loader not available"}
                    model_meta = {}
                    gen_time = time.time() - gen_start
                    self._performance_stats["generation_time"] = gen_time
                
                logger.info(f"✅ Answer generated successfully in {gen_time:.2f}s")
                
            except Exception as e:
                error_msg = str(e)
                gen_time = time.time() - gen_start
                self._performance_stats["generation_time"] = gen_time
                logger.error(f"❌ Answer generation failed in {gen_time:.2f}s: {e}")
                
                # Check if it's a token limit error and provide helpful info
                if "too many input tokens" in error_msg.lower() or "max input tokens" in error_msg.lower():
                    logger.error("💡 Tip: Context is still too long. Consider using fewer sources or shorter content.")
                
                answer = {
                    "summary": f"Sorry, I encountered an error generating the answer: {e}",
                    "error": str(e)
                }
                model_meta = {}
            # ==================================================
            # Step 6: Format Response with Performance Stats
            # ==================================================
            total_time = sum(self._performance_stats.values())
            
            response = {
                "answer": answer,
                "sources": sources,
                "query": query,
                "clean_query": clean_query,  # Include cleaned query
                "detected_intent": detected_intent.name,  # Include detected intent
                "total_sources": len(sources),
                "pipeline_mode": "simple_with_intent",  # Updated pipeline mode
                "success": True,
                "performance": {
                    "total_time": round(total_time, 3),
                    "intent_detection_time": round(self._performance_stats["intent_detection_time"], 3),
                    "embedding_time": round(self._performance_stats["embedding_time"], 3),
                    "search_time": round(self._performance_stats["search_time"], 3),
                    "context_time": round(self._performance_stats["context_time"], 3),
                    "generation_time": round(self._performance_stats["generation_time"], 3),
                    "breakdown": f"Intent: {self._performance_stats['intent_detection_time']:.3f}s | Embed: {self._performance_stats['embedding_time']:.2f}s | Search: {self._performance_stats['search_time']:.2f}s | Context: {self._performance_stats['context_time']:.3f}s | Generate: {self._performance_stats['generation_time']:.2f}s"
                }
            }
            
            # Add cost info if available
            if model_meta and "cost" in model_meta:
                response["cost_usd"] = model_meta["cost"]
            logger.info(f"✅ Intent-aware RAG pipeline completed in {total_time:.2f}s total - {response['performance']['breakdown']}")
            return response
        except Exception as e:
            logger.error(f"💥 Intent-aware RAG pipeline failed: {e}")
            return self._create_error_response(f"Pipeline failed: {e}")
    def _create_error_response(self, error_message: str) -> dict:
        """Create standardized error response"""
        # Make error messages more user-friendly
        user_friendly_message = "I encountered an issue while processing your request. Please try again."
        
        if "embedding" in error_message.lower():
            user_friendly_message = "I had trouble understanding your question. Please try rephrasing it."
        elif "vector search" in error_message.lower():
            user_friendly_message = "I couldn't find relevant documents for your query. Try using different keywords."
        elif "token" in error_message.lower():
            user_friendly_message = "Your question is too complex. Please try asking a simpler, more specific question."
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
            "error": error_message,  # Keep technical error for debugging
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

