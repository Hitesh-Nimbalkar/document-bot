


# rag_simple.py
"""
Simple RAG Pipeline for Testing
===============================
Simplified version focusing only on basic semantic search:
1. Get query embedding
2. Search vector database
3. Generate answer with LLM
No complex features:
- No query rewriting
- No intent classification  
- No metadata filtering
- No re-ranking
- No enhanced context building
"""
from typing import Any, Dict, List, Optional
from utils.logger import CustomLogger
from utils.model_loader import ModelLoader
# Remove get_embeddings import since it's broken
# from utils.embeddings import get_embeddings
from vector_db.vector_db import QdrantVectorDB
from prompt.prompt_library import PROMPT_MODEL_REGISTRY
logger = CustomLogger(__name__)

class SimpleRAGPipeline:
    """Simple RAG Pipeline for testing semantic search functionality"""
    def __init__(self, project_name: str, model_loader: Optional[ModelLoader] = None):
        """Initialize simple RAG pipeline"""
        self.project_name = project_name
        self.model_loader = model_loader
        
        # Vector DB manager - use QdrantVectorDB like the enhanced retriever
        self.vector_db = QdrantVectorDB()
        
        logger.info(f"🚀 Simple RAG Pipeline initialized for project '{project_name}' using collection '{self.vector_db.config.COLLECTION}'")
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
            # Step 1: Get Query Embedding
            # ==================================================
            logger.info("📊 Step 1: Getting query embedding")
            try:
                # Use model loader embed method directly (like query processor does)
                if not self.model_loader:
                    return self._create_error_response("Model loader not available for embedding generation")
                
                # Get embedding using model loader's embed method
                embedding_result = self.model_loader.embed(query, model_id="amazon.titan-embed-text-v2:0")
                
                # Handle tuple return (embedding, metadata) - same as query processor
                if isinstance(embedding_result, tuple):
                    query_embedding = embedding_result[0]
                else:
                    query_embedding = embedding_result
                
                if not query_embedding:
                    return self._create_error_response("Empty embedding generated")
                
                logger.info(f"✅ Query embedding generated (dim={len(query_embedding)})")
            except Exception as e:
                logger.error(f"❌ Embedding generation failed: {e}")
                return self._create_error_response(f"Embedding generation failed: {e}")
            # ==================================================
            # Step 2: Simple Vector Search
            # ==================================================
            logger.info(f"📚 Step 2: Searching vector database (top_k={top_k})")
            try:
                # Simple search - QdrantVectorDB uses its own collection config
                search_results = self.vector_db.search(
                    query_vector=query_embedding,
                    top_k=top_k
                )
                
                if not search_results:
                    logger.warning("❌ No relevant documents found")
                    return self._create_no_results_response(query)
                
                logger.info(f"📄 Found {len(search_results)} relevant chunks")
                
            except Exception as e:
                logger.error(f"❌ Vector search failed: {e}")
                return self._create_error_response(f"Vector search failed: {e}")
            # ==================================================
            # Step 3: Build Simple Context
            # ==================================================
            logger.info("📝 Step 3: Building context")
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
            logger.info(f"📝 Built context from {len(sources)} sources (approx {len(context_text)} chars, ~{len(context_text)//3} tokens)")
            # ==================================================
            # Step 4: Generate Answer
            # ==================================================
            logger.info("🧠 Step 4: Generating answer")
            try:
                # Build simple prompt
                prompt_text = self._build_simple_prompt(context_text, query)
                
                # Log prompt length for debugging
                prompt_length = len(prompt_text)
                estimated_tokens = prompt_length // 3  # More conservative estimate
                logger.info(f"📏 Prompt length: {prompt_length} chars (~{estimated_tokens} tokens)")
                
                # If prompt is still too long, use much fewer sources
                if estimated_tokens > 3000:  # Much more conservative limit
                    logger.warning("⚠️ Prompt still too long, using only first source with heavy truncation")
                    # Rebuild with just first source, heavily truncated
                    if sources:
                        first_source = sources[0]
                        content = first_source["metadata"].get("text", "")[:300]  # Very short
                        filename = first_source["filename"]
                        context_text = f"--- Source: {filename} ---\n{content}"
                        prompt_text = self._build_simple_prompt(context_text, query)
                        logger.info(f"📏 Emergency reduction - prompt length: {len(prompt_text)} chars (~{len(prompt_text)//3} tokens)")
                    else:
                        # Last resort - no context at all
                        logger.warning("⚠️ Using no context due to token limits")
                        context_text = "No relevant context found due to token limitations."
                        prompt_text = self._build_simple_prompt(context_text, query)
                
                # Generate answer using model loader
                if self.model_loader:
                    raw_answer, model_meta = self.model_loader.generate(
                        prompt_text,
                        max_tokens=512,
                        temperature=0.7
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
                        
                        # Log the raw vs clean answer for debugging
                        if raw_answer != clean_answer:
                            logger.info(f"🧹 Cleaned answer: '{raw_answer[:100]}...' → '{clean_answer[:100]}...'")
                    else:
                        # Handle empty response
                        answer = {"summary": "I couldn't generate a response. Please try rephrasing your question or check the sources below."}
                        
                else:
                    # Fallback if no model loader
                    answer = {"summary": "Model loader not available"}
                    model_meta = {}
                
                logger.info("✅ Answer generated successfully")
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Answer generation failed: {e}")
                
                # Check if it's a token limit error and provide helpful info
                if "too many input tokens" in error_msg.lower() or "max input tokens" in error_msg.lower():
                    logger.error("💡 Tip: Context is still too long. Consider using fewer sources or shorter content.")
                
                answer = {
                    "summary": f"Sorry, I encountered an error generating the answer: {e}",
                    "error": str(e)
                }
                model_meta = {}
            # ==================================================
            # Step 5: Format Response
            # ==================================================
            response = {
                "answer": answer,
                "sources": sources,
                "query": query,
                "total_sources": len(sources),
                "pipeline_mode": "simple",
                "success": True
            }
            
            # Add cost info if available
            if model_meta and "cost" in model_meta:
                response["cost_usd"] = model_meta["cost"]
            logger.info("✅ Simple RAG pipeline completed successfully")
            return response
        except Exception as e:
            logger.error(f"💥 Simple RAG pipeline failed: {e}")
            return self._create_error_response(f"Pipeline failed: {e}")
    def _build_simple_prompt(self, context: str, query: str) -> str:
        """Build a concise prompt for answer generation to save tokens"""
        return f"""Based on the context below, provide a clear and helpful answer to the question.
Context:
{context}
Question: {query}
Provide a clear, concise answer in plain English:"""
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
            "total_sources": 0,
            "pipeline_mode": "simple",
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
            "total_sources": 0,
            "pipeline_mode": "simple", 
            "success": False,
            "error": "No relevant documents found",
            "user_message": "No relevant documents found. Try different keywords."
        }
