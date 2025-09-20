# UI-related Lambda route handler for document status
import os
import datetime
import boto3
from utils.logger import CustomLogger
from chat_history.chat_history import log_chat_history
from Lambda.llm_lambda_test.lambda_handler import make_response
logger = CustomLogger(__name__)
s3 = boto3.client("s3")
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET")
TEMP_PREFIX = os.getenv("TEMP_DATA_KEY", "project-data/uploads/temp")

def handle_document_status(event, payload):
    """
    Handles /document_status route:
    - Shows status of documents (temp, processing, completed)
    - Returns metadata for processed documents
    """
    try:
        project_name = payload.get("project_name")
        if not project_name:
            return make_response(400, "Missing project_name")
            
        from utils.metadata import MetadataManager
        metadata_manager = MetadataManager()
        
        # Get processed documents from metadata table
        processed_docs = []
        try:
            # This would need to be implemented in MetadataManager
            processed_docs = metadata_manager.list_project_documents(project_name)
        except Exception as e:
            logger.warning(f"Could not fetch processed documents: {e}")
        
        # Get temp files (still being processed)
        temp_files = []
        try:
            temp_prefix = f"{TEMP_PREFIX}/{project_name}/"
            temp_response = s3.list_objects_v2(Bucket=DOCUMENTS_S3_BUCKET, Prefix=temp_prefix)
            for obj in temp_response.get("Contents", []):
                key = obj["Key"]
                filename = key.split("/")[-1]
                temp_files.append({
                    "filename": filename,
                    "key": key,
                    "size": obj.get("Size", 0),
                    "status": "processing",
                    "last_modified": obj.get("LastModified", "")
                })
        except Exception as e:
            logger.warning(f"Could not fetch temp files: {e}")
        
        result = {
            "processed_documents": processed_docs,
            "processing_files": temp_files,
            "total_processed": len(processed_docs),
            "total_processing": len(temp_files)
        }
        
        logger.info(f"✅ Document status retrieved for project: {project_name}")
        return make_response(200, result)
        
    except Exception as e:
        logger.error(f"💥 Error getting document status: {e}", exc_info=True)
        return make_response(500, f"Error getting document status: {str(e)}")
