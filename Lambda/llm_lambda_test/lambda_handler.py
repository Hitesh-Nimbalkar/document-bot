


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
from rag.rag_simple import SimpleRAGPipeline  # Add simple RAG pipeline
from src.data_ingestion import ingest_document
from src.data_analysis import DocumentAnalyzer
from utils.model_loader import ModelLoader, BedrockProvider
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
        
        # Get model configuration from payload or use defaults
        llm_model = payload.get("llm_model", os.getenv("DEFAULT_LLM_MODEL", "anthropic.claude-3-sonnet-20240229-v1:0"))
        embedding_model = payload.get("embedding_model", os.getenv("DEFAULT_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0"))
        region = payload.get("bedrock_region", os.getenv("BEDROCK_REGION", "ap-south-1"))
        
        logger.info(f"🧠 Initializing RAG with models: LLM={llm_model}, Embedding={embedding_model}, Region={region}")
        
        # Create ModelLoader with BedrockProvider
        model_loader = ModelLoader()
        bedrock_provider = BedrockProvider(
            embedding_model=embedding_model,
            llm_model=llm_model,
            region=region,
            logger=logger._logger if hasattr(logger, '_logger') else None
        )
        model_loader.register("bedrock", bedrock_provider, model_name=llm_model)
        
        # Initialize RAG pipeline with model loader and LLM model ID
        rag_pipeline = RAGPipeline(project_name=project_name, model_loader=model_loader, llm_model_id=llm_model)
        
        # Get chat history
        chat_history = []
        if session_id:
            try:
                chat_history = rag_pipeline.get_enhanced_chat_history(session_id, limit=payload.get("chat_history_limit", 10))
                logger.info(f"📚 Retrieved {len(chat_history)} chat history messages")
            except Exception as e:
                logger.warning(f"Could not retrieve chat history: {e}")
        
        # Enhanced RAG parameters from payload
        rag_params = {
            "query": query,
            "chat_history": chat_history,
            "event": event,
            "payload": payload,
            "top_k": payload.get("top_k", 5),
            "enable_reranking": payload.get("enable_reranking", True)
        }
        
        logger.info(f"🔍 RAG Parameters: top_k={rag_params['top_k']}, reranking={rag_params['enable_reranking']}")
        
        # Run RAG pipeline with enhanced parameters
        result = rag_pipeline.run(**rag_params)
        
        return make_response(200, {
            **result,
            "success": True,
            "pipeline_version": "enhanced_with_model_loader_v2",
            "models_used": {
                "llm_model": llm_model,
                "embedding_model": embedding_model,
                "region": region
            }
        })
    except Exception as e:
        logger.error(f"💥 RAG query failed: {e}", exc_info=True)
        return make_response(500, {
            "error": str(e), 
            "success": False,
            "error_type": "rag_query_error"
        })

def handle_rag_simple(payload: dict, event: dict) -> dict:
    """Handle simple RAG query - basic semantic search for testing"""
    try:
        query = payload.get("query")
        project_name = payload.get("project_name")
        session_id = payload.get("session_id")  # Accept session_id like regular RAG
        
        if not all([query, project_name]):
            raise ValueError("Missing required fields: query, project_name")
        
        logger.info(f"🚀 Simple RAG Query: {query} for project: {project_name}")
        
        # Get model configuration from payload or use defaults (same as regular RAG)
        llm_model = payload.get("llm_model", os.getenv("DEFAULT_LLM_MODEL", "anthropic.claude-3-sonnet-20240229-v1:0"))
        embedding_model = payload.get("embedding_model", os.getenv("DEFAULT_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0"))
        region = payload.get("bedrock_region", os.getenv("BEDROCK_REGION", "ap-south-1"))
        
        logger.info(f"🧠 Simple RAG models: LLM={llm_model}, Embedding={embedding_model}, Region={region}")
        
        # Create ModelLoader with BedrockProvider (same as regular RAG)
        model_loader = ModelLoader()
        bedrock_provider = BedrockProvider(
            embedding_model=embedding_model,
            llm_model=llm_model,
            region=region,
            logger=logger._logger if hasattr(logger, '_logger') else None
        )
        model_loader.register("bedrock", bedrock_provider, model_name=llm_model)
        
        # Initialize Simple RAG pipeline
        simple_rag = SimpleRAGPipeline(project_name=project_name, model_loader=model_loader)
        
        # Simple RAG parameters (same parameter names as regular RAG)
        top_k = payload.get("top_k", 5)
        chat_history_limit = payload.get("chat_history_limit", 10)  # Accept but don't use in simple mode
        enable_reranking = payload.get("enable_reranking", True)    # Accept but don't use in simple mode
        temperature = payload.get("temperature")  # Pass through generation parameters
        max_tokens = payload.get("max_tokens")
        top_p = payload.get("top_p")
        
        logger.info(f"🔍 Simple RAG Parameters: top_k={top_k} (other params accepted but not used in simple mode)")
        
        # Run simple RAG pipeline with same payload structure
        result = simple_rag.run(
            query=query,
            top_k=top_k,
            event=event,
            payload=payload  # Pass full payload to maintain consistency
        )
        
        return make_response(200, {
            **result,
            "pipeline_version": "simple_v1",
            "models_used": {
                "llm_model": llm_model,
                "embedding_model": embedding_model,
                "region": region
            }
        })
        
    except Exception as e:
        logger.error(f"💥 Simple RAG query failed: {e}", exc_info=True)
        return make_response(500, {
            "error": str(e), 
            "success": False,
            "error_type": "simple_rag_error"
        })
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
        elif route == "/rag_simple": return handle_rag_simple(payload, event)  # New simple RAG route
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
                {"route": "/rag_query", "methods": ["POST"], "description": "Perform enhanced RAG query"},
                {"route": "/rag_simple", "methods": ["POST"], "description": "Perform simple RAG query (testing)"},
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

