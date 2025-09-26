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
import datetime
import boto3
from botocore.exceptions import ClientError
from pydantic import ValidationError

# ---------------------------
# Logger & Config (ENV VARS)
# ---------------------------
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET")
TEMP_PREFIX = os.getenv("TEMP_DATA_KEY")

# ---------------------------
# Local imports
# ---------------------------
from utils.logger import CustomLogger
from rag.rag_pipeline import RAGPipeline
from rag_simple.rag_simple import SimpleRAGPipeline
from src.data_ingestion import ingest_document
from utils.model_loader import ModelLoader, BedrockProvider
from models.models import SimpleRAGRequest

# ---------------------------
# Logger instance
# ---------------------------
logger = CustomLogger(__name__)
s3 = boto3.client("s3")

# =====================================================
# RESPONSE HELPER with CORS
# =====================================================
def make_response(status_code, body):
    """Standard JSON + CORS response"""
    try:
        response = {
            "statusCode": status_code,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "OPTIONS,POST,GET,PUT,DELETE",
                "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Requested-With,X-Session-ID",
                "Content-Type": "application/json"
            },
            "body": body if isinstance(body, str) else json.dumps(body, default=str)
        }
        # add timestamp if not present
        if isinstance(body, dict) and "timestamp" not in body:
            parsed_body = json.loads(response["body"])
            parsed_body["timestamp"] = datetime.datetime.utcnow().isoformat()
            response["body"] = json.dumps(parsed_body, default=str)
        return response
    except Exception as e:
        logger.error(f"Error creating response: {e}")
        return {
            "statusCode": 500,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "OPTIONS,POST,GET,PUT,DELETE",
                "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Requested-With,X-Session-ID",
                "Content-Type": "application/json"
            },
            "body": json.dumps({"error": "Response formatting error", "details": str(e)})
        }

# =====================================================
# ROUTE HANDLERS
# =====================================================
def handle_ingest_route(event, payload):
    try:
        logger.info(f"🚀 Handling ingest route with payload: {payload}")
        ingest_result = ingest_document(payload)

        if hasattr(ingest_result, "results"):
            body = {
                "summary": ingest_result.summary,
                "results": [r.dict() for r in ingest_result.results]
            }
            return make_response(200, body)
        else:
            return make_response(ingest_result.statusCode, ingest_result.dict())
    except Exception as e:
        logger.error(f"💥 Error in handle_ingest_route: {e}", exc_info=True)
        return make_response(500, {"error": f"Error in ingestion: {str(e)}"})

def handle_rag_query(payload: dict, event: dict) -> dict:
    try:
        query = payload.get("query")
        project_name = payload.get("project_name")
        session_id = payload.get("session_id")

        if not all([query, project_name]):
            raise ValueError("Missing required fields: query, project_name")

        # Get model config
        llm_model = payload.get("llm_model", os.getenv("DEFAULT_LLM_MODEL", "anthropic.claude-3-sonnet-20240229-v1:0"))
        embedding_model = payload.get("embedding_model", os.getenv("DEFAULT_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0"))
        region = payload.get("bedrock_region", os.getenv("BEDROCK_REGION", "ap-south-1"))

        logger.info(f"🧠 Initializing RAG: LLM={llm_model}, Embedding={embedding_model}, Region={region}")

        model_loader = ModelLoader()
        bedrock_provider = BedrockProvider(
            embedding_model=embedding_model,
            llm_model=llm_model,
            region=region,
            logger=logger._logger if hasattr(logger, '_logger') else None
        )
        model_loader.register("bedrock", bedrock_provider, model_name=llm_model)

        rag_pipeline = RAGPipeline(project_name=project_name, model_loader=model_loader, llm_model_id=llm_model)

        chat_history = []
        if session_id:
            try:
                chat_history = rag_pipeline.get_enhanced_chat_history(session_id, limit=payload.get("chat_history_limit", 10))
            except Exception as e:
                logger.warning(f"Could not retrieve chat history: {e}")

        rag_params = {
            "query": query,
            "chat_history": chat_history,
            "event": event,
            "payload": payload,
            "top_k": payload.get("top_k", 5),
            "enable_reranking": payload.get("enable_reranking", True)
        }

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
        return make_response(500, {"error": str(e), "success": False, "error_type": "rag_query_error"})

def handle_rag_simple(payload: dict, event: dict) -> dict:
    """Simple RAG query"""
    try:
        try:
            validated_request = SimpleRAGRequest(**payload)
        except ValidationError as e:
            return make_response(400, {
                "error": "Invalid request format",
                "validation_errors": e.errors(),
                "success": False
            })

        metadata = validated_request.metadata or {}
        llm_model = metadata.get("llm_model") or os.getenv("DEFAULT_LLM_MODEL", "anthropic.claude-3-sonnet-20240229-v1:0")
        embedding_model = metadata.get("embedding_model") or os.getenv("DEFAULT_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
        region = metadata.get("bedrock_region") or os.getenv("BEDROCK_REGION", "ap-south-1")

        model_loader = ModelLoader()
        bedrock_provider = BedrockProvider(
            embedding_model=embedding_model,
            llm_model=llm_model,
            region=region,
            logger=logger._logger if hasattr(logger, '_logger') else None
        )
        model_loader.register("bedrock", bedrock_provider, model_name=llm_model)

        simple_rag = SimpleRAGPipeline(project_name=validated_request.project_name, model_loader=model_loader)
        top_k = min(metadata.get("top_k", 3), 3)
        pipeline_result = simple_rag.run(
            query=validated_request.query,
            top_k=top_k,
            event=event,
            payload=validated_request.dict()
        )

        return make_response(200, pipeline_result)

    except Exception as e:
        logger.error(f"💥 Simple RAG query failed: {e}", exc_info=True)
        return make_response(500, {
            "answer": {"summary": "An error occurred while processing your request."},
            "success": False,
            "error": str(e),
            "error_type": "simple_rag_error"
        })

# =====================================================
# MAIN LAMBDA HANDLER
# =====================================================
def lambda_handler(event, context):
    try:
        # Handle preflight CORS
        if event.get("httpMethod") == "OPTIONS":
            return make_response(200, {"message": "CORS preflight successful"})

        route = event.get("route") or event.get("path", "")
        payload = event.get("payload") or event.get("body", {})
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return make_response(400, {"error": "Invalid JSON in request body"})

        # Routes
        if route == "/get_presigned_url": return handle_get_presigned_url(event, payload)
        if route == "/ingest_data": return handle_ingest_route(event, payload)
        if route == "/rag_query": return handle_rag_query(payload, event)
        if route == "/rag_simple": return handle_rag_simple(payload, event)
        if route == "/health":
            return make_response(200, {
                "status": "healthy",
                "timestamp": datetime.datetime.utcnow().isoformat(),
                "version": "ui_presigned_only_v1",
                "function_name": context.function_name if context else "unknown"
            })

        return make_response(404, {"error": f"Route '{route}' not found"})

    except Exception as e:
        logger.error(f"💥 Critical error in lambda_handler: {e}", exc_info=True)
        return make_response(500, {"error": f"Critical Lambda error: {str(e)}", "success": False})
