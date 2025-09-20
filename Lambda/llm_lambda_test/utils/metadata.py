

"""
Simplified Metadata Management Utilities
This module provides a clean, simplified approach to metadata operations:
- MetadataManager: Class with only basic atomic operations
- Complex functions: Accept MetadataManager instance as first parameter
- Legacy wrappers: Simple functions that create manager and delegate
"""
import hashlib
import uuid
import os
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pydantic import BaseModel, Field
from .dynamodb import EnhancedDynamoDBClient
from .logger import logger
from .utils import CustomException

# ---------------------------
# Pydantic Models for Validation
# ---------------------------
class DocumentMetadata(BaseModel):
    document_id: str
    s3_key: str
    project_name: str
    user_id: str
    content_hash: str
    session_id: Optional[str] = None
    ingest_source: Optional[str] = None
    source_path: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: str
    filename: Optional[str] = None
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    status: str = Field(default="pending")
    created_timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

# ---------------------------
# Standalone Helper Functions
# ---------------------------
def generate_document_id(s3_key: str, project_name: str, user_id: str, content_hash: str) -> str:
    """Generate a unique document ID"""
    unique_string = f"{project_name}_{user_id}_{s3_key}_{content_hash}"
    return hashlib.sha256(unique_string.encode()).hexdigest()[:16]

def build_metadata(
    s3_key: str,
    project_name: str,
    user_id: str,
    content_hash: str,
    session_id: Optional[str] = None,
    ingest_source: Optional[str] = None,
    source_path: Optional[str] = None,
    embedding_provider: Optional[str] = None,
    embedding_model: Optional[str] = None,
    filename: Optional[str] = None,
    file_type: Optional[str] = None,
    file_size: Optional[int] = None,
) -> DocumentMetadata:
    """Build and validate a metadata object"""
    document_id = generate_document_id(s3_key, project_name, user_id, content_hash)
    
    return DocumentMetadata(
        document_id=document_id,
        s3_key=s3_key,
        project_name=project_name,
        user_id=user_id,
        content_hash=content_hash,
        session_id=session_id,
        ingest_source=ingest_source,
        source_path=source_path,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        filename=filename,
        file_type=file_type,
        file_size=file_size,
    )

