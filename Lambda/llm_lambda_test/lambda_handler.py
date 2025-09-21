# =====================================================
# UI MODULE IMPORTS (only get_presigned_url)
# =====================================================
def _not_implemented(module_name: str):
    def _handler(event, payload):
        return {
            "statusCode": 501,
            "body": {
                "error": f"{module_name} module not implemented"
            }
        }
    return _handler
try:
    from ui.get_presigned_url import handle_get_presigned_url
except ImportError as e:
    print(f"⚠️ Could not import get_presigned_url: {e}")
    handle_get_presigned_url = _not_implemented("Get presigned URL")

# =====================================================
# SYSTEM & LIBRARY IMPORTS
# =====================================================
import json
import os
import uuid
import datetime
import boto3
from botocore.exceptions import ClientError
# ---------------------------
# Logger & Config (ENV VARS)
# ---------------------------
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET")
TEMP_PREFIX = os.getenv("TEMP_DATA_KEY", "project-data/uploads/temp")
# ---------------------------
# Local imports
# ---------------------------
from utils.logger import CustomLogger, CustomException
from chat_history.chat_history import log_chat_history
from rag.rag_pipeline import RAGPipeline
from src.data_ingestion import ingest_document
from src.data_analysis import DocumentAnalyzer
# ---------------------------
# Logger instance
# ---------------------------
logger = CustomLogger(__name__)
s3 = boto3.client("s3")
ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt")
MAX_FILE_SIZE_MB = 25

# =====================================================
# RESPONSE HELPER
# =====================================================
def make_response(status_code, body):
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
        if isinstance(body, dict) and "timestamp" not in body:
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
# ROUTE HANDLERS
# =====================================================
def handle_ingest_route(event, payload):
    try:
        logger.info(f"🚀 Handling ingest route with payload: {payload}")
        
        # Transform lambda_upload_responses format to expected format
        if "lambda_upload_responses" in payload:
            logger.info("📋 Transforming lambda_upload_responses format")
            lambda_responses = payload["lambda_upload_responses"]
            
            if not isinstance(lambda_responses, list) or not lambda_responses:
                logger.error("❌ lambda_upload_responses must be a non-empty list")
                return make_response(400, {"error": "Invalid lambda_upload_responses format"})
            
            # Transform the format: extract the body from each lambda response and use it directly
            try:
                # Take the first response and use its body as the base payload
                first_response = lambda_responses[0]
                if "body" in first_response:
                    # Parse the body to get the actual data
                    base_payload = json.loads(first_response["body"]) if isinstance(first_response["body"], str) else first_response["body"]
                    
                    # If there are multiple responses, collect all doc_locs
                    all_doc_locs = []
                    for response in lambda_responses:
                        if "body" in response:
                            response_data = json.loads(response["body"]) if isinstance(response["body"], str) else response["body"]
                            if "doc_loc" in response_data:
                                all_doc_locs.append(response_data["doc_loc"])
                            if "doc_locs" in response_data:
                                all_doc_locs.extend(response_data["doc_locs"])
                    
                    # Use the transformed format
                    payload = {
                        **base_payload,  # Use all fields from the first response
                        "doc_locs": all_doc_locs  # Override with collected doc_locs
                    }
                    logger.info(f"🔄 Transformed payload: {payload}")
                    
            except Exception as e:
                logger.error(f"❌ Failed to transform lambda responses: {e}")
                return make_response(400, {"error": f"Failed to transform payload: {str(e)}"})
        
        ingest_result = ingest_document(payload)
        logger.info(f"📋 Ingest result type: {type(ingest_result)}")
        logger.info(f"📋 Ingest result: {ingest_result}")
        
        if hasattr(ingest_result, "results"):
            body = {
                "summary": ingest_result.summary,
                "results": [r.dict() for r in ingest_result.results]
            }
            logger.info(f"✅ Ingestion complete → {body['summary']}")
            return make_response(200, body)
        else:
            logger.warning(f"⚠️ Ingest result doesn't have results attribute, returning raw result")
            return make_response(ingest_result.statusCode, ingest_result.dict())
    except Exception as e:
        logger.error(f"💥 Error in handle_ingest_route: {e}", exc_info=True)
        return make_response(500, {"error": f"Error in ingestion: {str(e)}", "details": str(e)})

def handle_rag_query(payload: dict, event: dict) -> dict:
    try:
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
        return make_response(200, {
            **result,
            "success": True,
            "pipeline_version": "enhanced_with_metadata_and_chat_history"
        })
    except Exception as e:
        logger.error(f"💥 RAG query failed: {e}")
        return make_response(500, {"error": str(e), "success": False})

# =====================================================
# MAIN LAMBDA HANDLER
# =====================================================
def lambda_handler(event, context):
    try:
        route = event.get("route") or event.get("httpMethod", "").upper() + " " + event.get("path", "/unknown")
        payload = event.get("payload") or event.get("body", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return make_response(400, {"error": "Invalid JSON in request body"})
        if event.get("httpMethod") == "OPTIONS":
            return make_response(200, {"message": "CORS preflight successful"})
        # Core API routes
        if route == "/get_presigned_url": return handle_get_presigned_url(event, payload)
        elif route == "/ingest_data": return handle_ingest_route(event, payload)
        elif route == "/rag_query": return handle_rag_query(payload, event)
        # Health check
        elif route == "/health":
            return make_response(200, {
                "status": "healthy",
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "version": "ui_presigned_only_v1",
                "lambda_context": {
                    "function_name": context.function_name if context else "unknown",
                    "remaining_time": context.get_remaining_time_in_millis() if context else None
                }
            })
        elif route == "/routes":
            available_routes = [
                {"route": "/get_presigned_url", "methods": ["POST"], "description": "Generate presigned URL"},
                {"route": "/ingest_data", "methods": ["POST"], "description": "Ingest document data"},
                {"route": "/rag_query", "methods": ["POST"], "description": "Perform RAG query"},
                {"route": "/health", "methods": ["GET"], "description": "Health check"},
                {"route": "/routes", "methods": ["GET"], "description": "List available routes"}
            ]
            return make_response(200, {"available_routes": available_routes})
        else:
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
