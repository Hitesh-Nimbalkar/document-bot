

"""
Prompt Registry for RAG Simple Pipeline
=======================================
This module defines a registry of prompt templates used by the query_processor
component in a simple RAG pipeline.
Supported prompt types:
- SUMMARIZE: Generate comprehensive summaries
- EXPLAIN: Provide detailed explanations
- COMPARE: Compare and contrast aspects
- LIST: Create well-structured lists
- ANSWER: Provide direct answers (default/fallback)
Usage:
    registry.get_prompt("query_processor", "SUMMARIZE", context=context, query=query)
    registry.get_prompt("query_processor", "EXPLAIN", context=context, query=query)
"""
from typing import Dict
from utils.logger import CustomLogger
logger = CustomLogger(__name__)

class PromptRegistry:
    """Central registry for prompt templates, organized by pipeline component."""
    def __init__(self):
        self.templates = self._initialize_component_templates()
        logger.info(f"🎯 Prompt Registry initialized with {len(self.templates)} components")
    def _initialize_component_templates(self) -> Dict[str, Dict[str, Dict[str, str]]]:
        """Define all prompt templates grouped by component and type."""
        return {
            "query_processor": {
                "SUMMARIZE": {
                    "instruction": "Generate comprehensive summaries of retrieved information",
                    "template": """Based on the retrieved information below, provide a clear and comprehensive summary.
Focus on:
- Key findings and main points
- Important trends or patterns  
- Critical insights and takeaways
- Overall conclusions
Retrieved Information:
{context}
User Request: {query}
Summary:"""
                },
                "EXPLAIN": {
                    "instruction": "Provide detailed explanations with examples and context",
                    "template": """Based on the retrieved information below, provide a detailed explanation.
Focus on:
- Clear definitions and concepts
- How things work or function
- Examples and practical applications
- Background context and relationships
Retrieved Information:
{context}
User Request: {query}
Explanation:"""
                },
                "COMPARE": {
                    "instruction": "Compare and contrast different aspects with trade-offs",
                    "template": """Based on the retrieved information below, provide a thorough comparison.
Focus on:
- Key similarities
- Important differences
- Advantages and disadvantages
- Trade-offs and considerations
Retrieved Information:
{context}
User Request: {query}
Comparison:"""
                },
                "LIST": {
                    "instruction": "Create well-structured lists or enumerations",
                    "template": """Based on the retrieved information below, create a well-organized list.
Focus on:
- Clear, logical organization
- Numbered or bulleted format
- Brief descriptions
- Complete coverage of relevant points
Retrieved Information:
{context}
User Request: {query}
List:"""
                },
                "ANSWER": {
                    "instruction": "Provide direct, helpful answers with supporting evidence",
                    "template": """Based on the retrieved information below, provide a clear and helpful answer.
Focus on:
- Direct response to the specific question
- Supporting evidence from the context
- Concise explanations
- Practical, actionable information
Retrieved Information:
{context}
User Request: {query}
Answer:"""
                },
            }
        }
    def get_prompt(self, component: str, prompt_type: str, **kwargs) -> str:
        """Retrieve and fill a prompt template."""
        if component not in self.templates:
            logger.warning(f"⚠️ Component '{component}' not found, using 'query_processor'")
            component = "query_processor"
        if prompt_type not in self.templates[component]:
            logger.warning(f"⚠️ Prompt '{prompt_type}' not found, using 'ANSWER'")
            prompt_type = "ANSWER"
        template = self.templates[component][prompt_type]["template"]
        try:
            filled_prompt = template.format(**kwargs)
            logger.info(f"✅ Filled {component}/{prompt_type} prompt")
            return filled_prompt
        except KeyError as e:
            missing_var = str(e).strip("'")
            logger.error(f"❌ Missing variable '{missing_var}' for {component}/{prompt_type}")
            raise ValueError(f"Missing required variable '{missing_var}'")
    def get_component_prompts(self, component: str) -> Dict[str, str]:
        """Return all prompt types and their descriptions for a component."""
        if component not in self.templates:
            logger.warning(f"⚠️ Component '{component}' not found")
            return {}
        prompts = {
            prompt_type: data.get("instruction", "No description available")
            for prompt_type, data in self.templates[component].items()
        }
        logger.info(f"✅ Retrieved {len(prompts)} prompts for component '{component}'")
        return prompts
    def validate_prompt(self, component: str, prompt_type: str, required_vars: list) -> bool:
        """Validate if a prompt exists and contains all required variables."""
        if component not in self.templates:
            logger.error(f"❌ Component '{component}' not found")
            return False
        if prompt_type not in self.templates[component]:
            logger.error(f"❌ Prompt type '{prompt_type}' not found in '{component}'")
            return False
        template = self.templates[component][prompt_type]["template"]
        missing_vars = [var for var in required_vars if var not in template]
        if missing_vars:
            logger.error(f"❌ Missing variables in {component}/{prompt_type}: {missing_vars}")
            return False
        logger.info(f"✅ Prompt {component}/{prompt_type} validation passed")
        return True
    def fill_template(self, intent: str, context: str, query: str) -> str:
        """Legacy method mapping to the new get_prompt structure."""
        return self.get_prompt("query_processor", intent, context=context, query=query)

