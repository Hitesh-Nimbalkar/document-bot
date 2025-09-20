# =====================================================
# UI MODULE IMPORTS (UI-specific functionality only)
# =====================================================
try:
    from ui.list_project_files import handle_list_project_files
    from ui.get_presigned_url import handle_get_presigned_url
    from ui.get_models_config import handle_get_models_config
    # New UI functionality imports
    from ui.upload_status import handle_upload_status
    from ui.document_preview import handle_document_preview
    from ui.batch_operations import handle_batch_operations
    from ui.project_management import handle_project_management
    from ui.document_search import handle_document_search
    from ui.export_data import handle_export_data
    # Additional UI components
    from ui.user_management import handle_user_management
    from ui.analytics_dashboard import handle_analytics_dashboard
    from ui.notification_system import handle_notifications
except ImportError as e:
    print(f"Warning: Some UI modules not found: {e}")

    # Define safe fallbacks for all UI handlers
    def _not_implemented(module_name: str):
        def _handler(event, payload):
            return {
                "statusCode": 501,
                "body": {
                    "error": f"{module_name} module not implemented"
                }
            }
        return _handler

    handle_list_project_files = _not_implemented("List project files")
    handle_get_presigned_url = _not_implemented("Get presigned URL")
    handle_get_models_config = _not_implemented("Get models config")
    handle_upload_status = _not_implemented("Upload status")
    handle_document_preview = _not_implemented("Document preview")
    handle_batch_operations = _not_implemented("Batch operations")
    handle_project_management = _not_implemented("Project management")
    handle_document_search = _not_implemented("Document search")
    handle_export_data = _not_implemented("Export data")
    handle_user_management = _not_implemented("User management")
    handle_analytics_dashboard = _not_implemented("Analytics dashboard")
    handle_notifications = _not_implemented("Notification system")


# =====================================================
# SYSTEM & LIBRARY IMPORTS
# =====================================================
import json
import os
import uuid
import datetime
import boto3
from botocore.exceptions import ClientError
from pydantic import ValidationError

# ---------------------------
# Logger & Config (ENV VARS)
# ---------------------------
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET")  # Bucket for finalized documents
TEMP_PREFIX = os.getenv("TEMP_DATA_KEY", "project-data/uploads/temp")  # Temporary upload prefix

# ---------------------------
# Local imports
# ---------------------------
from utils.logger import CustomLogger, CustomException
#from utils.document_type_utils import detect_document_type, extract_text_from_document
from chat_history.chat_history import log_chat_history
from rag.rag_pipeline import RAGPipeline
from src.data_ingestion import ingest_document
from src.data_analysis import DocumentAnalyzer
# from src.document_comparator import DocumentComparator
# from models.models import IngestionPayload, IngestionResponse, DocumentComparisonInput

# ---------------------------
# Logger instance
# ---------------------------
logger = CustomLogger(__name__)
s3 = boto3.client("s3")

ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt")
MAX_FILE_SIZE_MB = 25   # optional limit


# =====================================================
# ENHANCED RESPONSE HELPER
# =====================================================
def make_response(status_code, body):
    """Enhanced response helper with better error handling and validation"""
    try:
        response = {
            "statusCode": status_code,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "OPTIONS,POST,GET,PUT,DELETE",
                "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Requested-With",
                "Content-Type": "application/json"
            },
            "body": body if isinstance(body, str) else json.dumps(body, default=str)
        }
        
        # Add timestamp to all responses
        if isinstance(body, dict) and "timestamp" not in body:
            if isinstance(response["body"], str):
                parsed_body = json.loads(response["body"])
                parsed_body["timestamp"] = datetime.datetime.utcnow().isoformat()
                response["body"] = json.dumps(parsed_body, default=str)
        
        return response
    except Exception as e:
        logger.error(f"Error creating response: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Response formatting error", "details": str(e)})
        }


# =====================================================
# INPUT VALIDATION HELPERS
# =====================================================
def validate_common_params(payload, required_fields=None):
    """Validate common parameters across UI routes"""
    if required_fields is None:
        required_fields = []
    
    missing_fields = []
    for field in required_fields:
        if field not in payload or payload[field] is None:
            missing_fields.append(field)
    
    if missing_fields:
        raise ValueError(f"Missing required fields: {', '.join(missing_fields)}")
    
    if "project_name" in payload:
        project_name = payload["project_name"]
        if not isinstance(project_name, str) or len(project_name.strip()) == 0:
            raise ValueError("project_name must be a non-empty string")
    
    return True


