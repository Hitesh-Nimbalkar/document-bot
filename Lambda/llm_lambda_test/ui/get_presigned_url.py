# =====================================================
# UI-related Lambda route handler for Upload button
# =====================================================
import json
import os
import boto3
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from botocore.exceptions import ClientError

# Import shared utilities
try:
    from utils.logger import CustomLogger
except ImportError:
    import logging
    CustomLogger = logging.getLogger

# =====================================================
# MODELS
# =====================================================
class GetPresignedUrlRequest(BaseModel):
    project_name: str = Field(..., min_length=1, max_length=100)
    file_name: str = Field(..., min_length=1, max_length=255)
    file_content: Optional[str] = None  # base64-encoded file content
    content_type: Optional[str] = None
    session_id: str = Field(..., min_length=1)
    user_id: str = Field(..., min_length=1, max_length=100)

    # Optional embedding info
    embedding_provider: str
    embedding_model: str

class GetPresignedUrlResponse(BaseModel):
    """
    OUTPUT MODEL – shaped like IngestionPayload
    So the Upload button output can be used directly by the Ingestion button
    """
    session_id: str
    project_name: str
    user_id: str
    doc_loc: str
    doc_locs: List[str]
    ingest_source: str
    source_path: str
    embedding_provider: str
    embedding_model: str


# =====================================================
# CONFIG
# =====================================================
logger = CustomLogger(__name__)
s3_client = boto3.client("s3")
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET", "document-bot-bucket")


# =====================================================
# HANDLER
# =====================================================
def handle_get_presigned_url(event, payload):
    """
    Upload file to S3 and return GetPresignedUrlResponse.
    This is triggered by the Upload button.
    """
    try:
        logger.info("📤 Upload handler started")

        # Validate payload
        try:
            request_data = GetPresignedUrlRequest(**payload)
        except Exception as e:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": f"Invalid payload: {str(e)}", "success": False})
            }

        project_name = request_data.project_name
        file_name = request_data.file_name
        content_type = request_data.content_type
        session_id = request_data.session_id
        user_id = request_data.user_id
        file_content = request_data.file_content

        logger.info(f"🔐 Upload request - User={user_id}, Project={project_name}, File={file_name}")

        # Sanitize file name
        safe_file_name = file_name.replace(" ", "_").replace("/", "_")

        # S3 key
        s3_key = f"project_data/uploads/temp/{project_name}/{safe_file_name}"

        # Content type detection
        if not content_type:
            ext = safe_file_name.lower().split(".")[-1] if "." in safe_file_name else ""
            content_type_map = {
                "pdf": "application/pdf",
                "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "doc": "application/msword",
                "txt": "text/plain",
                "csv": "text/csv",
                "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            }
            content_type = content_type_map.get(ext, "application/octet-stream")

        # Direct upload to S3
        if not file_content:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "file_content (base64) is required for upload", "success": False})
            }

        import base64
        file_bytes = base64.b64decode(file_content)

        s3_client.put_object(
            Bucket=DOCUMENTS_S3_BUCKET,
            Key=s3_key,
            Body=file_bytes,
            ContentType=content_type,
            Metadata={
                "project": project_name,
                "original_name": file_name,
                "user_id": user_id,
                "session_id": session_id,
                "upload_timestamp": datetime.utcnow().isoformat()
            }
        )

        logger.info(f"✅ Uploaded to S3: s3://{DOCUMENTS_S3_BUCKET}/{s3_key}")

        # Build ingestion-style response, but wrapped as GetPresignedUrlResponse
        response = GetPresignedUrlResponse(
            session_id=session_id,
            project_name=project_name,
            user_id=user_id,
            doc_loc=f"{safe_file_name}",
            doc_locs=[safe_file_name],
            ingest_source="ui_upload",
            source_path=s3_key,
            embedding_provider=request_data.embedding_provider,
            embedding_model=request_data.embedding_model,
        )

        return {
            "statusCode": 200,
            "body": json.dumps(response.dict())
        }

    except ClientError as e:
        logger.error(f"S3 error: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"success": False, "error": str(e)})
        }
    except Exception as e:
        logger.error(f"Error in upload handler: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"success": False, "error": str(e)})
        }