# ---------------------------
# MetadataManager Class - Only Basic Operations
# ---------------------------
class MetadataManager:
    """
    Clean metadata manager with only basic atomic operations.
    Contains only atomic operations that can be used by complex workflow functions.
    """
    def __init__(self, table_name: Optional[str] = None):
        """
        Initialize MetadataManager with DynamoDB client and table name.
        
        Args:
            table_name: Optional table name. If not provided, reads from METADATA_TABLE env var.
        """
        # Get table name from parameter or environment variable
        self.ddb_table = table_name or os.environ.get("METADATA_TABLE")
        
        if not self.ddb_table:
            raise CustomException("DynamoDB table name not found. Provide table_name parameter or set METADATA_TABLE environment variable")
        
        self.dynamo_client = EnhancedDynamoDBClient()
        
        logger.info(f"✅ MetadataManager initialized with table={self.ddb_table}")
    def save_metadata(self, metadata: dict) -> bool:
        """Save metadata to DynamoDB"""
        logger.info(f"💾 Saving metadata for document_id={metadata.get('document_id')} to table={self.ddb_table}")
        
        try:
            success = self.dynamo_client.put_item(self.ddb_table, metadata)
            if success:
                logger.info(f"✅ Metadata saved successfully for document_id={metadata.get('document_id')}")
            else:
                logger.error(f"❌ Failed to save metadata for document_id={metadata.get('document_id')}")
            return success
        except Exception as e:
            logger.error(f"❌ Error saving metadata: {str(e)}", exc_info=True)
            return False
    def get_metadata(self, document_id: str) -> Optional[dict]:
        """Retrieve metadata from DynamoDB by document_id"""
        logger.debug(f"📖 Retrieving metadata for document_id={document_id} from table={self.ddb_table}")
        
        try:
            metadata = self.dynamo_client.get_item(self.ddb_table, {"document_id": document_id})
            if metadata:
                logger.info(f"✅ Retrieved metadata for document_id={document_id}")
            else:
                logger.info(f"ℹ️ No metadata found for document_id={document_id}")
            return metadata
        except Exception as e:
            logger.error(f"❌ Error retrieving metadata: {str(e)}", exc_info=True)
            return None
    def update_metadata_status(self, document_id: str, new_status: str) -> bool:
        """Update the status of a document in DynamoDB"""
        logger.info(f"🔄 Updating status to '{new_status}' for document_id={document_id}")
        
        try:
            success = self.dynamo_client.update_item(
                table_name=self.ddb_table,
                key={"document_id": document_id},
                update_expression="SET #status = :status, updated_timestamp = :timestamp",
                expression_attribute_names={"#status": "status"},
                expression_attribute_values={
                    ":status": new_status,
                    ":timestamp": datetime.utcnow().isoformat()
                }
            )
            
            if success:
                logger.info(f"✅ Status updated to '{new_status}' for document_id={document_id}")
            else:
                logger.error(f"❌ Failed to update status for document_id={document_id}")
            return success
        except Exception as e:
            logger.error(f"❌ Error updating metadata status: {str(e)}", exc_info=True)
            return False
    def delete_metadata(self, document_id: str) -> bool:
        """Delete metadata from DynamoDB"""
        logger.info(f"🗑️ Deleting metadata for document_id={document_id}")
        
        try:
            success = self.dynamo_client.delete_item(self.ddb_table, {"document_id": document_id})
            if success:
                logger.info(f"✅ Metadata deleted successfully for document_id={document_id}")
            else:
                logger.error(f"❌ Failed to delete metadata for document_id={document_id}")
            return success
        except Exception as e:
            logger.error(f"❌ Error deleting metadata: {str(e)}", exc_info=True)
            return False
    def check_metadata_exists(self, content_hash: str, embedding_model: Optional[str] = None) -> Tuple[bool, bool]:
        """Check if metadata exists for the given content_hash and embedding_model"""
        logger.debug(f"🔍 Checking metadata existence for content_hash={content_hash[:12]}...")
        
        try:
            items = self.dynamo_client.query_items(
                table_name=self.ddb_table,
                index_name="content_hash-index",
                key_condition_expression="content_hash = :hash",
                expression_attribute_values={":hash": content_hash}
            )
            any_exists = bool(items)
            exact_exists = False
            if embedding_model:
                exact_exists = any(
                    item.get("embedding_model") == embedding_model for item in items
                )
                logger.debug(f"Checked for exact embedding_model={embedding_model}: {exact_exists}")
            logger.info(
                f"Duplicate check result → any_exists={any_exists}, exact_exists={exact_exists}"
            )
            return any_exists, exact_exists
        except Exception as e:
            logger.error(f"❌ Error querying DynamoDB for content_hash={content_hash}: {str(e)}", exc_info=True)
            raise CustomException(f"Error checking metadata: {str(e)}")
    def find_documents_by_project(self, project_name: str, user_id: str) -> List[dict]:
        """Find all documents for a specific project and user using scan (assuming no project-user GSI)"""
        logger.debug(f"🔍 Finding documents for project={project_name}, user={user_id}")
        
        try:
            documents = self.dynamo_client.scan_items(
                table_name=self.ddb_table,
                filter_expression="project_name = :project AND user_id = :user",
                expression_attribute_values={
                    ":project": project_name,
                    ":user": user_id
                }
            )
            
            logger.info(f"✅ Found {len(documents)} documents for project={project_name}")
            return documents
        except Exception as e:
            logger.error(f"❌ Error finding documents by project: {str(e)}", exc_info=True)
            return []
    def find_documents_by_session(self, session_id: str, user_id: str) -> List[dict]:
        """Find all documents for a specific session and user"""
        logger.debug(f"🔍 Finding documents for session={session_id}, user={user_id}")
        
        try:
            documents = self.dynamo_client.scan_items(
                table_name=self.ddb_table,
                filter_expression="session_id = :session AND user_id = :user",
                expression_attribute_values={
                    ":session": session_id,
                    ":user": user_id
                }
            )
            
            logger.info(f"✅ Found {len(documents)} documents for session={session_id}")
            return documents
        except Exception as e:
            logger.error(f"❌ Error finding documents by session: {str(e)}", exc_info=True)
            return []

