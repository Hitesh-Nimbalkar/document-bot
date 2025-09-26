



from typing import List, Optional, Dict, Any, Union
from pydantic import BaseModel, Field, validator
from enum import Enum
import datetime
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
# ---------------------------
# RAG SIMPLE MODELS - Simple Input/Response
# ---------------------------
class RAGSimpleInput(BaseModel):
    """Simple input model for RAG queries"""
    query: str
    project_name: str
    llm_model: str
    embedding_model: str
    bedrock_region: str = "ap-south-1"  # Fixed region
    temperature: float
    max_tokens: int
    top_k: int = 3  # Fixed value for simple RAG
    session_id: str  # Session ID from login - REQUIRED
class RAGSimpleResponse(BaseModel):
    """Enhanced response model for RAG queries with monitoring fields"""
    # Core response
    answer: str
    source_documents: list = []
    
    # Request tracking
    query: str
    project_name: str
    timestamp: str
    
    # Model configuration used
    models_used: dict = {}
    
    # Performance metrics
    processing_time_seconds: Optional[float] = None
    total_documents_retrieved: int = 0
    
    # Response metadata
    success: bool = True
    error: Optional[str] = None
    pipeline_version: str = "simple_v1"
    
    # Parameters used for monitoring
    parameters_used: dict = {}




class SimpleRAGRequest(BaseModel):
    # Required fields only
    project_name: str = Field(..., min_length=1, description="Project name")  # Changed back to project_name
    user_id: str = Field(..., min_length=1, description="User identifier")
    query: str = Field(..., min_length=1, max_length=2000, description="User query")
    
    # Optional fields
    session_id: Optional[str] = Field(None, description="Session identifier")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="All other configuration and UI metadata")
    
    @validator("query")
    def validate_query(cls, v):
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace only")
        return v.strip()
    class Config:
        schema_extra = {
            "example": {
                "project_name": "my_project",  # Changed back to project_name
                "user_id": "user123", 
                "session_id": "session456",
                "query": "How do I reset my device?",
                "metadata": {
                    "user_role": "customer",
                    "locale": "en-US",
                    "channel": "web",
                    "query_type": "faq",
                    "urgency": "low",
                    "llm_model": "anthropic.claude-3-opus-20240229",
                    "embedding_model": "amazon.titan-embed-text-v2:0",
                    "bedrock_region": "us-east-1",
                    "top_k": 3,
                    "max_tokens": 1024,
                    "temperature": 0.7
                }
            }
        }
