from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import boto3
import os
import json
from utils.config_loader import load_config_from_s3
from pydantic import ValidationError
from models.models import IngestionPayload
from src.data_analysis import DocumentAnalyzer
from chat_history.chat_history import ChatHistory
import uuid
from datetime import datetime

app = FastAPI()

@app.get("/list-models")
async def list_models():
    """
    Returns available embedding and query models from the config YAML in S3.
    Reads CONFIG_BUCKET and CONFIG_KEY env vars for S3 location.
    """
    bucket = os.environ.get('CONFIG_BUCKET')
    key = os.environ.get('CONFIG_KEY')
    if not bucket or not key:
        return JSONResponse(status_code=500, content={"error": "Missing CONFIG_BUCKET or CONFIG_KEY environment variable."})
    try:
        config = load_config_from_s3(bucket, key)
        embedding_models = list(config.get('embedding_models', {}).keys())
        query_models = list(config.get('query_models', {}).keys())
        return {"embedding_models": embedding_models, "query_models": query_models}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to load config: {str(e)}"})

# List documents for the current user/project
@app.post("/list-documents")
async def list_documents(request: Request):
    """
    Returns a list of available documents for the given project/user/session.
    Expects JSON body with: project_id, user_id, session_id (optional).
    Lists files from both temp and approved S3 folders.
    """
    data = await request.json()
    project = data.get('project_id') or data.get('projectName')
    user = data.get('user_id') or data.get('userId')
    session = data.get('session_id') or data.get('sessionId')
    if not project or not user:
        return JSONResponse(status_code=400, content={"error": "project_id and user_id are required"})
    bucket = os.environ.get('UPLOAD_BUCKET')
    if not bucket:
        return JSONResponse(status_code=500, content={"error": "UPLOAD_BUCKET environment variable not set"})
    s3 = boto3.client('s3')
    # List from temp and approved folders
    prefixes = [
        f"uploads/tmp/{project}/{user}/",
        f"uploads/approved/{project}/{user}/"
    ]
    documents = []
    for prefix in prefixes:
        try:
            paginator = s3.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                for obj in page.get('Contents', []):
                    key = obj['Key']
                    # Only list files, not folders
                    if key.endswith('/'):
                        continue
                    name = key.split('/')[-1]
                    documents.append({
                        'name': name,
                        'key': key,
                        'location': 'temp' if '/tmp/' in key else 'approved'
                    })
        except Exception as e:
            continue
    return {"documents": documents}

# Add a FastAPI route for pre-signed S3 upload URL
@app.post("/get-presigned-url")
async def get_presigned_url(request: Request):
    """
    Returns a pre-signed S3 URL for uploading a file, using the correct bucket and folder structure.
    Expects JSON body with: fileName, projectName, userId, and optionally sessionId.
    Bucket name is taken from UPLOAD_BUCKET env var (required).
    S3 key: uploads/tmp/{projectName}/{userId}/{sessionId}/{fileName} if sessionId is present, else without sessionId.
    """
    data = await request.json()
    file_name = data.get('fileName')
    project_name = data.get('projectName')
    user_id = data.get('userId')
    session_id = data.get('sessionId') or data.get('session_id')
    if not file_name or not project_name or not user_id:
        return JSONResponse(status_code=400, content={"error": "fileName, projectName, and userId are required"})
    bucket = os.environ.get('UPLOAD_BUCKET')
    if not bucket:
        return JSONResponse(status_code=500, content={"error": "UPLOAD_BUCKET environment variable not set"})
    # Build S3 key structure, optionally including session_id
    if session_id:
        s3_key = f"uploads/tmp/{project_name}/{user_id}/{session_id}/{file_name}"
    else:
        s3_key = f"uploads/tmp/{project_name}/{user_id}/{file_name}"
    s3 = boto3.client('s3')
    try:
        url = s3.generate_presigned_url(
            ClientMethod='put_object',
            Params={'Bucket': bucket, 'Key': s3_key},
            ExpiresIn=3600
        )
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to generate pre-signed URL: {str(e)}"})
    return {"url": url, "key": s3_key, "bucket": bucket}

def handle_analyze_document(event, payload):
    """
    Handler for analyzing a document directly from S3 bucket/key in the payload.
    Expects 's3_bucket' and 's3_key' in the payload.
    Validates payload using AnalyzeDocumentPayload.
    """
    from models.models import AnalyzeDocumentPayload
    from pydantic import ValidationError
    try:
        validated = AnalyzeDocumentPayload(**payload)
    except ValidationError as e:
        return {
            'statusCode': 400,
            'body': f"Payload validation error: {e.json()}"
        }
    s3_bucket = validated.s3_bucket
    s3_key = validated.s3_key
    try:
        analysis_result = analyze_document_from_ingest_response({'s3_bucket': s3_bucket, 's3_key': s3_key})
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f'Error during document analysis: {str(e)}'
        }
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Document analysis complete.',
            'analysis_summary': analysis_result
        })
    }