# ---------------------------
#  Workflow Functions
# ---------------------------
def create_and_check_metadata(
    manager: MetadataManager,
    s3_key: str,
    project_name: str,
    user_id: str,
    content_hash: str,
    session_id: str,
    ingest_source: str,
    source_path: str,
    embedding_provider: str,
    embedding_model: str,
    filename: str,
    file_type: str,
    file_size: int,
    auto_save: bool = True,
) -> Tuple[dict, dict]:
    """
    Build metadata, check duplicates, optionally save, return both.
    All inputs are now required (no Optional types). Caller must supply defaults if unknown.
    """
    logger.info(f"🚀 Creating + checking metadata for file={filename or s3_key}")
    # Basic validation - aligned with split.py expectations
    required_map = {
        "s3_key": s3_key,
        "project_name": project_name,
        "user_id": user_id,
        "content_hash": content_hash,
        "session_id": session_id,
        "ingest_source": ingest_source,
        "source_path": source_path,
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "filename": filename,
        "file_type": file_type,
    }
    missing = [k for k, v in required_map.items() if v in (None, "")]
    if missing:
        logger.error(f"❌ Missing required metadata fields: {missing}")
        raise CustomException(f"Missing required metadata fields: {missing}")
    # Validate file_size is numeric
    if not isinstance(file_size, (int, float)) or file_size < 0:
        logger.warning(f"Invalid file_size={file_size}, setting to 0")
        file_size = 0
    # Build metadata object using the standalone function
    metadata_obj = build_metadata(
        s3_key, project_name, user_id, content_hash, session_id,
        ingest_source, source_path, embedding_provider, embedding_model, filename, file_type, file_size
    )
    metadata = metadata_obj.dict()
    metadata["content_hash"] = content_hash  # Keep top-level for GSI
    logger.info(
        f"📄 File info → name={filename} type={file_type} size={file_size} bytes"
    )
    logger.debug(f"📦 Metadata prepared → {metadata}")
    # Check for duplicates using MetadataManager basic method
    any_exists, exact_exists = manager.check_metadata_exists(content_hash, embedding_model)
    
    # Auto-save if requested and no exact duplicate exists
    saved = False
    if auto_save and not exact_exists:
        logger.info(f"💾 Auto-saving metadata (no exact duplicate found)")
        saved = manager.save_metadata(metadata)
        if saved:
            # Update status using MetadataManager basic method
            manager.update_metadata_status(metadata["document_id"], "uploaded")
    elif exact_exists:
        logger.info(f"⚠️ Exact duplicate found, skipping auto-save")
    else:
        logger.info(f"📝 Auto-save disabled, metadata prepared but not saved")
    exists = {
        "any_exists": any_exists, 
        "exact_exists": exact_exists,
        "saved": saved
    }
    logger.info(f"✅ Final metadata ready (exists={exists}) for file={filename or s3_key}")
    return metadata, exists

