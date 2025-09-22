



# =====================================================
# Simple Query Processor for RAG Simple Pipeline
# =====================================================
"""
🎯 Query Processor - Intent Detection & Prompt Selection Logic
=============================================================
Complete Query Processing Logic:
The RAG pipeline only needs to pass the query and context.
This processor handles ALL the logic for:
1. Intent detection from user queries
2. Query cleaning for vector search  
3. Prompt selection based on detected intent
4. Prompt filling with context
Usage in RAG Pipeline:
    clean_query, intent, prompt = processor.process_query_and_get_prompt(query, context)
    # Use clean_query for vector search
    # Use prompt for LLM generation
Example:
- Input: "summarize about regional trends" + context
- Output: ("regional trends", SUMMARIZE, filled_summary_prompt)
"""
import re
import logging
from enum import Enum
from typing import Tuple, Dict
from rag_simple.prompt_registry import PromptRegistry
logger = logging.getLogger(__name__)
# =====================================================
# Intent Enumeration
# =====================================================
class Intent(str, Enum):
    """Standardized intent categories for query processing"""
    SUMMARIZE = "SUMMARIZE"
    EXPLAIN   = "EXPLAIN"
    COMPARE   = "COMPARE"
    LIST      = "LIST"
    ANSWER    = "ANSWER"  # default / fallback