def handle_ingest_data(event, payload):
    from models.models import IngestionPayload
    from pydantic import ValidationError
    try:
        validated = IngestionPayload(**payload)
    except ValidationError as e:
        return {
            'statusCode': 400,
            'body': f"Payload validation error: {e.json()}"
        }
    user_content = payload.get('user_query', 'Document ingestion and analysis request')
    user_message_id = log_chat_history(
        event=event,
        payload=payload,
        role='user',
        content=user_content
    )
    ingest_result = data_ingest(event)
    if ingest_result.get('statusCode', 500) != 200:
        return ingest_result
    try:
        ingest_body = ingest_result.get('body', '{}')
        if isinstance(ingest_body, str):
            try:
                ingest_body_json = json.loads(ingest_body)
            except json.JSONDecodeError:
                ingest_body_json = {'body': ingest_body}
        else:
            ingest_body_json = ingest_body
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f'Error parsing ingestion Lambda response: {str(e)}'
        }
    try:
        analysis_result = analyze_document_from_ingest_response(ingest_body_json)
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f'Error during document analysis: {str(e)}'
        }
    llm_content = f"Data ingestion and analysis complete. {json.dumps(analysis_result)}"
    # If document_type is present, include it in metadata
    metadata = None
    if isinstance(analysis_result, dict) and 'document_type' in analysis_result:
        metadata = {'document_type': analysis_result['document_type']}
    log_chat_history(
        event=event,
        payload=payload,
        role='assistant',
        content=llm_content,
        reply_to=user_message_id,
        metadata=metadata
    )
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Data ingestion and analysis complete.',
            'analysis_summary': analysis_result
        })
    }

def handle_compare_documents(event, payload):
    from models.models import CompareDocumentsPayload, DocumentComparisonInput
    from pydantic import ValidationError
    try:
        validated = CompareDocumentsPayload(**payload)
    except ValidationError as e:
        return {
            'statusCode': 400,
            'body': f"Payload validation error: {e.json()}"
        }
    doc1_info = payload.get('document_1', {})
    doc2_info = payload.get('document_2', {})
    s3_bucket = doc1_info.get('s3_bucket')
    s3_key_1 = doc1_info.get('s3_key')
    s3_key_2 = doc2_info.get('s3_key')
    if not (s3_bucket and s3_key_1 and s3_key_2):
        return {
            'statusCode': 400,
            'body': 'Missing S3 bucket or keys for document comparison.'
        }
    s3 = boto3.client('s3')
    try:
        obj1 = s3.get_object(Bucket=s3_bucket, Key=s3_key_1)
        doc1_text = obj1['Body'].read().decode('utf-8')
        obj2 = s3.get_object(Bucket=s3_bucket, Key=s3_key_2)
        doc2_text = obj2['Body'].read().decode('utf-8')
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f'Error downloading documents from S3: {str(e)}'
        }
    from src.document_comparator import DocumentComparator
    comparator = DocumentComparator()
    input_data = DocumentComparisonInput(document_1=doc1_text, document_2=doc2_text)
    try:
        comparison_result = comparator.compare_documents(input_data)
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f'Error during document comparison: {str(e)}'
        }
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': 'Document comparison complete.',
            'comparison_result': comparison_result
        })
    }

def log_chat_history(
    event: dict,
    payload: dict,
    role: str,
    content: str,
    reply_to: str = None,
    metadata: dict = None
):
    """
    Logs a single chat message (user or assistant) to DynamoDB chat history.
    Extracts project_id, user_id, and session_id from event/payload.
    Generates a unique message_id. If role is 'assistant' and reply_to is provided, links to user message.
    """
    import uuid
    chat_history = ChatHistory()
    project_id = payload.get('project_id') or payload.get('project_name') or event.get('project_id') or event.get('project_name')
    user_id = payload.get('user_id') or event.get('user_id')
    session_id = payload.get('session_id') or event.get('session_id')
    message_id = str(uuid.uuid4())
    chat_history.append_message(
        project_id=project_id,
        user_id=user_id,
        session_id=session_id,
        role=role,
        content=content,
        message_id=message_id,
        reply_to=reply_to,
        metadata=metadata
    )
    return message_id

