
import os
import boto3
import hashlib
import json
from botocore.exceptions import ClientError
from datetime import datetime
import tempfile
from utils
from ..utils.utils import CustomLogger, CustomException
#from models.models import IngestionResponse
logger = CustomLogger(__name__)
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3')
METADATA_TABLE = os.environ.get('METADATA_TABLE')
DOCUMENTS_S3_BUCKET = os.environ.get('DOCUMENTS_S3_BUCKET')
CONTENT_HASH_KEY = os.environ.get('CONTENT_HASH_KEY', 'content_hash')
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

def lambda_handler(event, context):
    """
    Main Lambda handler for document ingestion.
    Delegates to ingest_document(payload).
    """
    payload = event if isinstance(event, dict) else json.loads(event)
    response = ingest_document(payload)
    # Validate response with Pydantic model (IngestionResponse)
    if not isinstance(response, IngestionResponse):
        response = IngestionResponse(**response)
    return response

def ingest_document(payload):
    """
    High-level sequence of steps for document ingestion:
    1. Validate required fields in the payload.
    2. Download the file from S3 using the provided key.
    3. Compute a content hash of the file for deduplication.
    4. Create and check metadata in DynamoDB to prevent duplicates.
    5. If not a duplicate, extract text, generate embeddings, and store them in the vector database.
    6. Update DynamoDB with the new metadata after successful vector DB upsert.
    7. Move the file from the temp folder to the documents folder in S3, preserving folder structure.
    """
    s3_bucket = DOCUMENTS_S3_BUCKET
    s3_key = payload.get('s3_key')
    session_id = payload.get('session_id')
    project_name = payload.get('project_name')
    user_id = payload.get('user_id')
    # Validate required fields
    if not all([s3_bucket, s3_key, session_id, project_name, user_id]):
        logger.error('Missing required fields in payload.')
        return IngestionResponse(statusCode=400, body='Missing required fields.')
    # Download file from S3
    try:
        logger.info(f"Downloading file {s3_key} from bucket {s3_bucket}")
        s3_obj = s3.get_object(Bucket=s3_bucket, Key=s3_key)
        file_bytes = s3_obj['Body'].read()
        logger.info(f"Successfully downloaded file {s3_key}")
    except ClientError as e:
        logger.error(f"Error fetching file from S3: {str(e)}")
        return IngestionResponse(statusCode=500, body=f'Error fetching file from S3: {str(e)}')
    # Compute content hash
    content_hash = compute_content_hash(file_bytes)
    # Create metadata and check for duplicates
    try:
        logger.info("Creating and checking metadata for duplicates")
        ingest_source = payload.get('ingest_source') or 'user_upload'
        source_path = payload.get('source_path') or 'UI'
        embedding_model = payload.get('embedding_model') or 'unknown-embedding-model'
        metadata, (any_exists, exact_exists) = create_and_check_metadata(
            temp_s3_key, project_name, user_id, content_hash,
            session_id, ingest_source, source_path, embedding_model,
            ddb_table=METADATA_TABLE,
            content_hash_key="content_hash"
        )

        if any_exists:
            logger.warning(f"Duplicate detected for {doc_loc}")
            return IngestionResponse(
                statusCode=409,
                body=f"Duplicate data already exists: {doc_loc}",
                s3_bucket=s3_bucket,
                s3_key=doc_s3_key
            )
    except Exception as e:
        logger.error(f"Error querying DynamoDB: {str(e)}")
        return IngestionResponse(statusCode=500, body=f'Error querying DynamoDB: {str(e)}')
    if exists:
        logger.warning('Duplicate data already exists in our vector database.')
        return IngestionResponse(statusCode=409, body='Duplicate data already exists in our vector database.')
    # Extract text, generate embeddings, and push to vector DB
    try:
        logger.info("Processing and storing embeddings")
        pipeline = PDFIngestionPipeline()
        pipeline.process_and_store(file_bytes, metadata)
    except Exception as e:
        logger.error(f"Error processing and storing embeddings: {str(e)}")
        return IngestionResponse(statusCode=500, body=f'Error processing and storing embeddings: {str(e)}')
    # Only after successful vector DB upsert, update DynamoDB
    try:
        logger.info("Updating DynamoDB with new metadata")
        table = dynamodb.Table(METADATA_TABLE)
        table.put_item(Item=metadata)
    except Exception as e:
        logger.error(f"Error writing to DynamoDB: {str(e)}")
        return IngestionResponse(statusCode=500, body=f'Error writing to DynamoDB: {str(e)}')
    # Move file from temp to Documents folder in S3
    try:
        temp_key = s3_key  # assuming s3_key is the temp location
        # Replace only the first occurrence of 'temp/' with 'documents/' to preserve subfolder structure
        if temp_key.startswith('temp/'):
            documents_key = 'documents/' + temp_key[len('temp/'):]
        else:
            # If not starting with temp/, try to replace first occurrence anywhere
            documents_key = temp_key.replace('temp/', 'documents/', 1)
        move_file_s3_temp_to_documents(s3_bucket, temp_key, documents_key)
    except Exception as e:
        logger.error(f"Error moving file in S3: {str(e)}")
        return IngestionResponse(statusCode=500, body=f'Error moving file in S3: {str(e)}')
    logger.info('Document ingested, embeddings stored, metadata updated, and file moved.')
    # Set ingest_source and source_path for UI uploads if not provided
    ingest_source = payload.get('ingest_source') or 'user_upload'
    source_path = payload.get('source_path') or 'UI'
    return IngestionResponse(
        statusCode=201,
        body='Document ingested, embeddings stored, metadata updated, and file moved.',
        s3_bucket=s3_bucket,
        s3_key=documents_key,
        ingest_source=ingest_source,
        source_path=source_path,
        embedding_model=embedding_model
    )