# =====================================================
# Simple Query Processor
# =====================================================
class SimpleQueryProcessor:
    """
    Lightweight query processor for simple RAG pipeline.
    Focuses on intent detection and query cleaning without heavy preprocessing.
    """
    
    # Standardized intent patterns (lowercase only)
    INTENT_PATTERNS: dict[Intent, list[str]] = {
        Intent.SUMMARIZE: [
            "summarize", "summary", "sum up", "overview", 
            "key points", "main points", "briefly", "tl;dr"
        ],
        Intent.EXPLAIN: [
            "explain", "describe", "tell me about", "what is", 
            "what are", "how does", "definition of", "define"
        ],
        Intent.COMPARE: [
            "compare", "difference", "versus", "vs", 
            "better than", "similar to", "contrast", "differ"
        ],
        Intent.LIST: [
            "list", "show me", "what are all", "enumerate", 
            "give me a list", "all the", "show all"
        ],
    }
    # Words to remove when cleaning queries
    CLEANUP_WORDS = {
        "about", "the", "a", "an", "of", "on", "for", "to", "me", 
        "please", "can", "you", "would", "could", "should"
    }
    def __init__(self):
        """Initialize the simple query processor with prompt registry"""
        self.prompt_registry = PromptRegistry()
        self.component_name = "query_processor"
        
        # Validate that all required prompts exist for this component
        if self.validate_component_prompts():
            logger.info("🔧 SimpleQueryProcessor initialized with validated query_processor prompts")
        else:
            logger.warning("⚠️ SimpleQueryProcessor initialized but some prompts failed validation")
        
        # Cache available prompts for performance
        self._available_prompts = self.prompt_registry.get_component_prompts(self.component_name)
    def detect_intent_and_clean(self, query: str) -> Tuple[str, Intent]:
        """
        Detect user intent from query with STANDARDIZED categories only.
        
        Args:
            query: The user's original query
            
        Returns:
            Tuple of (clean_search_query, detected_intent)
            
        Examples:
            "summarize about regional trends" → ("regional trends", Intent.SUMMARIZE)
            "explain market data" → ("market data", Intent.EXPLAIN)
            "regional trends" → ("regional trends", Intent.ANSWER)
        """
        if not query or not query.strip():
            logger.warning("Empty query provided")
            return "", Intent.ANSWER
            
        q_lower = query.lower().strip()
        detected_intent = Intent.ANSWER
        clean_query = query
        # Check each intent pattern
        for intent_type, patterns in self.INTENT_PATTERNS.items():
            for phrase in patterns:
                # Use regex to ensure word/phrase boundaries (avoid partial matches)
                if re.search(rf"\b{re.escape(phrase)}\b", q_lower):
                    detected_intent = intent_type
                    # Remove ALL patterns for that intent from the query
                    clean_query = q_lower
                    for pattern in patterns:
                        clean_query = re.sub(rf"\b{re.escape(pattern)}\b", " ", clean_query)
                    # Remove cleanup words and collapse spaces
                    words = [
                        word for word in clean_query.split() 
                        if word and word not in self.CLEANUP_WORDS
                    ]
                    clean_query = " ".join(words).strip()
                    logger.info(f"🎯 Intent: {detected_intent} | Clean query: '{clean_query}'")
                    return clean_query, detected_intent
        # Default case - no intent detected
        logger.info(f"🎯 Intent: {Intent.ANSWER} (default) | Query unchanged: '{query}'")
        return query, Intent.ANSWER
    def process_query_and_get_prompt(self, query: str, context: str) -> tuple[str, Intent, str]:
        """
        Complete query processing: detect intent, clean query, and get appropriate prompt.
        
        This is the main method the RAG pipeline should use - it handles all the logic
        for intent detection and prompt selection using the prompt registry.
        
        Args:
            query: The user's original query
            context: Retrieved context from vector database
            
        Returns:
            tuple: (clean_query_for_search, detected_intent, filled_prompt_for_llm)
        """
        if not query or not query.strip():
            logger.warning("Empty query provided, using default ANSWER intent")
            return "", Intent.ANSWER, self._get_fallback_prompt(context, query)
        
        # Step 1: Detect intent and clean query
        clean_query, detected_intent = self.detect_intent_and_clean(query)
        
        # Step 2: Get the appropriate prompt from the registry with error handling
        try:
            filled_prompt = self._get_prompt_for_intent(detected_intent, context, query)
        except Exception as e:
            logger.error(f"❌ Failed to get prompt for intent {detected_intent}: {e}")
            logger.info("🔄 Falling back to default ANSWER prompt")
            filled_prompt = self._get_fallback_prompt(context, query)
            detected_intent = Intent.ANSWER
        
        logger.info(f"🎯 Complete processing: '{query}' → '{clean_query}' + {self.component_name}/{detected_intent.name} prompt")
        return clean_query, detected_intent, filled_prompt
    
    def _get_prompt_for_intent(self, intent: Intent, context: str, query: str) -> str:
        """
        Get the appropriate prompt for the detected intent using the prompt registry.
        
        Args:
            intent: The detected intent
            context: Retrieved context from vector database
            query: The original user query
            
        Returns:
            The filled prompt template
            
        Raises:
            ValueError: If the prompt cannot be retrieved or filled
        """
        # Validate the prompt exists and has required variables
        if not self.prompt_registry.validate_prompt(
            self.component_name, 
            intent.value, 
            ["{context}", "{query}"]
        ):
            raise ValueError(f"Invalid prompt configuration for {self.component_name}/{intent.value}")
        
        # Get the filled prompt from the registry
        return self.prompt_registry.get_prompt(
            component=self.component_name,
            prompt_type=intent.value,
            context=context,
            query=query
        )
    
    def _get_fallback_prompt(self, context: str, query: str) -> str:
        """
        Get a fallback prompt when the primary prompt fails.
        
        Args:
            context: Retrieved context from vector database
            query: The original user query
            
        Returns:
            The fallback ANSWER prompt
        """
        try:
            return self.prompt_registry.get_prompt(
                component=self.component_name,
                prompt_type=Intent.ANSWER.value,
                context=context,
                query=query
            )
        except Exception as e:
            logger.error(f"❌ Even fallback prompt failed: {e}")
            # Last resort: create a basic prompt manually
            return f"""Based on the retrieved information below, provide a clear and helpful answer.
Retrieved Information:
{context}
User Request: {query}
Answer:"""
    def get_intent_display_name(self, intent: Intent) -> str:
        """Get a user-friendly display name for the intent"""
        display_names = {
            Intent.SUMMARIZE: "Summary",
            Intent.EXPLAIN: "Explanation", 
            Intent.COMPARE: "Comparison",
            Intent.LIST: "List",
            Intent.ANSWER: "Answer"
        }
        return display_names.get(intent, "Answer")
    def validate_cleaned_query(self, cleaned_query: str, min_length: int = 2) -> bool:
        """
        Validate that the cleaned query is meaningful for search.
        
        Args:
            cleaned_query: The cleaned search query
            min_length: Minimum number of characters required
            
        Returns:
            True if query is valid for search, False otherwise
        """
        if not cleaned_query or len(cleaned_query.strip()) < min_length:
            logger.warning(f"Cleaned query too short: '{cleaned_query}'")
            return False
            
        # Check if query has at least one meaningful word
        meaningful_words = [
            word for word in cleaned_query.split() 
            if len(word) > 2 and word not in self.CLEANUP_WORDS
        ]
        
        if not meaningful_words:
            logger.warning(f"No meaningful words in cleaned query: '{cleaned_query}'")
            return False
            
        return True
    
    def get_supported_prompts(self) -> Dict[str, str]:
        """
        Get all prompt types supported by this query processor component.
        Uses the cached prompts for better performance.
        
        Returns:
            Dictionary mapping prompt types to their descriptions
        """
        if hasattr(self, '_available_prompts') and self._available_prompts:
            return self._available_prompts
        
        # Fallback to direct registry call if cache is not available
        return self.prompt_registry.get_component_prompts(self.component_name)
    
    def validate_component_prompts(self) -> bool:
        """
        Validate that all required prompts exist for this component.
        Uses the prompt registry's validation methods.
        
        Returns:
            True if all prompts are valid, False otherwise
        """
        required_prompts = [intent.value for intent in Intent]
        required_vars = ["{context}", "{query}"]
        all_valid = True
        
        for prompt_type in required_prompts:
            if not self.prompt_registry.validate_prompt(
                self.component_name, 
                prompt_type, 
                required_vars
            ):
                all_valid = False
                logger.error(f"❌ Invalid prompt: {self.component_name}/{prompt_type}")
        
        if all_valid:
            logger.info(f"✅ All {self.component_name} component prompts are valid")
        
        return all_valid
    
    def get_prompt_instruction(self, intent: Intent) -> str:
        """
        Get the instruction/description for a specific intent's prompt.
        
        Args:
            intent: The intent to get the instruction for
            
        Returns:
            The instruction text or a default message
        """
        prompts = self.get_supported_prompts()
        return prompts.get(intent.value, "No instruction available")
    
    def is_prompt_available(self, intent: Intent) -> bool:
        """
        Check if a prompt is available for the given intent.
        
        Args:
            intent: The intent to check
            
        Returns:
            True if prompt is available, False otherwise
        """
        return intent.value in self.get_supported_prompts()
