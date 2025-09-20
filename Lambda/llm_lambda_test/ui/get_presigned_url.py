# UI-related Lambda route handler for presigned URL
import json
import os
import boto3
import uuid
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel, Field
from botocore.exceptions import ClientError
# Import shared utilities
try:
    from utils.logger import CustomLogger
except ImportError:
    import logging
    CustomLogger = logging.getLogger
# Pydantic Models for Request/Response validation
class GetPresignedUrlRequest(BaseModel):
    """
    INPUT MODEL - Request payload from UI to get_presigned_url endpoint
    
    FRONTEND INTEGRATION:
    - JavaScript in ingest/ingest.html sends payload matching this model
    """
    project_name: str = Field(..., description="Name of the project", min_length=1, max_length=100)
    file_name: str = Field(..., description="Original filename", min_length=1, max_length=255)
    content_type: Optional[str] = Field(None, description="MIME type of the file (optional, will be auto-detected)")
    expiration: Optional[int] = Field(3600, description="URL expiration time in seconds", ge=60, le=86400)
    
    # Session and user context (added for authentication/tracking)
    session_id: str = Field(..., description="Session ID from user login", min_length=1)
    user_id: str = Field(..., description="Username/User ID from session", min_length=1, max_length=100)
class GetPresignedUrlResponse(BaseModel):
    """
    OUTPUT MODEL - Response payload from get_presigned_url endpoint to UI
    
    FRONTEND INTEGRATION:
    - JavaScript receives this exact structure from the API
    """
    success: bool = Field(..., description="Whether the request was successful")
    upload_url: Optional[str] = Field(None, description="S3 presigned POST URL")
    fields: Optional[dict] = Field(None, description="Form fields required for the POST request")
    s3_key: Optional[str] = Field(None, description="S3 object key for the uploaded file")
    get_url: Optional[str] = Field(None, description="Presigned GET URL for accessing the file")
    expiration: Optional[int] = Field(None, description="Expiration time in seconds")
    expires_at: Optional[str] = Field(None, description="ISO timestamp when the URL expires")
    metadata: Optional[dict] = Field(None, description="Additional file metadata")
    error: Optional[str] = Field(None, description="Error message if success is False")
logger = CustomLogger(__name__)
s3_client = boto3.client('s3')
# Environment variables
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET", "document-bot-bucket")
PRESIGNED_URL_EXPIRATION = int(os.environ.get("PRESIGNED_URL_EXPIRATION", "3600"))  # 1 hour

def handle_get_presigned_url(event, payload):
    """
    Generate presigned URL for file upload
    
    Payload validation using GetPresignedUrlRequest model:
    - project_name: Required string (1-100 chars)
    - file_name: Required string (1-255 chars) 
    - content_type: Optional string (auto-detected if not provided)
    - expiration: Optional int (60-86400 seconds, default 3600)
    
    Returns GetPresignedUrlResponse model with upload_url, fields, etc.
    """
    try:
        logger.info("🔗 Starting presigned URL generation")
        # Validate payload using Pydantic model
        try:
            request_data = GetPresignedUrlRequest(**payload)
        except Exception as e:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": f"Invalid request payload: {str(e)}",
                    "success": False
                })
            }
        # Extract validated parameters
        project_name = request_data.project_name
        file_name = request_data.file_name
        content_type = request_data.content_type
        expiration = request_data.expiration
        session_id = request_data.session_id
        user_id = request_data.user_id
        logger.info(f"🔐 Processing upload request - User: {user_id}, Session: {session_id}, Project: {project_name}")
        # Sanitize file name
        safe_file_name = file_name.replace(" ", "_").replace("/", "_")
        # Generate S3 key for temporary location (ingestion pipeline expects this)
        # This matches what data_ingestion.py expects: {TEMP_DATA_KEY}/{project_name}/{filename}
        s3_key = f"project-data/{project_name}/uploads/temp/{safe_file_name}"
        # Content type detection
        if not content_type:
            # Basic content type detection based on file extension
            ext = safe_file_name.lower().split('.')[-1] if '.' in safe_file_name else ''
            content_type_map = {
                'pdf': 'application/pdf',
                'docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
                'doc': 'application/msword',
                'txt': 'text/plain',
                'csv': 'text/csv',
                'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            }
            content_type = content_type_map.get(ext, 'application/octet-stream')
        # Generate presigned POST URL
        presigned_post = s3_client.generate_presigned_post(
            Bucket=DOCUMENTS_S3_BUCKET,
            Key=s3_key,
            Fields={
                'Content-Type': content_type,
                'x-amz-meta-project': project_name,
                'x-amz-meta-original-name': file_name,
                'x-amz-meta-upload-timestamp': datetime.utcnow().isoformat(),
                'x-amz-meta-user-id': user_id,
                'x-amz-meta-session-id': session_id
            },
            Conditions=[
                {'Content-Type': content_type},
                ['content-length-range', 1, 26214400],  # 1 byte to 25MB
                {'x-amz-meta-project': project_name},
                {'x-amz-meta-user-id': user_id}
            ],
            ExpiresIn=expiration
        )
        # Also generate presigned GET URL for future access
        get_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': DOCUMENTS_S3_BUCKET, 'Key': s3_key},
            ExpiresIn=expiration
        )
        # Create validated response using Pydantic model
        response_data = GetPresignedUrlResponse(
            success=True,
            upload_url=presigned_post['url'],
            fields=presigned_post['fields'],
            s3_key=s3_key,
            get_url=get_url,
            expiration=expiration,
            expires_at=(datetime.utcnow() + timedelta(seconds=expiration)).isoformat(),
            metadata={
                "project_name": project_name,
                "original_file_name": file_name,
                "content_type": content_type,
                "max_file_size_mb": 25,
                "user_id": user_id,
                "session_id": session_id
            }
        )
        logger.info(f"✅ Generated presigned URL for {project_name}/{file_name}")
        return {
            "statusCode": 200,
            "body": json.dumps(response_data.dict())
        }
    except ClientError as e:
        logger.error(f"S3 error in get_presigned_url: {e}")
        error_response = GetPresignedUrlResponse(
            success=False,
            error=f"Failed to generate presigned URL: {str(e)}"
        )
        return {
            "statusCode": 500,
            "body": json.dumps(error_response.dict())
        }
    except Exception as e:
        logger.error(f"Error in get_presigned_url: {e}", exc_info=True)
        error_response = GetPresignedUrlResponse(
            success=False,
            error=str(e)
        )
        return {
            "statusCode": 500,
            "body": json.dumps(error_response.dict())
        }

