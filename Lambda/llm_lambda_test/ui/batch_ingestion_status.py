# batch_ingestion_status_handler.py
"""
UI-related Lambda route handler for batch ingestion status.

Responsibilities:
- Handle `/batch_ingestion_status` route
- Retrieve project ingestion status from DynamoDB
- Calculate and return batch ingestion statistics
"""

# ======================================================
# Imports
# ======================================================
import os

from utils.logger import CustomLogger
from utils.dynamodb import get_item_from_dynamo, scan_table
from Lambda.llm_lambda_test.lambda_handler import make_response

# ======================================================
# Logger / Env Vars
# ======================================================
logger = CustomLogger(__name__)
PROJECT_CONFIG_TABLE = os.environ.get("PROJECT_CONFIG_TABLE")


# ======================================================
# Handler
# ======================================================
def handle_batch_ingestion_status(event, payload):
    """
    Handles /batch_ingestion_status route:
    - Checks status of multiple document ingestion
    - Returns progress overview for file uploads
    """
    try:
        project_name = payload.get("project_name")
        session_id = payload.get("session_id")

        if not project_name:
            return make_response(400, "Missing required parameter: project_name")

        # --------------------------------------------------
        # Get overall project status
        # --------------------------------------------------
        try:
            project_status = get_item_from_dynamo(
                PROJECT_CONFIG_TABLE,
                {"project_name": project_name},
            )
        except Exception as e:
            logger.warning(f"⚠️ Could not get project status: {e}")
            project_status = {}

        # --------------------------------------------------
        # Get ingestion history for this session/project
        # --------------------------------------------------
        try:
            ingestion_history = []
            scan_result = scan_table(
                PROJECT_CONFIG_TABLE,
                filter_expression="project_name = :project_name",
                expression_attribute_values={":project_name": project_name},
            )

            for item in scan_result.get("Items", []):
                if item.get("record_type") == "ingestion" or "ingestion" in str(item):
                    ingestion_history.append(item)

        except Exception as e:
            logger.warning(f"⚠️ Could not get ingestion history: {e}")
            ingestion_history = []

        # --------------------------------------------------
        # Calculate batch statistics
        # --------------------------------------------------
        total_documents = len(ingestion_history)
        successful_documents = len([h for h in ingestion_history if h.get("status") == "completed"])
        failed_documents = len([h for h in ingestion_history if h.get("status") == "failed"])
        in_progress_documents = len([h for h in ingestion_history if h.get("status") == "processing"])

        batch_status = {
            "project_name": project_name,
            "session_id": session_id,
            "total_documents": total_documents,
            "successful_documents": successful_documents,
            "failed_documents": failed_documents,
            "in_progress_documents": in_progress_documents,
            "completion_percentage": (successful_documents / total_documents * 100) if total_documents > 0 else 0,
            "project_status": project_status.get("status", "unknown"),
            "last_updated": project_status.get("last_updated"),
            "ingestion_history": ingestion_history[-10:] if ingestion_history else [],  # Last 10 records
        }

        logger.info(
            f"📊 Batch status for {project_name}: {successful_documents}/{total_documents} completed"
        )
        return make_response(200, batch_status)

    except Exception as e:
        logger.error(f"💥 Error getting batch ingestion status: {e}", exc_info=True)
        return make_response(500, f"Error getting batch status: {str(e)}")