def analyze_document_from_ingest_response(ingest_body_json):
    """
    Accepts the full ingestion Lambda response JSON, extracts s3_bucket and s3_key,
    downloads the document, and analyzes it.
    """
    s3_bucket = ingest_body_json.get('s3_bucket')
    s3_key = ingest_body_json.get('s3_key')
    if not s3_bucket or not s3_key:
        raise ValueError('Missing s3_bucket or s3_key in ingestion Lambda response.')
    from utils.document_type_utils import detect_document_type, extract_text_from_document
    import boto3
    s3 = boto3.client('s3')
    doc_type = detect_document_type(s3_bucket, s3_key, s3_client=s3)
    document_text = extract_text_from_document(s3_bucket, s3_key, doc_type, s3_client=s3)
    analyzer = DocumentAnalyzer()
    analysis_result = analyzer.analyze_document(document_text)
    # Add detected document type to result
    return {
        'document_type': doc_type,
        'analysis': analysis_result
    }

def data_ingest(event):
    payload = event.get('payload', {})
    # Ensure session_id is present in the payload
    session_id = payload.get('session_id') or event.get('session_id')
    if not session_id:
        return {
            'statusCode': 400,
            'body': 'Missing session_id in payload.'
        }
    payload['session_id'] = session_id
    try:
        validated = IngestionPayload(**payload)
    except ValidationError as e:
        return {
            'statusCode': 400,
            'body': f"Payload validation error: {e.json()}"
        }
    # Call the local ingestion logic directly
    from src.data_ingestion import ingest_document
    result = ingest_document(payload)
    # Validate with IngestionResponse
    from models.models import IngestionResponse
    if not isinstance(result, IngestionResponse):
        result = IngestionResponse(**result)
    return result.dict()

def lambda_handler(event, context):
    bucket = os.environ.get('CONFIG_BUCKET')
    key = os.environ.get('CONFIG_KEY')
    if not bucket or not key:
        return {
            'statusCode': 500,
            'body': 'Missing CONFIG_BUCKET or CONFIG_KEY environment variable.'
        }
    try:
        config = load_config_from_s3(bucket, key)
        # Extract session_id from event and log or process as needed
        session_id = event.get('session_id')
        if session_id:
            # Optionally log or store session_id for tracking
            pass
        action = event.get('action')
        payload = event.get('payload', {})
        # Log user message if present
        if action == 'ingest_data':
            user_content = payload.get('user_query', 'Document ingestion and analysis request')
            log_chat_history(
                event=event,
                payload=payload,
                role='user',
                content=user_content
            )
        # Action dispatch table
        action_handlers = {
            'ingest_data': handle_ingest_data,
            'compare_documents': handle_compare_documents,
            'analyze_document': handle_analyze_document,
            'rag_query': handle_rag_query,
        }
        handler = action_handlers.get(action)
        if handler:
            return handler(event, payload)
        else:
            return {
                'statusCode': 400,
                'body': 'Unknown action.'
            }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f'Error in lambda_handler: {str(e)}'
        }

# --- RAG handler ---
def handle_rag_query(event, payload):
    """
    Handler for Retrieval-Augmented Generation (RAG) queries.
    Expects payload with at least 'query' (user question) and optionally other metadata.
    Stores both the user query and RAG result as chat history messages, linking them via reply_to.
    Passes recent chat history as context to the RAG pipeline if available.
    """
    try:
        from rag.rag_pipeline import run_rag_pipeline
        query = payload.get('query')
        if not query:
            return {
                'statusCode': 400,
                'body': 'Missing query in payload.'
            }
        project_id = payload.get('project_id')
        user_id = payload.get('user_id')
        session_id = payload.get('session_id')
        chat_history = None
        user_message_id = str(uuid.uuid4())
        recent_messages = None
        if project_id and user_id and session_id:
            chat_history = ChatHistory()
            # Fetch last 10 messages for this session
            history_dict = chat_history.get_recent_history(session_id, limit=10)
            recent_messages = history_dict.get('messages', [])
            # Store user query as a message
            chat_history.append_message(
                project_id=project_id,
                user_id=user_id,
                session_id=session_id,
                role='user',
                content=query,
                message_id=user_message_id,
                metadata={
                    'source': 'user',
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }
            )
        # Run RAG pipeline, passing recent messages as context if available
        rag_result = run_rag_pipeline(query=query, payload=payload, chat_history=recent_messages)
        # Store RAG result as assistant message, linking to user query
        if chat_history:
            chat_history.append_message(
                project_id=project_id,
                user_id=user_id,
                session_id=session_id,
                role='assistant',
                content=rag_result if isinstance(rag_result, str) else str(rag_result),
                message_id=str(uuid.uuid4()),
                reply_to=user_message_id,
                metadata={
                    'source': 'rag_pipeline',
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }
            )
        return {
            'statusCode': 200,
            'body': rag_result
        }
    except Exception as e:
        return {
            'statusCode': 500,
            'body': f'Error in handle_rag_query: {str(e)}'
        }