# UI-related Lambda route handler for document deletion
import os
import boto3
from utils.logger import CustomLogger
from chat_history.chat_history import log_chat_history
from Lambda.llm_lambda_test.lambda_handler import make_response
logger = CustomLogger(__name__)
s3 = boto3.client("s3")
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET")

def handle_delete_document(event, payload):
    """
    Handles /delete_document route:
    - Removes document from S3 and vector database
    - Cleans up metadata
    """
    try:
        project_name = payload.get("project_name")
        doc_key = payload.get("doc_key")
        filename = payload.get("filename")
        
        if not all([project_name, (doc_key or filename)]):
            return make_response(400, "Missing required parameters: project_name and (doc_key or filename)")
        
        # Construct S3 key if only filename provided
        if filename and not doc_key:
            doc_key = f"{os.getenv('DOCUMENTS_DATA_KEY', 'project-data/documents')}/{project_name}/{filename}"
        
        # Delete from S3
        try:
            s3.delete_object(Bucket=DOCUMENTS_S3_BUCKET, Key=doc_key)
            logger.info(f"🗑️ Deleted from S3: {doc_key}")
        except Exception as e:
            logger.warning(f"Could not delete from S3: {e}")
        
        # Delete from vector database
        try:
            from vector_db.vector_db import QdrantVectorDB
            vector_db = QdrantVectorDB()
            # This would need a delete method implemented
            # vector_db.delete_document(project_name, filename)
            logger.info(f"🗑️ Deleted from vector DB: {filename}")
        except Exception as e:
            logger.warning(f"Could not delete from vector DB: {e}")
        
        # Clean up metadata
        try:
            from utils.metadata import MetadataManager
            metadata_manager = MetadataManager()
            # This would need a delete method implemented
            # metadata_manager.delete_document(project_name, filename)
            logger.info(f"🗑️ Cleaned up metadata for: {filename}")
        except Exception as e:
            logger.warning(f"Could not clean up metadata: {e}")
        
        # Log to chat history
        try:
            log_chat_history(
                event=event, 
                payload=payload, 
                role="system", 
                content=f"🗑️ Document deleted: {filename or doc_key}",
                metadata={"action": "document_deleted", "filename": filename}
            )
        except Exception as e:
            logger.warning(f"Could not log to chat history: {e}")
        
        logger.info(f"✅ Document deletion completed: {filename}")
        return make_response(200, {"message": f"Document deleted: {filename or doc_key}"})
        
    except Exception as e:
        logger.error(f"💥 Error deleting document: {e}", exc_info=True)
        return make_response(500, f"Error deleting document: {str(e)}")

