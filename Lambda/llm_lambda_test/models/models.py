from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

# ---------------------------
# Model for analyze_document action
# ---------------------------
class AnalyzeDocumentPayload(BaseModel):
    s3_bucket: str = Field(..., description="S3 bucket where the document is stored")
    s3_key: str = Field(..., description="S3 key (path) to the document")
    project_id: Optional[str] = Field(None, description="Project identifier")
    user_id: Optional[str] = Field(None, description="User identifier")
    session_id: Optional[str] = Field(None, description="Session identifier")


# ---------------------------
# Dedicated payload for document comparison requests
# ---------------------------
class CompareDocumentsPayload(BaseModel):
    project_id: str
    user_id: str
    session_id: str
    document_1: dict  # expects {'s3_bucket': str, 's3_key': str}
    document_2: dict  # expects {'s3_bucket': str, 's3_key': str}

# ---------------------------
# Input model for document comparison
# ---------------------------
class DocumentComparisonInput(BaseModel):
    document_1: str
    document_2: str
    extra_instructions: Optional[str] = None

# ---------------------------
# Model for document comparison results
# ---------------------------
class DocumentComparisonResult(BaseModel):
    similarities: Optional[str] = None
    differences: Optional[str] = None
    unique_to_doc1: Optional[str] = None
    unique_to_doc2: Optional[str] = None
    metadata: Optional[dict] = None

# ---------------------------
# Data analysis metadata
# ---------------------------
class Entity(BaseModel):
    """Represents extracted entities from the document"""
    text: str
    type: str
    start_pos: Optional[int] = None
    end_pos: Optional[int] = None


class SectionSummary(BaseModel):
    """Summary for a specific section of the document"""
    section_title: Optional[str] = None
    summary_text: str


class DataAnalysisMetadata(BaseModel):
    """Structured metadata for the analyzed document"""
    title: Optional[str] = None
    author: Optional[str] = None
    date_created: Optional[str] = None
    document_type: Optional[str] = None
    language: Optional[str] = None
    num_pages: Optional[int] = None
    keywords: Optional[List[str]] = None
    entities: Optional[List[Entity]] = None
    summary: Optional[str] = None
    section_summaries: Optional[List[SectionSummary]] = None
    additional_metadata: Optional[Dict[str, str]] = None
