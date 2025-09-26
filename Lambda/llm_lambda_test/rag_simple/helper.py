

"""
Helper functions for RAG Pipeline
=================================
Contains utility functions for response cleaning and text processing.
"""
import re
from utils.logger import CustomLogger
logger = CustomLogger(__name__)
def clean_llm_response(text: str) -> str:
    """Clean LLM response by removing repetitive content and artifacts"""
    if not text or not text.strip():
        return "No response generated."
    
    try:
        # Basic cleanup
        clean_text = text.strip()
        clean_text = clean_text.replace('\n\n\n', '\n\n')  # Remove triple newlines
        clean_text = clean_text.replace('  ', ' ')  # Remove double spaces
        
        # Remove repetitive sentences
        clean_text = _remove_repetitive_sentences(clean_text)
        
        # Clean patterns
        clean_text = _clean_repetitive_patterns(clean_text)
        
        # Validate result
        if len(clean_text) < 10:
            return "I found relevant information but couldn't generate a clear answer. Please check the sources below."
        
        return clean_text
        
    except Exception as e:
        logger.error(f"❌ Error cleaning response: {e}")
        return text[:1000] + "..." if len(text) > 1000 else text
def _remove_repetitive_sentences(text: str) -> str:
    """Remove duplicate and similar sentences"""
    try:
        sentences = [s.strip() for s in text.split('.') if s.strip()]
        seen_sentences = set()
        unique_sentences = []
        
        for sentence in sentences:
            clean_sentence = sentence.lower().strip()
            
            # Skip short sentences
            if len(clean_sentence) < 10:
                continue
                
            # Check for duplicates
            if clean_sentence in seen_sentences:
                logger.info(f"🔄 Removed duplicate: '{sentence[:50]}...'")
                continue
            
            # Check similarity (simplified)
            is_similar = any(
                _calculate_similarity(clean_sentence, seen) > 0.8 
                for seen in seen_sentences
            )
            
            if is_similar:
                logger.info(f"🔄 Removed similar: '{sentence[:50]}...'")
                continue
            
            seen_sentences.add(clean_sentence)
            unique_sentences.append(sentence)
            
            # Limit length
            if len(unique_sentences) >= 15:
                logger.info("✂️ Truncated response to prevent excessive length")
                break
        
        result = '. '.join(unique_sentences)
        if result and not result.endswith('.'):
            result += '.'
            
        logger.info(f"🧹 Sentences: {len(sentences)} → {len(unique_sentences)}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error removing repetitive sentences: {e}")
        return text
def _clean_repetitive_patterns(text: str) -> str:
    """Clean repetitive patterns like bullet points and citations"""
    try:
        # Remove repeated lines
        lines = text.split('\n')
        unique_lines = []
        seen_lines = set()
        
        for line in lines:
            clean_line = re.sub(r'\s+', ' ', line.strip().lower())
            if clean_line and clean_line not in seen_lines and len(clean_line) > 5:
                seen_lines.add(clean_line)
                unique_lines.append(line.strip())
        
        result = '\n'.join(unique_lines)
        result = re.sub(r'(\d+\.[^0-9]+?)(\1){2,}', r'\1', result)  # Remove repeated numbered items
        result = re.sub(r'(●[^●]+?)(\1){2,}', r'\1', result)  # Remove repeated bullet points
        # Remove repeated parenthetical citations
        result = re.sub(r'(\([^)]+\)\s*)(\1){2,}', r'\1', result)
        
        return result.strip()
        
    except Exception as e:
        logger.error(f"❌ Error cleaning patterns: {e}")
        return text
def _calculate_similarity(text1: str, text2: str) -> float:
    """Calculate Jaccard similarity between two texts"""
    try:
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if len(words1) < 3 or len(words2) < 3:
            return 0.0
        
        intersection = len(words1.intersection(words2))
        union = len(words1.union(words2))
        
        return intersection / union if union > 0 else 0.0
        
    except Exception:
        return 0.0
def create_error_response(error_message: str) -> dict:
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
def create_no_results_response(query: str) -> dict:
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
def remove_repetitive_content(text: str) -> str:
    """Remove repetitive content from LLM responses"""
    from utils.logger import CustomLogger
    logger = CustomLogger(__name__)
    
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
        result = clean_repetitive_patterns(result)
        
        logger.info(f"🧹 Repetition removal: {len(sentences)} → {len(unique_sentences)} sentences")
        return result
        
    except Exception as e:
        logger.error(f"❌ Error removing repetitive content: {e}")
        # Return truncated version as fallback
        return text[:1000] + "..." if len(text) > 1000 else text
def clean_repetitive_patterns(text: str) -> str:
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
    result = re.sub(r'(\d+\.[^0-9]+?)(\1){2,}', r'\1', result)  # Remove repeated numbered items
    result = re.sub(r'(●[^●]+?)(\1){2,}', r'\1', result)  # Remove repeated bullet points
    # Remove repeated parenthetical citations
    result = re.sub(r'(\([^)]+\)\s*)(\1){2,}', r'\1', result)
    
    return result.strip()