# =====================================================
# ROUTE HANDLERS (UI imports)
# =====================================================
def handle_ingest_route(event, payload):
    """Handles /ingest_data route: Runs ingestion pipeline and returns results"""
    try:
        ingest_result = ingest_document(payload)
        if hasattr(ingest_result, "results"):  # BatchIngestionResponse
            body = {
                "summary": ingest_result.summary,
                "results": [r.dict() for r in ingest_result.results]
            }
            logger.info(f"✅ Ingestion complete → {body['summary']}")
            return make_response(200, body)
        else:
            logger.info(f"✅ Single ingestion complete → status={ingest_result.statusCode}")
            return make_response(ingest_result.statusCode, ingest_result.dict())
    except Exception as e:
        logger.error(f"💥 Error in handle_ingest_route: {e}", exc_info=True)
        return make_response(500, f"Error in ingestion: {str(e)}")


def handle_rag_query(payload: dict, event: dict) -> dict:
    """Handle RAG query with enhanced pipeline including chat history integration"""
    try:
        logger.info("🔍 Starting enhanced RAG query handling")
        
        query = payload.get("query")
        project_name = payload.get("project_name")
        session_id = payload.get("session_id")
        
        if not all([query, project_name]):
            raise ValueError("Missing required fields: query, project_name")
            
        rag_pipeline = RAGPipeline(project_name=project_name)
        
        chat_history = []
        if session_id:
            try:
                chat_history = rag_pipeline.get_enhanced_chat_history(session_id, limit=10)
                logger.info(f"📜 Retrieved {len(chat_history)} chat history messages")
            except Exception as e:
                logger.warning(f"Could not retrieve chat history: {e}")
        
        result = rag_pipeline.run(
            query=query,
            chat_history=chat_history,
            event=event,
            payload=payload,
            top_k=payload.get("top_k", 5),
            enable_reranking=payload.get("enable_reranking", True)
        )
        
        enhancement_info = result.get("enhancement_features", {})
        logger.info(f"✨ Enhanced RAG features used: {enhancement_info}")
        return make_response(200, {
            **result,
            "success": True,
            "pipeline_version": "enhanced_with_metadata_and_chat_history"
        })
        
    except Exception as e:
        logger.error(f"💥 Enhanced RAG query failed: {e}")
        return make_response(500, {"error": str(e), "success": False})


# =====================================================
# UI ROUTE HANDLERS - ENHANCED WITH VALIDATION
# =====================================================
def handle_ui_route(route_name, handler_func, event, payload, required_fields=None):
    """Generic UI route handler with validation"""
    try:
        logger.info(f"🎨 Processing UI route: {route_name}")
        
        if required_fields:
            validate_common_params(payload, required_fields)
        
        payload["_route_context"] = {
            "route_name": route_name,
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "request_id": event.get("requestContext", {}).get("requestId", str(uuid.uuid4()))
        }
        
        result = handler_func(event, payload)
        
        if not isinstance(result, dict) or "statusCode" not in result:
            logger.warning(f"Handler {route_name} returned improper format, wrapping...")
            result = make_response(200, result)
        
        logger.info(f"✅ UI route {route_name} completed successfully")
        return result
        
    except ValueError as ve:
        logger.error(f"Validation error in UI route {route_name}: {ve}")
        return make_response(400, {
            "error": str(ve),
            "route": route_name,
            "success": False,
            "error_type": "validation"
        })
    except Exception as e:
        logger.error(f"💥 Error in UI route {route_name}: {e}", exc_info=True)
        return make_response(500, {
            "error": str(e),
            "route": route_name,
            "success": False,
            "error_type": "internal"
        })


# Individual route wrappers
def handle_upload_status_route(event, payload): return handle_ui_route("upload_status", handle_upload_status, event, payload, ["project_name"])
def handle_document_preview_route(event, payload): return handle_ui_route("document_preview", handle_document_preview, event, payload, ["document_id"])
def handle_batch_operations_route(event, payload): return handle_ui_route("batch_operations", handle_batch_operations, event, payload, ["operation_type"])
def handle_project_management_route(event, payload): return handle_ui_route("project_management", handle_project_management, event, payload, ["action"])
def handle_document_search_route(event, payload): return handle_ui_route("document_search", handle_document_search, event, payload, ["project_name"])
def handle_export_data_route(event, payload): return handle_ui_route("export_data", handle_export_data, event, payload, ["export_type"])
def handle_user_management_route(event, payload): return handle_ui_route("user_management", handle_user_management, event, payload, ["action"])
def handle_analytics_dashboard_route(event, payload): return handle_ui_route("analytics_dashboard", handle_analytics_dashboard, event, payload, ["dashboard_type"])
def handle_notifications_route(event, payload): return handle_ui_route("notifications", handle_notifications, event, payload)


