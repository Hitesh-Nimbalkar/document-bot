
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
dynamodb = boto3.resource('dynamodb')
# Environment variables
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET", "document-bot-bucket")
PROJECTS_TABLE = os.environ.get("PROJECTS_TABLE", "document-bot-projects")
# Initialize DynamoDB table
try:
    projects_table = dynamodb.Table(PROJECTS_TABLE)
except Exception as e:
    logger.warning(f"Could not connect to DynamoDB table {PROJECTS_TABLE}: {e}")
    projects_table = None
def handle_project_management(event, payload):
    """
    Handle project management operations
    
    Expected payload:
    {
        "action": "create|list|update|delete|get",
        "project_name": "string" (for specific operations),
        "description": "string" (for create/update),
        "project_type": "string" (optional),
        "metadata": {} (optional)
    }
    """
    try:
        action = payload.get("action")
        if not action:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": "action is required (create, list, update, delete, get)",
                    "success": False
                })
            }
        
        logger.info(f"🏗️ Processing project management action: {action}")
        
        if action == "create":
            return create_project(payload)
        elif action == "list":
            return list_projects(payload)
        elif action == "get":
            return get_project(payload)
        elif action == "update":
            return update_project(payload)
        elif action == "delete":
            return delete_project(payload)
        else:
            return {
                "statusCode": 400,
                "body": json.dumps({
                    "error": f"Unknown action: {action}",
                    "success": False,
                    "available_actions": ["create", "list", "get", "update", "delete"]
                })
            }
            
    except Exception as e:
        logger.error(f"Error in project_management: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": str(e),
                "success": False
            })
        }
def create_project(payload):
    """Create a new project"""
    project_name = payload.get("project_name")
    if not project_name:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "project_name is required for create action",
                "success": False
            })
        }
    
    # Sanitize project name
    safe_project_name = project_name.replace(" ", "_").lower()
    
    project_data = {
        "project_id": safe_project_name,
        "project_name": project_name,
        "description": payload.get("description", ""),
        "project_type": payload.get("project_type", "general"),
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
        "status": "active",
        "document_count": 0,
        "metadata": payload.get("metadata", {})
    }
    
    try:
        # Create S3 folder structure
        s3_prefix = f"project-data/{safe_project_name}/"
        s3_client.put_object(
            Bucket=DOCUMENTS_S3_BUCKET,
            Key=f"{s3_prefix}.project_info",
            Body=json.dumps(project_data),
            ContentType='application/json'
        )
        
        # Store in DynamoDB if available
        if projects_table:
            projects_table.put_item(
                Item=project_data,
                ConditionExpression='attribute_not_exists(project_id)'
            )
        
        logger.info(f"✅ Created project: {project_name}")
        
        return {
            "statusCode": 201,
            "body": json.dumps({
                "success": True,
                "message": "Project created successfully",
                "project": project_data
            })
        }
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'ConditionalCheckFailedException':
            return {
                "statusCode": 409,
                "body": json.dumps({
                    "error": "Project already exists",
                    "success": False
                })
            }
        raise e
def list_projects(payload):
    """List all projects"""
    try:
        projects = []
        
        if projects_table:
            # Get from DynamoDB
            response = projects_table.scan()
            projects = response.get('Items', [])
        else:
            # Fallback: Get from S3
            paginator = s3_client.get_paginator('list_objects_v2')
            page_iterator = paginator.paginate(
                Bucket=DOCUMENTS_S3_BUCKET,
                Prefix="project-data/",
                Delimiter="/"
            )
            
            for page in page_iterator:
                for prefix_info in page.get('CommonPrefixes', []):
                    project_folder = prefix_info['Prefix']
                    project_id = project_folder.replace('project-data/', '').rstrip('/')
                    
                    # Try to get project info
                    try:
                        obj = s3_client.get_object(
                            Bucket=DOCUMENTS_S3_BUCKET,
                            Key=f"{project_folder}.project_info"
                        )
                        project_data = json.loads(obj['Body'].read())
                        projects.append(project_data)
                    except:
                        # Create basic project info
                        projects.append({
                            "project_id": project_id,
                            "project_name": project_id.replace("_", " ").title(),
                            "created_at": "unknown",
                            "status": "active"
                        })
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "projects": projects,
                "total_count": len(projects)
            }, default=str)
        }
        
    except Exception as e:
        logger.error(f"Error listing projects: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Failed to list projects",
                "success": False
            })
        }
def get_project(payload):
    """Get specific project details"""
    project_name = payload.get("project_name")
    if not project_name:
        return {
            "statusCode": 400,
            "body": json.dumps({
                "error": "project_name is required",
                "success": False
            })
        }
    
    safe_project_name = project_name.replace(" ", "_").lower()
    
    try:
        if projects_table:
            response = projects_table.get_item(Key={'project_id': safe_project_name})
            if 'Item' not in response:
                return {
                    "statusCode": 404,
                    "body": json.dumps({
                        "error": "Project not found",
                        "success": False
                    })
                }
            project_data = response['Item']
        else:
            # Get from S3
            obj = s3_client.get_object(
                Bucket=DOCUMENTS_S3_BUCKET,
                Key=f"project-data/{safe_project_name}/.project_info"
            )
            project_data = json.loads(obj['Body'].read())
        
        # Get document count
        file_count = get_project_file_count(safe_project_name)
        project_data['document_count'] = file_count
        
        return {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "project": project_data
            }, default=str)
        }
        
    except ClientError as e:
        if e.response['Error']['Code'] == 'NoSuchKey':
            return {
                "statusCode": 404,
                "body": json.dumps({
                    "error": "Project not found",
                    "success": False
                })
            }
        raise e
def get_project_file_count(project_id):
    """Get count of files in project"""
    try:
        paginator = s3_client.get_paginator('list_objects_v2')
        page_iterator = paginator.paginate(
            Bucket=DOCUMENTS_S3_BUCKET,
            Prefix=f"project-data/{project_id}/"
        )
        
        count = 0
        for page in page_iterator:
            count += len(page.get('Contents', []))
        
        return max(0, count - 1)  # Subtract 1 for .project_info file
    except:
        return 0
def update_project(payload):
    """Update project (placeholder for now)"""
    return {
        "statusCode": 501,
        "body": json.dumps({
            "error": "Update project not yet implemented",
            "success": False
        })
    }
def delete_project(payload):
    """Delete project (placeholder for now)"""
    return {
        "statusCode": 501,
        "body": json.dumps({
            "error": "Delete project not yet implemented", 
            "success": False
        })
    }