def process_document_metadata(
    manager: MetadataManager,
    s3_key: str,
    project_name: str,
    user_id: str,
    content_hash: str,
    session_id: Optional[str] = None,
    ingest_source: Optional[str] = None,
    source_path: Optional[str] = None,
    embedding_provider: Optional[str] = None,
    embedding_model: Optional[str] = None,
    filename: Optional[str] = None,
    file_type: Optional[str] = None,
    file_size: Optional[int] = None,
    force_save: bool = False
) -> dict:
    """
    Complete document metadata processing workflow.
    Provides defaults for any missing values to satisfy required create_and_check_metadata contract.
    """
    logger.info(f"🔄 Processing document metadata workflow for: {filename or s3_key}")
    # Normalize required fields (align with data_ingestion defaults)
    _session_id = session_id or "unknown_session"
    _ingest_source = ingest_source or "unknown_source"
    _source_path = source_path or "unknown_path"
    _embedding_provider = embedding_provider or "unknown_provider"
    _embedding_model = embedding_model or "unknown_model"
    _filename = filename or os.path.basename(s3_key) or "unknown_file"
    _file_type = file_type or "unknown"
    _file_size = int(file_size) if isinstance(file_size, (int, float)) else 0
    logger.debug(
        f"🧾 Normalized fields → session_id={_session_id} ingest_source={_ingest_source} provider={_embedding_provider} model={_embedding_model} file={_filename} type={_file_type} size={_file_size}"
    )
    try:
        metadata, exists = create_and_check_metadata(
            manager=manager,
            s3_key=s3_key,
            project_name=project_name,
            user_id=user_id,
            content_hash=content_hash,
            session_id=_session_id,
            ingest_source=_ingest_source,
            source_path=_source_path,
            embedding_provider=_embedding_provider,
            embedding_model=_embedding_model,
            filename=_filename,
            file_type=_file_type,
            file_size=_file_size,
            auto_save=False
        )
        document_id = metadata["document_id"]
        actions_taken = {"saved": False, "skipped_reason": None}
        if exists["exact_exists"] and not force_save:
            logger.info(f"⚠️ Exact duplicate found for {_filename}, skipping save")
            actions_taken["skipped_reason"] = "exact_duplicate_exists"
            status = "duplicate_skipped"
        else:
            logger.info(f"💾 Saving metadata for {_filename}")
            save_success = manager.save_metadata(metadata)
            if save_success:
                actions_taken["saved"] = True
                status = "saved"
                logger.info(f"✅ Document metadata saved successfully: {document_id}")
            else:
                status = "error"
                actions_taken["skipped_reason"] = "save_failed"
                logger.error(f"❌ Failed to save metadata for: {_filename}")
        result = {
            "document_id": document_id,
            "metadata": metadata,
            "duplicate_info": exists,
            "actions_taken": actions_taken,
            "status": status
        }
        logger.info(f"✅ Metadata workflow completed for {_filename}: {status}")
        return result
    except Exception as e:
        logger.error(f"💥 Error in metadata workflow for {filename or s3_key}: {str(e)}", exc_info=True)
        return {
            "document_id": None,
            "metadata": None,
            "duplicate_info": {"any_exists": False, "exact_exists": False},
            "actions_taken": {"saved": False, "skipped_reason": "workflow_error"},
            "status": "error"
        }

def get_project_summary(manager: MetadataManager, project_name: str, user_id: str) -> dict:
    """
    Get a comprehensive summary of all documents in a project.
    Uses MetadataManager basic operations.
    """
    logger.info(f"📊 Getting project summary for project={project_name}, user={user_id}")
    
    try:
        # Use MetadataManager basic method to find documents
        documents = manager.find_documents_by_project(project_name, user_id)
        
        if not documents:
            return {
                "project_name": project_name,
                "user_id": user_id,
                "total_documents": 0,
                "status_breakdown": {},
                "file_types": {},
                "total_size": 0,
                "documents": []
            }
        
        # Analyze the documents
        status_breakdown = {}
        file_types = {}
        total_size = 0
        
        for doc in documents:
            # Count by status
            status = doc.get("status", "unknown")
            status_breakdown[status] = status_breakdown.get(status, 0) + 1
            
            # Count by file type
            file_type = doc.get("file_type", "unknown")
            file_types[file_type] = file_types.get(file_type, 0) + 1
            
            # Sum file sizes
            size = doc.get("file_size", 0)
            if isinstance(size, (int, float)):
                total_size += size
        
        summary = {
            "project_name": project_name,
            "user_id": user_id,
            "total_documents": len(documents),
            "status_breakdown": status_breakdown,
            "file_types": file_types,
            "total_size": total_size,
            "documents": documents
        }
        
        logger.info(f"✅ Project summary generated: {len(documents)} documents, {total_size} bytes total")
        return summary
        
    except Exception as e:
        logger.error(f"💥 Error getting project summary: {str(e)}", exc_info=True)
        return {
            "project_name": project_name,
            "user_id": user_id,
            "total_documents": 0,
            "status_breakdown": {},
            "file_types": {},
            "total_size": 0,
            "documents": [],
            "error": str(e)
        }


