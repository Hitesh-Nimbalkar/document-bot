# Standard Library
from datetime import datetime
from typing import Optional, List
import uuid
import os

# Pydantic
from pydantic import BaseModel

# AWS SDK
import boto3
from boto3.dynamodb.conditions import Attr

# Custom Utilities
from utils.logger import CustomLogger, CustomException

# Initialize logger
logger = CustomLogger(__name__)

# Initialize DynamoDB resource
dynamodb = boto3.resource('dynamodb')
# --- Nested Models ---
class UserInfo(BaseModel):
    id: str
    project: str
    session: Optional[str] = None

class StorageInfo(BaseModel):
    s3_key: str
    source_path: Optional[str] = None

class ProcessingInfo(BaseModel):
    embedding_model: Optional[str] = None
    ingest_source: Optional[str] = None
    preprocessing_steps: Optional[list[str]] = None

class AuditInfo(BaseModel):
    upload_timestamp: str
    content_hash: str

class VectorMetadata(BaseModel):
    backend: str = "qdrant"
    collection: str = "document_embeddings"
    vector_dimension: int = 1536
    embedding_model: Optional[str] = None
    distance_metric: str = "cosine"
    project: str
    user_id: str
    session: Optional[str] = None
    tags: Optional[List[str]] = None

class MetadataModel(BaseModel):
    document_id: str
    chunk_id: Optional[str] = None
    user: UserInfo
    storage: StorageInfo
    processing: Optional[ProcessingInfo] = None
    vector: Optional[VectorMetadata] = None
    audit: AuditInfo

# --- Builders ---
def build_metadata_dict(
    s3_key: str,
    project_name: str,
    user_id: str,
    content_hash: str,
    session_id: str = None,
    ingest_source: str = None,
    source_path: str = None,
    embedding_model: str = None
) -> MetadataModel:
    """
    Build and validate a nested metadata dictionary for DynamoDB using MetadataModel.
    """
    logger.info(f"Building nested metadata for s3_key={s3_key}, project={project_name}, user={user_id}")

    metadata_obj = MetadataModel(
        document_id=str(uuid.uuid4()),
        user=UserInfo(id=user_id, project=project_name, session=session_id),
        storage=StorageInfo(s3_key=s3_key, source_path=source_path),
        processing=ProcessingInfo(embedding_model=embedding_model, ingest_source=ingest_source),
        vector=VectorMetadata(
            embedding_model=embedding_model,
            project=project_name,
            user_id=user_id,
            session=session_id,
            tags=[source_path, ingest_source] if source_path or ingest_source else None  # optional mapping
        ),
        audit=AuditInfo(upload_timestamp=datetime.utcnow().isoformat(), content_hash=content_hash)
    )

    logger.info(f"Validated nested metadata object: {metadata_obj}")
    return metadata_obj

# --- Checks ---
def check_metadata_exists(content_hash: str, ddb_table=None, content_hash_key=None, embedding_model=None):
    """
    Check if (1) any document with the same content_hash exists,
    (2) if a document with the same content_hash AND embedding_model exists.
    """

    table = dynamodb.Table(ddb_table)

    try:
        logger.info(f"Checking for metadata in DynamoDB for content_hash: {content_hash}")

        # Any match on content_hash
        response_any = table.scan(
            FilterExpression=f"{content_hash_key} = :h",
            ExpressionAttributeValues={':h': content_hash}
        )
        any_exists = bool(response_any['Items'])
        logger.info(f"Any metadata exists: {any_exists}")

        # Exact match with embedding_model (stored under processing.embedding_model)
        exact_exists = False
        if embedding_model:
            response_exact = table.scan(
                FilterExpression=f"{content_hash_key} = :h AND processing.embedding_model = :e",
                ExpressionAttributeValues={':h': content_hash, ':e': embedding_model}
            )
            exact_exists = bool(response_exact['Items'])
            logger.info(f"Exact metadata exists: {exact_exists}")

    except Exception as e:
        logger.error(f"Error querying DynamoDB: {str(e)}")
        raise CustomException(f"Error querying DynamoDB: {str(e)}")

    return any_exists, exact_exists

# --- Wrapper ---
def create_and_check_metadata(
    s3_key: str,
    project_name: str,
    user_id: str,
    content_hash: str,
    session_id: str = None,
    ingest_source: str = None,
    source_path: str = None,
    embedding_model: str = None,
    ddb_table=None,
    content_hash_key=None
):
    """
    Build nested metadata and check if it exists in DynamoDB by content_hash and embedding_model.
    Returns (metadata_dict, (any_exists, exact_exists))
    """
    metadata_obj = build_metadata_dict(
        s3_key, project_name, user_id, content_hash,
        session_id, ingest_source, source_path, embedding_model
    )

    metadata = metadata_obj.dict()

    if content_hash_key != 'audit.content_hash':
        # remap key only if user config differs
        metadata[content_hash_key] = metadata['audit'].pop('content_hash')

    any_exists, exact_exists = check_metadata_exists(
        content_hash, ddb_table, content_hash_key=content_hash_key, embedding_model=embedding_model
    )

    logger.info(f"Final nested metadata dict for DynamoDB: {metadata}")
    return metadata, (any_exists, exact_exists)