# =====================================================
# Usage Example and Testing
# =====================================================
if __name__ == "__main__":
    """Test the simple query processor with example queries and prompt registry integration"""
    
    processor = SimpleQueryProcessor()
    
    # Display available prompts from the registry
    print("🎯 Available Prompts from Registry:")
    print("=" * 50)
    available_prompts = processor.get_supported_prompts()
    for prompt_type, instruction in available_prompts.items():
        print(f"• {prompt_type}: {instruction}")
    print()
    
    test_queries = [
        "summarize about regional trends",
        "explain market data analysis", 
        "compare Q1 vs Q2 performance",
        "list all available products",
        "regional trends",  # No intent
        "what is machine learning",
        "summary of the report",
        "tell me about sales data"
    ]
    
    sample_context = "Sample context about market data, regional trends, and quarterly performance metrics..."
    
    print("🧪 Testing Simple Query Processor with Prompt Registry:")
    print("=" * 60)
    
    for query in test_queries:
        print(f"Original Query: '{query}'")
        
        # Test intent detection and cleaning
        clean_query, intent = processor.detect_intent_and_clean(query)
        is_valid = processor.validate_cleaned_query(clean_query)
        intent_display = processor.get_intent_display_name(intent)
        prompt_available = processor.is_prompt_available(intent)
        
        print(f"→ Clean Query: '{clean_query}'")
        print(f"→ Intent: {intent_display} ({intent.value})")
        print(f"→ Valid Query: {is_valid}")
        print(f"→ Prompt Available: {prompt_available}")
        
        # Test complete processing with prompt generation
        try:
            clean_q, detected_intent, filled_prompt = processor.process_query_and_get_prompt(query, sample_context)
            print(f"→ Generated Prompt: {len(filled_prompt)} characters")
            print(f"→ Processing Status: ✅ Success")
        except Exception as e:
            print(f"→ Processing Status: ❌ Error: {e}")
        
        print("-" * 50)

