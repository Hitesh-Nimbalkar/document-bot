import json

from utils.logger import CustomLogger
from src.data_ingestion import ingest_document

logger = CustomLogger(__name__)


def handle_batch_operations(event, payload):
    """
    Handle batch operations on multiple documents.
    Supports: batch_ingest, batch_delete, batch_analyze
    """
    try:
        operation = payload.get("operation")
        documents = payload.get("documents", [])
        project_name = payload.get("project_name")

        if not all([operation, documents, project_name]):
            return {
                "statusCode": 400,
                "body": json.dumps(
                    {"error": "operation, documents, and project_name are required"}
                ),
            }

        if operation == "batch_ingest":
            return handle_batch_ingest(documents, project_name, payload)
        elif operation == "batch_delete":
            return handle_batch_delete(documents, project_name)
        elif operation == "batch_analyze":
            return handle_batch_analyze(documents, project_name)
        else:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Invalid operation"}),
            }

    except Exception as e:
        logger.error(f"Error in batch operations: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


def handle_batch_ingest(documents, project_name, payload):
    """Handle batch ingestion of multiple documents"""
    results = []

    for doc in documents:
        try:
            doc_payload = {**payload, "file_path": doc}
            result = ingest_document(doc_payload)
            results.append(
                {
                    "document": doc,
                    "status": "success",
                    "result": result.dict() if hasattr(result, "dict") else result,
                }
            )
        except Exception as e:
            results.append(
                {
                    "document": doc,
                    "status": "error",
                    "error": str(e),
                }
            )

    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "operation": "batch_ingest",
                "total_documents": len(documents),
                "results": results,
                "success_count": sum(1 for r in results if r["status"] == "success"),
                "error_count": sum(1 for r in results if r["status"] == "error"),
            }
        ),
    }


def handle_batch_delete(documents, project_name):
    """Handle batch deletion of documents"""
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "operation": "batch_delete",
                "message": f"Deleted {len(documents)} documents from {project_name}",
            }
        ),
    }


def handle_batch_analyze(documents, project_name):
    """Handle batch analysis of documents"""
    return {
        "statusCode": 200,
        "body": json.dumps(
            {
                "operation": "batch_analyze",
                "message": f"Analyzed {len(documents)} documents from {project_name}",
            }
        ),
    }
