import json
import boto3
from utils.logger import CustomLogger

# ======================================================
# Logger / AWS Clients
# ======================================================
logger = CustomLogger(__name__)
s3 = boto3.client("s3")


# ======================================================
# Handler
# ======================================================
def handle_export_data(event, payload):
    """
    Handle data export requests.
    Supports: export_project, export_documents, export_analysis.
    """
    try:
        export_type = payload.get("export_type")
        project_name = payload.get("project_name")
        export_format = payload.get("export_format", "json")

        if not all([export_type, project_name]):
            return {
                "statusCode": 400,
                "body": json.dumps(
                    {"error": "export_type and project_name are required"}
                ),
            }

        if export_type == "project":
            return export_project_data(project_name, export_format, payload)
        elif export_type == "documents":
            return export_documents(project_name, export_format, payload)
        elif export_type == "analysis":
            return export_analysis_results(project_name, export_format, payload)
        else:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Invalid export_type"}),
            }

    except Exception as e:
        logger.error(f"Error in data export: {e}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


# ======================================================
# Export Functions
# ======================================================
def export_project_data(project_name, export_format, payload):
    """Export complete project data"""
    export_url = generate_export_file(project_name, "project", export_format)

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "export_type": "project",
                "project_name": project_name,
                "format": export_format,
                "download_url": export_url,
                "expires_at": "2024-01-16T12:00:00Z",
            }
        ),
    }


def export_documents(project_name, export_format, payload):
    """Export document metadata and content"""
    document_list = payload.get("documents", [])
    export_url = generate_export_file(project_name, "documents", export_format)

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "export_type": "documents",
                "project_name": project_name,
                "document_count": len(document_list),
                "format": export_format,
                "download_url": export_url,
                "expires_at": "2024-01-16T12:00:00Z",
            }
        ),
    }


def export_analysis_results(project_name, export_format, payload):
    """Export analysis results and insights"""
    export_url = generate_export_file(project_name, "analysis", export_format)

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "export_type": "analysis",
                "project_name": project_name,
                "format": export_format,
                "download_url": export_url,
                "expires_at": "2024-01-16T12:00:00Z",
            }
        ),
    }


def generate_export_file(project_name, export_type, format):
    """Generate export file and return presigned URL"""
    filename = f"{project_name}_{export_type}_export_{format}"
    # Generate presigned URL for download (mocked for now)
    return f"https://your-export-bucket.s3.amazonaws.com/{filename}?presigned=true"