# =====================================================
# MAIN LAMBDA HANDLER
# =====================================================
def lambda_handler(event, context):
    """Main Lambda entrypoint with comprehensive error handling"""
    try:
        route = event.get("route") or event.get("httpMethod", "").upper() + " " + event.get("path", "/unknown")
        payload = event.get("payload") or event.get("body", {})
        
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                logger.error("Invalid JSON in payload")
                return make_response(400, {"error": "Invalid JSON in request body"})
        
        logger.info(f"📨 Received request → route={route}, method={event.get('httpMethod', 'UNKNOWN')}")
        
        if event.get("httpMethod") == "OPTIONS":
            return make_response(200, {"message": "CORS preflight successful"})
        
        # Core API routes
        if route == "/get_presigned_url": return handle_get_presigned_url(event, payload)
        elif route == "/ingest_data": return handle_ingest_route(event, payload)
        elif route == "/list_project_files": return handle_list_project_files(event, payload)
        elif route == "/rag_query": return handle_rag_query(payload, event)
        elif route == "/get_models_config": return handle_get_models_config(event, payload)
        
        # UI routes
        elif route == "/upload_status": return handle_upload_status_route(event, payload)
        elif route == "/document_preview": return handle_document_preview_route(event, payload)
        elif route == "/batch_operations": return handle_batch_operations_route(event, payload)
        elif route == "/project_management": return handle_project_management_route(event, payload)
        elif route == "/document_search": return handle_document_search_route(event, payload)
        elif route == "/export_data": return handle_export_data_route(event, payload)
        elif route == "/user_management": return handle_user_management_route(event, payload)
        elif route == "/analytics_dashboard": return handle_analytics_dashboard_route(event, payload)
        elif route == "/notifications": return handle_notifications_route(event, payload)
        
        # Health check
        elif route == "/health":
            return make_response(200, {
                "status": "healthy",
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "version": "enhanced_ui_v1.1",
                "lambda_context": {
                    "function_name": context.function_name if context else "unknown",
                    "remaining_time": context.get_remaining_time_in_millis() if context else None
                }
            })
        elif route == "/routes":
            available_routes = [
                {"route": "/get_presigned_url", "methods": ["POST"], "description": "Generate presigned URL"},
                {"route": "/ingest_data", "methods": ["POST"], "description": "Ingest document data"},
                {"route": "/list_project_files", "methods": ["POST"], "description": "List files in a project"},
                {"route": "/rag_query", "methods": ["POST"], "description": "Perform RAG query"},
                {"route": "/get_models_config", "methods": ["GET", "POST"], "description": "Get model configuration"},
                {"route": "/upload_status", "methods": ["GET", "POST"], "description": "Check upload status"},
                {"route": "/document_preview", "methods": ["POST"], "description": "Generate document preview"},
                {"route": "/batch_operations", "methods": ["POST"], "description": "Perform batch operations"},
                {"route": "/project_management", "methods": ["POST", "PUT", "DELETE"], "description": "Manage projects"},
                {"route": "/document_search", "methods": ["POST"], "description": "Search documents"},
                {"route": "/export_data", "methods": ["POST"], "description": "Export data"},
                {"route": "/user_management", "methods": ["POST", "PUT", "DELETE"], "description": "Manage users"},
                {"route": "/analytics_dashboard", "methods": ["GET", "POST"], "description": "Get analytics data"},
                {"route": "/notifications", "methods": ["GET", "POST"], "description": "Handle notifications"},
                {"route": "/health", "methods": ["GET"], "description": "Health check"},
                {"route": "/routes", "methods": ["GET"], "description": "List available routes"}
            ]
            return make_response(200, {"available_routes": available_routes})
        
        else:
            logger.warning(f"❌ Unknown route → {route}")
            return make_response(404, {
                "error": f"Route '{route}' not found",
                "available_routes_endpoint": "/routes",
                "supported_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
            })
            
    except Exception as e:
        logger.error(f"💥 Critical error in lambda_handler: {e}", exc_info=True)
        return make_response(500, {
            "error": f"Lambda handler critical error: {str(e)}",
            "success": False,
            "error_type": "critical"
        })
