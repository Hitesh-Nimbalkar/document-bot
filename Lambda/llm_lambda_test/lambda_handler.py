import json
import os
import boto3
from pydantic import ValidationError

from utils.config_loader import get_config
from chat_history.chat_history import log_chat_history
from models.models import IngestionPayload, IngestionResponse, DocumentComparisonInput
from src.data_ingestion import ingest_document
from src.data_analysis import DocumentAnalyzer
from src.document_comparator import DocumentComparator
from utils.document_type_utils import detect_document_type, extract_text_from_document
from rag.rag_pipeline import RAGPipeline  # ✅ RAG pipeline
from utils.logger import CustomLogger , CustomException
import uuid
import datetime
from botocore.exceptions import ClientError

logger = CustomLogger(__name__)


s3 = boto3.client("s3")
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET")
TEMP_PREFIX = os.getenv("TEMP_DATA_KEY", "project-data/uploads/temp")

# Allowed file types
ALLOWED_EXTENSIONS = (".pdf", ".docx", ".txt")
MAX_FILE_SIZE_MB = 25   # optional limit

def handle_get_presigned_url(event, payload):
    project_name = payload.get("project_name")
    filename = payload.get("filename")
    content_type = payload.get("content_type", "application/octet-stream")
    file_size = payload.get("file_size", 0)  # frontend can send this

    if not project_name or not filename:
        return {"statusCode": 400, "body": "Missing project_name or filename"}

    # Validate extension
    if not filename.lower().endswith(ALLOWED_EXTENSIONS):
        msg = f"Unsupported file type: {filename}"
        logger.warning(msg)
        return {"statusCode": 415, "body": msg}

    # Validate file size if provided
    if file_size and file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        msg = f"File too large (max {MAX_FILE_SIZE_MB}MB): {filename}"
        logger.warning(msg)
        return {"statusCode": 413, "body": msg}

    # Generate unique key
    safe_name = filename.split("/")[-1].replace(" ", "_")
    file_key = f"{uuid.uuid4().hex}_{safe_name}"   # this will be doc_loc
    s3_key = f"{TEMP_PREFIX}/{project_name}/{file_key}"

    try:
        url = s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": DOCUMENTS_S3_BUCKET,
                "Key": s3_key,
                "ContentType": content_type
            },
            ExpiresIn=600  # 10 min expiry
        )
        return {"statusCode": 200, "body": json.dumps({"url": url, "doc_loc": file_key})}
    except ClientError as e:
        logger.error(f"Error creating presigned URL: {e}", exc_info=True)
        return {"statusCode": 500, "body": f"Error creating presigned URL: {str(e)}"}

def handle_ingest_route(event, payload):
    try:
        ingest_result = ingest_document(payload)
        if hasattr(ingest_result, "results"):  # BatchIngestionResponse
            body = {
                "summary": ingest_result.summary,
                "results": [r.dict() for r in ingest_result.results]
            }
            return {"statusCode": 200, "body": json.dumps(body)}
        else:
            return {"statusCode": ingest_result.statusCode, "body": json.dumps(ingest_result.dict())}
    except Exception as e:
        logger.error(f"Error in handle_ingest_route: {e}")
        return {"statusCode": 500, "body": f"Error in ingestion: {str(e)}"}

def handle_doc_compare_route(event, payload):
    """Handles the /doc_compare route"""
    if "document_1" not in payload or "document_2" not in payload:
        return {"statusCode": 400, "body": "Both 'document_1' and 'document_2' must be provided."}

    session_id = payload.get("session_id") or event.get("session_id")

    try:
        comparator = DocumentComparator()
        comparison_input = DocumentComparisonInput(
            document_1=payload["document_1"], document_2=payload["document_2"]
        )
        comparison_result = comparator.compare_documents(comparison_input)
    except Exception as e:
        return {"statusCode": 500, "body": f"Error during document comparison: {str(e)}"}

    user_message_id = payload.get("message_id") or "user_" + str(session_id)
    log_chat_history(event, payload, "user", "Requesting document comparison", {"comparison_performed": True})
    log_chat_history(event, payload, "assistant", f"Document comparison result: {comparison_result}",
                     reply_to=user_message_id, metadata={"comparison_performed": True})

    return {"statusCode": 200, "body": json.dumps(comparison_result)}

def handle_rag_query(event, payload):
    """Handles the /rag_query route: retrieval + generation with dynamic prompt_type"""
    query = payload.get("query")
    if not query:
        return {"statusCode": 400, "body": "Missing query text"}

    prompt_type = payload.get("prompt_type", "rag_query")  

    try:
        rag = RAGPipeline(prompt_type=prompt_type)
        result = rag.run(query)

        # Log with prompt_type
        user_message_id = log_chat_history(event, payload, "user", f"RAG query ({prompt_type}): {query}")
        log_chat_history(event, payload, "assistant", f"RAG answer: {json.dumps(result['answer'])}",
                         reply_to=user_message_id, metadata={"rag": True, "prompt_type": prompt_type})

        return {"statusCode": 200, "body": json.dumps(result)}
    except Exception as e:
        return {"statusCode": 500, "body": f"RAG query failed: {str(e)}"}

def lambda_handler(event, context):
    try:
        """event = {
    "route": "/ingest_data",
    "payload": {
        "session_id": "sess_123",
        "project_name": "demo_project",
        "user_id": "user_1",
        "doc_locs": ["uuid1_contract.pdf"],  # file already uploaded to temp S3
        "ingest_source": "ui",
        "source_path": "browser_upload",
        "embedding_model": "bedrock_default"
    }
}
"""
        route = event.get("route")
        payload = event.get("payload", event)
        if route == "/get_presigned_url":
            return handle_get_presigned_url(event, payload)
        elif route == "/ingest_data":
            return handle_ingest_route(event, payload)
        elif route == "/doc_compare":
            return handle_doc_compare_route(event, payload)
        elif route == "/rag_query":
            return handle_rag_query(event, payload)
        else:
            return {"statusCode": 404, "body": f"Route '{route}' not found."}
    except Exception as e:
        return {"statusCode": 500, "body": f"Error in lambda_handler: {str(e)}"}