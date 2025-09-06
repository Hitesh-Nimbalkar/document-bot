
# Import output models at the top
from models.models import DataAnalysisMetadata, DocumentComparisonResult
# =============================================================================
# PROMPT REGISTRY (add prompt objects here as needed)
# =============================================================================
DOCUMENT_ANALYSIS_PROMPT = """
You are an expert document analyst.
Analyze the following document and extract key insights, summary, and any important metadata.
Document:
{document_text}
Instructions:
- Provide a concise summary.
- List key points or findings.
- Extract any relevant metadata (e.g., author, date, topic) if available.
"""
# Prompt for document comparison
DOCUMENT_COMPARATOR_PROMPT = """
You are an expert at comparing documents.
Compare the following two documents and provide:
- A summary of similarities
- A summary of differences
- Key points unique to each document
- Any relevant metadata or insights
Document 1:
{document_1}
Document 2:
{document_2}
"""

# =============================================================================
# PROMPT-MODEL MAPPING REGISTRY (map prompt names to output/response models)
# =============================================================================
PROMPT_MODEL_REGISTRY = {
    "document_analysis": {
        "prompt": DOCUMENT_ANALYSIS_PROMPT,
        "output_model": DataAnalysisMetadata
    },
    "document_comparator": {
        "prompt": DOCUMENT_COMPARATOR_PROMPT,
        "output_model": DocumentComparisonResult
    },
}