import json
from utils.logger import CustomLogger

# ======================================================
# Logger
# ======================================================
logger = CustomLogger(__name__)


# ======================================================
# Handlers
# ======================================================
def handle_document_search(event, payload):
    """
    Handle document search and filtering.
    Supports: text search, metadata filtering, date range filtering.
    """
    try:
        project_name = payload.get("project_name")
        search_query = payload.get("search_query", "")
        filters = payload.get("filters", {})
        sort_by = payload.get("sort_by", "relevance")
        limit = payload.get("limit", 20)
        offset = payload.get("offset", 0)

        if not project_name:
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "project_name is required"}),
            }

        search_results = perform_document_search(
            project_name, search_query, filters, sort_by, limit, offset
        )

        return {
            "statusCode": 200,
            "body": json.dumps(
                {
                    "search_query": search_query,
                    "filters": filters,
                    "results": search_results["documents"],
                    "total_count": search_results["total_count"],
                    "page_info": {
                        "limit": limit,
                        "offset": offset,
                        "has_more": search_results["has_more"],
                    },
                }
            ),
        }

    except Exception as e:
        logger.error(f"Error in document search: {e}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


def perform_document_search(project_name, search_query, filters, sort_by, limit, offset):
    """Perform the actual document search (mock implementation)."""
    mock_documents = [
        {
            "file_path": "document1.pdf",
            "title": "Sample Document 1",
            "content_preview": "This is a sample document about...",
            "metadata": {
                "upload_date": "2024-01-01",
                "file_size": "2.5 MB",
                "document_type": "PDF",
            },
            "relevance_score": 0.95,
        },
        {
            "file_path": "document2.docx",
            "title": "Sample Document 2",
            "content_preview": "Another document containing...",
            "metadata": {
                "upload_date": "2024-01-02",
                "file_size": "1.8 MB",
                "document_type": "DOCX",
            },
            "relevance_score": 0.87,
        },
    ]

    return {
        "documents": mock_documents[offset : offset + limit],
        "total_count": len(mock_documents),
        "has_more": (offset + limit) < len(mock_documents),
    }
