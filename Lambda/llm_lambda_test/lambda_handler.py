# lambda_handler.py
import json
import os
from pydantic import ValidationError

from utils.config_loader import get_config
from chat_history.chat_history import log_chat_history
from models.models import IngestionPayload, IngestionResponse, DocumentComparisonInput
from src.data_ingestion import ingest_document
from src.data_analysis import DocumentAnalyzer
from src.document_comparator import DocumentComparator
from utils.document_type_utils import detect_document_type, extract_text_from_document


def handle_ingest_route(event, payload):
    """
    Handles the /ingest_data route: ingestion + analysis
    """
    # Validate payload
    try:
        validated = IngestionPayload(**payload)
    except ValidationError:
        return {"statusCode": 400, "body": "Invalid ingestion payload."}

    # Log user request
    user_content = payload.get("user_query", "Document ingestion and analysis request")
    user_message_id = log_chat_history(event, payload, "user", user_content)

    # Ensure session_id
    session_id = payload.get("session_id") or event.get("session_id")
    if not session_id:
        return {"statusCode": 400, "body": "Missing session_id in payload."}
    payload["session_id"] = session_id

    # Run ingestion
    try:
        ingest_result = ingest_document(payload)
        if not isinstance(ingest_result, IngestionResponse):
            ingest_result = IngestionResponse(**ingest_result)
    except Exception as e:
        return {"statusCode": 500, "body": f"Error during ingestion: {str(e)}"}

    ingest_dict = ingest_result.dict()

    # Run analysis
    try:
        s3_bucket = ingest_dict.get("s3_bucket")
        s3_key = ingest_dict.get("s3_key")
        if not s3_bucket or not s3_key:
            raise ValueError("Missing s3_bucket or s3_key in ingestion response.")

        s3_client = boto3.client("s3")
        doc_type = detect_document_type(s3_bucket, s3_key, s3_client=s3_client)
        document_text = extract_text_from_document(s3_bucket, s3_key, doc_type, s3_client=s3_client)

        analyzer = DocumentAnalyzer()
        analysis_result = analyzer.analyze_document(document_text)
    except Exception as e:
        return {"statusCode": 500, "body": f"Error during document analysis: {str(e)}"}

    # Log assistant response
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


def handle_doc_compare_route(event, payload):
    """
    Handles the /doc_compare route
    """
    # Validate payload
    if "document_1" not in payload or "document_2" not in payload:
        return {"statusCode": 400, "body": "Both 'document_1' and 'document_2' must be provided."}

    session_id = payload.get("session_id") or event.get("session_id")

    # Initialize comparator
    try:
        comparator = DocumentComparator()
        comparison_input = DocumentComparisonInput(
            document_1=payload["document_1"],
            document_2=payload["document_2"]
        )
        comparison_result = comparator.compare_documents(comparison_input)
    except Exception as e:
        return {"statusCode": 500, "body": f"Error during document comparison: {str(e)}"}

    # Log chat history
    user_message_id = payload.get("message_id") or "user_" + str(session_id)
    log_chat_history(event, payload, role="user", content="Requesting document comparison", metadata={"comparison_performed": True})
    log_chat_history(event, payload, role="assistant", content=f"Document comparison result: {comparison_result}", reply_to=user_message_id, metadata={"comparison_performed": True})

    return {
        "statusCode": 200,
        "body": json.dumps(comparison_result)
    }


def lambda_handler(event, context):
    """
    AWS Lambda entry point with routing for:
    1. /ingest_data
    2. /doc_compare
    """
    try:
        # Load config
        config_bucket = os.environ.get("CONFIG_BUCKET")
        config_key = os.environ.get("CONFIG_KEY")
        if config_bucket and config_key:
            config = get_config()
    except Exception as e:
        return {"statusCode": 500, "body": f"Error loading config: {str(e)}"}

    try:
        # Routing
        route = event.get("route")
        payload = event.get("payload", event)

        if route == "/ingest_data":
            return handle_ingest_route(event, payload)
        elif route == "/doc_compare":
            return handle_doc_compare_route(event, payload)
        else:
            return {
                "statusCode": 404,
                "body": f"Route '{route}' not found. Use '/ingest_data' or '/doc_compare'."
            }
    except Exception as e:
        return {"statusCode": 500, "body": f"Error in lambda_handler: {str(e)}"}
