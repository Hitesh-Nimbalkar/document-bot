
# Model for analyze_document action
from pydantic import BaseModel, Field
class AnalyzeDocumentPayload(BaseModel):
    s3_bucket: str = Field(..., description="S3 bucket where the document is stored")
    s3_key: str = Field(..., description="S3 key (path) to the document")
    project_id: str = Field(None, description="Project identifier")
    user_id: str = Field(None, description="User identifier")
    session_id: str = Field(None, description="Session identifier")
# Pydantic model for DynamoDB metadata table
class MetadataModel(BaseModel):
    s3_key: str
    project_name: str
    user_id: str
    upload_timestamp: str
    content_hash: str  # or use the value of CONTENT_HASH_KEY if dynamic
    session_id: Optional[str] = None
    ingest_source: Optional[str] = None
    source_path: Optional[str] = None
    embedding_model: Optional[str] = None  # Name of the embedding model used
    # Add any other fields as needed for your use case
# Dedicated payload for document comparison requests
class CompareDocumentsPayload(BaseModel):
    project_id: str
    user_id: str
    session_id: str
    document_1: dict  # expects {'s3_bucket': str, 's3_key': str}
    document_2: dict  # expects {'s3_bucket': str, 's3_key': str}
# Input model for document comparison
class DocumentComparisonInput(BaseModel):
    document_1: str
    document_2: str
    # Optionally add: extra_instructions: Optional[str] = None
# Model for document comparison results
class DocumentComparisonResult(BaseModel):
    similarities: Optional[str]
    differences: Optional[str]
    unique_to_doc1: Optional[str]
    unique_to_doc2: Optional[str]
    metadata: Optional[dict]
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class IngestionPayload(BaseModel):
    session_id: str
    s3_bucket: str
    s3_key: str
    project_name: str
    user_id: str
    ingest_source: Optional[str] = None  # 'user_upload' or 'indexing_pipeline'
    source_path: Optional[str] = None    # For pipeline ingestions, original source location
    embedding_model: Optional[str] = None  # Name of the embedding model used
class DataAnalysisMetadata(BaseModel):
    title: Optional[str]
    author: Optional[str]
    date: Optional[str]
    summary: Optional[str]
    keywords: Optional[List[str]]
    document_type: Optional[str]  # Added to store detected document type
    ingest_source: Optional[str] = None  # 'user_upload' or 'indexing_pipeline'
    source_path: Optional[str] = None    # For pipeline ingestions, original source location
    embedding_model: Optional[str] = None  # Name of the embedding model used
    # Add more fields as needed for your use case
# Pydantic model for a single chat message (LangChain compatible)
class ChatMessage(BaseModel):
    message_id: str
    timestamp: str
    role: str  # 'user', 'assistant', or 'system' (LangChain convention)
    content: str
    reply_to: Optional[str] = None  # message_id of the message this is replying to
    metadata: Optional[Dict[str, Any]] = None
    # For backward compatibility, allow 'sender' as an alias for 'role'
    class Config:
        fields = {'role': 'sender'}
# Pydantic model for chat history for a session (with project_id, user_id, session_id)
class ChatHistoryModel(BaseModel):
    project_id: str
    user_id: str
    session_id: str
    messages: List[ChatMessage] = Field(default_factory=list)
# Pydantic model for ingestion response
class IngestionResponse(BaseModel):
    statusCode: int
    body: str
    s3_bucket: Optional[str] = None
    s3_key: Optional[str] = None
    ingest_source: Optional[str] = None  # 'user_upload' or 'indexing_pipeline'
    source_path: Optional[str] = None    # For pipeline ingestions, original source location
    embedding_model: Optional[str] = None  # Name of the embedding model used
