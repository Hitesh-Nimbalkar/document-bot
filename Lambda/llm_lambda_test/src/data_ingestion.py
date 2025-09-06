
import os
import json
import boto3
import hashlib
import tempfile
from datetime import datetime
from botocore.exceptions import ClientError
from utils.metadata import create_and_check_metadata
from utils.logger import CustomLogger, CustomException
from models.models import IngestionResponse
from vector_db.vector_db import PDFIngestionPipeline
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

logger = CustomLogger(__name__)
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')

METADATA_TABLE = os.environ.get('METADATA_TABLE')
DOCUMENTS_S3_BUCKET = os.environ.get('DOCUMENTS_S3_BUCKET')

# ---------------------------
# Ingestion payload
# ---------------------------
class IngestionPayload(BaseModel):
    session_id: str
    doc_loc: str
    project_name: str
    user_id: str
    ingest_source: Optional[str] = None
    source_path: Optional[str] = None
    embedding_model: Optional[str] = None
    

# ---------------------------
# Ingestion response
# ---------------------------
class IngestionResponse(BaseModel):
    statusCode: int
    body: str
    s3_bucket: Optional[str] = None
    s3_key: Optional[str] = None
    ingest_source: Optional[str] = None
    source_path: Optional[str] = None
    embedding_model: Optional[str] = None


def move_file_s3_temp_to_documents(s3_bucket: str, temp_key: str, documents_key: str):
    """
    Move a file from the temporary folder to the Documents folder in the same S3 bucket.
    Copies the file and then deletes the original from the temp folder.
    """
    try:
        logger.info(f"Copying file from {temp_key} to {documents_key} in bucket {s3_bucket}")
        s3.copy_object(Bucket=s3_bucket, CopySource={'Bucket': s3_bucket, 'Key': temp_key}, Key=documents_key)
        s3.delete_object(Bucket=s3_bucket, Key=temp_key)
        logger.info(f"Successfully moved file from {temp_key} to {documents_key}")
    except ClientError as e:
        logger.error(f"Error moving file in S3: {str(e)}")
        raise CustomException(f"Error moving file in S3: {str(e)}")
def compute_content_hash(file_bytes: bytes) -> str:
    """Compute SHA-256 hash of file bytes."""
    return hashlib.sha256(file_bytes).hexdigest()
def get_temporary_file_from_s3(s3_bucket: str, project_name: str, file_name: str) -> bytes:
    """
    Fetch a file from the S3 temporary folder for a specific project and return its content as bytes.
    """
    temp_key = f"temp/{project_name}/{file_name}"
    try:
        logger.info(f"Fetching file {temp_key} from bucket {s3_bucket}")
        s3_obj = s3.get_object(Bucket=s3_bucket, Key=temp_key)
        logger.info(f"Successfully fetched file {temp_key}")
        return s3_obj['Body'].read()
    except ClientError as e:
        logger.error(f"Error fetching temporary file from S3: {str(e)}")
        raise CustomException(f"Error fetching temporary file from S3: {str(e)}")

def ingest_document(payload):
    """
    High-level steps:
Validate fields in payload
Download from S3 temp
Compute hash
Create metadata + check duplicates
Store embeddings (future)
Update DynamoDB
Move file temp → documents
    """
    s3_bucket = DOCUMENTS_S3_BUCKET
    # Required fields
    session_id = payload.get('session_id')
    project_name = payload.get('project_name')
    user_id = payload.get('user_id')
    doc_loc = payload.get('doc_loc')
    if not all([s3_bucket, session_id, project_name, user_id, doc_loc]):
        logger.error('Missing required fields in payload.')
        return IngestionResponse(statusCode=400, body='Missing required fields.')
    # Build S3 keys
    temp_s3_key = f"project_data/uploads/temp/{project_name}/{doc_loc}"
    doc_s3_key = f"project_data/uploads/temp/documents/{project_name}/{doc_loc}"
    # Download file from S3
    try:
        logger.info(f"Downloading file {temp_s3_key} from bucket {s3_bucket}")
        s3_obj = s3.get_object(Bucket=s3_bucket, Key=temp_s3_key)
        file_bytes = s3_obj['Body'].read()
        logger.info(f"Successfully downloaded {temp_s3_key}")
    except ClientError as e:
        logger.error(f"Error fetching file from S3: {str(e)}")
        return IngestionResponse(statusCode=500, body=f'Error fetching file from S3: {str(e)}')
    # Compute content hash
    content_hash = compute_content_hash(file_bytes)
    # Metadata + deduplication
    try:
        logger.info("Creating and checking metadata for duplicates")
        ingest_source = payload.get('ingest_source') or 'user_upload'
        source_path = payload.get('source_path') or 'UI'
        embedding_model = payload.get('embedding_model') or 'dummy-embedding-model'
        metadata, exists = create_and_check_metadata(
            temp_s3_key, project_name, user_id, content_hash,
            session_id, ingest_source, source_path, embedding_model
        )
    except Exception as e:
        logger.error(f"Error querying DynamoDB: {str(e)}")
        return IngestionResponse(statusCode=500, body=f'Error querying DynamoDB: {str(e)}')
    if exists:
        logger.warning('Duplicate data already exists in vector DB.')
        return IngestionResponse(statusCode=409, body='Duplicate data already exists.')
    # (Future: process embeddings)
    # pipeline = PDFIngestionPipeline()
    # pipeline.process_and_store(file_bytes, metadata)
    # Write metadata → DynamoDB
    try:
        logger.info("Updating DynamoDB with new metadata")
        table = dynamodb.Table(METADATA_TABLE)
        table.put_item(Item=metadata)
    except Exception as e:
        logger.error(f"Error writing to DynamoDB: {str(e)}")
        return IngestionResponse(statusCode=500, body=f'Error writing to DynamoDB: {str(e)}')
    # Move file temp → documents
    try:
        move_file_s3_temp_to_documents(s3_bucket, temp_s3_key, doc_s3_key)
    except Exception as e:
        logger.error(f"Error moving file in S3: {str(e)}")
        return IngestionResponse(statusCode=500, body=f'Error moving file in S3: {str(e)}')
    logger.info('Document ingested, embeddings stored, metadata updated, and file moved.')
    return IngestionResponse(
        statusCode=201,
        body='Document ingested successfully.',
        s3_bucket=s3_bucket,
        s3_key=doc_s3_key,
        ingest_source=ingest_source,
        source_path=source_path,
        embedding_model=embedding_model
    )
