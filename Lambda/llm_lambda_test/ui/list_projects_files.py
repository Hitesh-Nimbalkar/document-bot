# UI-related Lambda route handlers for llm_lambda_test
import os
import json
import boto3
from datetime import datetime
from botocore.exceptions import ClientError
# Import shared utilities
try:
    from utils.logger import CustomLogger
except ImportError:
    import logging
    CustomLogger = logging.getLogger
from Lambda.llm_lambda_test.lambda_handler import make_response
logger = CustomLogger(__name__)
s3_client = boto3.client('s3')
# Environment variables
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET", "document-bot-bucket")
TEMP_PREFIX = os.getenv("TEMP_DATA_KEY", "project-data/uploads/temp")

def handle_list_project_files(event, payload):
    """
    Handle listing files for a specific project
    Expected payload:
    {
        "project_name": "string",
        "page": int (optional),
        "limit": int (optional),
        "file_type": "string" (optional)
    }
    """
    try:
        logger.info("📁 Starting list project files request")
        # Extract parameters
        project_name = payload.get("project_name")
        if not project_name:
            return make_response(400, "project_name is required")
        page = payload.get("page", 1)
        limit = payload.get("limit", 50)
        file_type = payload.get("file_type")
        # S3 prefix for the project
        prefix = f"project-data/{project_name}/"
        # List objects from S3
        paginator = s3_client.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(
            Bucket=DOCUMENTS_S3_BUCKET,
            Prefix=prefix,
            MaxItems=limit,
            PageSize=100
        )
        files = []
        total_size = 0
        for page_data in page_iterator:
            if 'Contents' in page_data:
                for obj in page_data['Contents']:
                    file_key = obj['Key']
                    file_name = file_key.replace(prefix, '')
                    # Skip empty folder markers
                    if not file_name:
                        continue
                    # Filter by file type if specified
                    if file_type and not file_name.lower().endswith(f".{file_type.lower()}"):
                        continue
                    file_info = {
                        "file_name": file_name,
                        "file_key": file_key,
                        "size": obj['Size'],
                        "last_modified": obj['LastModified'].isoformat(),
                        "file_type": file_name.split('.')[-1].lower() if '.' in file_name else 'unknown',
                        "url": f"s3://{DOCUMENTS_S3_BUCKET}/{file_key}"
                    }
                    files.append(file_info)
                    total_size += obj['Size']
        # Sort files by last modified (newest first)
        files.sort(key=lambda x: x['last_modified'], reverse=True)
        # Apply pagination
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_files = files[start_idx:end_idx]
        response = {
            "success": True,
            "project_name": project_name,
            "files": paginated_files,
            "pagination": {
                "current_page": page,
                "total_files": len(files),
                "files_per_page": limit,
                "total_pages": (len(files) + limit - 1) // limit
            },
            "summary": {
                "total_files": len(files),
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2)
            }
        }
        logger.info(f"✅ Listed {len(paginated_files)} files for project {project_name}")
        return make_response(200, response)
    except ClientError as e:
        logger.error(f"S3 error in list_project_files: {e}")
        return make_response(500, {
            "error": "Failed to access S3 bucket",
            "success": False,
            "details": str(e)
        })
    except Exception as e:
        logger.error(f"Error in list_project_files: {e}", exc_info=True)
        return make_response(500, {
            "error": str(e),
            "success": False
        })

