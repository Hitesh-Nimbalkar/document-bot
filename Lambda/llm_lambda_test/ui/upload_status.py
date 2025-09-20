import json
import boto3
import os
from datetime import datetime
from botocore.exceptions import ClientError
# Import shared utilities
try:
    from utils.logger import CustomLogger
except ImportError:
    import logging
    CustomLogger = logging.getLogger
logger = CustomLogger(__name__)
# AWS clients
s3_client = boto3.client('s3')
# Environment variables
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET", "document-bot-bucket")
def handle_upload_status(event, payload):
    """
    Handle upload status tracking
    
    Expected payload:
    {
        "project_name": "string",
        "upload_id": "string" (optional),
        "file_name": "string" (optional)
    }
    """
    try:
        logger.info("📊 Starting upload status check")
        
        project_name = payload.get("project_name")
        if not project_name:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "project_name is required",
                    "success": False
                })
            }
        
        upload_id = payload.get("upload_id")
        file_name = payload.get("file_name")
        
        if upload_id:
            # Check specific upload by ID
            return check_upload_by_id(project_name, upload_id)
        elif file_name:
            # Check upload by file name
            return check_upload_by_filename(project_name, file_name)
        else:
            # Get all uploads for project
            return get_project_upload_status(project_name)
            
    except Exception as e:
        logger.error(f"Error in upload_status: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "success": False
            })
        }
def check_upload_by_id(project_name, upload_id):
    """Check upload status by upload ID"""
    try:
        # List objects with upload_id in the key
        response = s3_client.list_objects_v2(
            Bucket=DOCUMENTS_S3_BUCKET,
            Prefix=f"project-data/{project_name}/uploads/",
        )
        
        matching_files = []
        for obj in response.get('Contents', []):
            if upload_id in obj['Key']:
                # Get object metadata
                head_response = s3_client.head_object(
                    Bucket=DOCUMENTS_S3_BUCKET,
                    Key=obj['Key']
                )
                
                file_status = {
                    "file_key": obj['Key'],
                    "file_name": obj['Key'].split('/')[-1],
                    "size": obj['Size'],
                    "last_modified": obj['LastModified'].isoformat(),
                    "upload_status": "completed",
                    "metadata": head_response.get('Metadata', {}),
                    "content_type": head_response.get('ContentType', 'unknown')
                }
                matching_files.append(file_status)
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "upload_id": upload_id,
                "project_name": project_name,
                "files": matching_files,
                "total_files": len(matching_files)
            }, default=str)
        }
        
    except ClientError as e:
        logger.error(f"S3 error in check_upload_by_id: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Failed to check upload status",
                "success": False
            })
        }
def check_upload_by_filename(project_name, file_name):
    """Check upload status by filename"""
    try:
        # Search for files with matching filename
        response = s3_client.list_objects_v2(
            Bucket=DOCUMENTS_S3_BUCKET,
            Prefix=f"project-data/{project_name}/",
        )
        
        matching_files = []
        for obj in response.get('Contents', []):
            if file_name in obj['Key']:
                head_response = s3_client.head_object(
                    Bucket=DOCUMENTS_S3_BUCKET,
                    Key=obj['Key']
                )
                
                file_status = {
                    "file_key": obj['Key'],
                    "file_name": obj['Key'].split('/')[-1],
                    "size": obj['Size'],
                    "last_modified": obj['LastModified'].isoformat(),
                    "upload_status": "completed",
                    "metadata": head_response.get('Metadata', {}),
                    "ingestion_status": "pending"  # Would need to check actual ingestion status
                }
                matching_files.append(file_status)
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "search_filename": file_name,
                "project_name": project_name,
                "files": matching_files,
                "total_matches": len(matching_files)
            }, default=str)
        }
        
    except Exception as e:
        logger.error(f"Error in check_upload_by_filename: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "success": False
            })
        }
def get_project_upload_status(project_name):
    """Get upload status for entire project"""
    try:
        # Get all uploads in the project
        paginator = s3_client.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(
            Bucket=DOCUMENTS_S3_BUCKET,
            Prefix=f"project-data/{project_name}/uploads/"
        )
        
        recent_uploads = []
        total_size = 0
        
        for page in page_iterator:
            for obj in page.get('Contents', []):
                try:
                    head_response = s3_client.head_object(
                        Bucket=DOCUMENTS_S3_BUCKET,
                        Key=obj['Key']
                    )
                    
                    upload_info = {
                        "file_key": obj['Key'],
                        "file_name": obj['Key'].split('/')[-1],
                        "size": obj['Size'],
                        "size_mb": round(obj['Size'] / (1024 * 1024), 2),
                        "last_modified": obj['LastModified'].isoformat(),
                        "upload_status": "completed",
                        "metadata": head_response.get('Metadata', {}),
                        "content_type": head_response.get('ContentType', 'unknown')
                    }
                    
                    recent_uploads.append(upload_info)
                    total_size += obj['Size']
                    
                except ClientError:
                    # Skip files we can't access
                    continue
        
        # Sort by last modified (newest first)
        recent_uploads.sort(key=lambda x: x['last_modified'], reverse=True)
        
        # Limit to most recent 50
        recent_uploads = recent_uploads[:50]
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "project_name": project_name,
                "recent_uploads": recent_uploads,
                "summary": {
                    "total_uploads": len(recent_uploads),
                    "total_size_bytes": total_size,
                    "total_size_mb": round(total_size / (1024 * 1024), 2),
                    "last_upload": recent_uploads[0]['last_modified'] if recent_uploads else None
                }
            }, default=str)
        }
        
    except Exception as e:
        logger.error(f"Error in get_project_upload_status: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "success": False
            })
        }