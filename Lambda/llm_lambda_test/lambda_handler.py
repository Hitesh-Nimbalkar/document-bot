import boto3
import os
import json
from datetime import datetime
from pydantic import ValidationError

from utils.config_loader import get_config
from models.models import IngestionPayload, IngestionResponse
from src.data_ingestion import ingest_document
from utils.document_type_utils import detect_document_type, extract_text_from_document
from chat_history.chat_history import log_chat_history
from src.data_analysis import DocumentAnalyzer


def handle_ingest_data(event, payload):
    """
    Handles ingestion + analysis in one flow
    """
    
    import hashlib
    # -----------------------------
    # Validate payload
    # -----------------------------
    try:
        validated = IngestionPayload(**payload)
    except ValidationError:
        return {"statusCode": 400, "body": "Invalid ingestion payload."}

    # -----------------------------
    # Log user request
    # -----------------------------
    user_content = payload.get("user_query", "Document ingestion and analysis request")
    user_message_id = log_chat_history(event, payload, "user", user_content)

    # -----------------------------
    # Run ingestion
    # -----------------------------
    session_id = payload.get("session_id") or event.get("session_id")
    if not session_id:
        return {"statusCode": 400, "body": "Missing session_id in payload."}
    payload["session_id"] = session_id

    try:
        ingest_result = ingest_document(payload)
        if not isinstance(ingest_result, IngestionResponse):
            ingest_result = IngestionResponse(**ingest_result)
    except Exception as e:
        return {"statusCode": 500, "body": f"Error during ingestion: {str(e)}"}

    ingest_dict = ingest_result.dict()
    print("Ingestion result:", ingest_dict)

    # -----------------------------
    # Analysis
    # -----------------------------
    try:
        s3_bucket = ingest_dict.get("s3_bucket")
        s3_key = ingest_dict.get("s3_key")
        if not s3_bucket or not s3_key:
            raise ValueError("Missing s3_bucket or s3_key in ingestion response.")

        s3 = boto3.client("s3")
        doc_type = detect_document_type(s3_bucket, s3_key, s3_client=s3)
        document_text = extract_text_from_document(s3_bucket, s3_key, doc_type, s3_client=s3)

        analyzer = DocumentAnalyzer()
        analysis_result = analyzer.analyze_document(document_text)
    except Exception as e:
        return {"statusCode": 500, "body": f"Error during document analysis: {str(e)}"}

    # -----------------------------
    # Log assistant reply
    # -----------------------------
    llm_content = f"Data ingestion and analysis complete. {json.dumps(analysis_result)}"
    chat_history_metadata = {"document_type": doc_type} if doc_type else None
    log_chat_history(event, payload, "assistant", llm_content, reply_to=user_message_id, metadata=chat_history_metadata)

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Data ingestion and analysis complete.",
            "analysis_summary": {
                "document_type": doc_type,
                "analysis": analysis_result,
            },
        }),
    }


def lambda_handler(event, context):
    """
    AWS Lambda entry point
    """
    try:
        config_bucket = os.environ.get("CONFIG_BUCKET")
        config_key = os.environ.get("CONFIG_KEY")
        if not config_bucket or not config_key:
            print("CONFIG_BUCKET or CONFIG_KEY missing, skipping config load")
        config = get_config()
    except Exception as e:
        return {"statusCode": 500, "body": f"Error loading config: {str(e)}"}

    try:
        payload = event.get("payload", event)
        print("Executing data ingestion with payload:", json.dumps(payload))
        return handle_ingest_data(event, payload)
    except Exception as e:
        return {"statusCode": 500, "body": f"Error in lambda_handler: {str(e)}"}
