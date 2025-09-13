# Standard Library
from datetime import datetime
from typing import Optional, List, Tuple
import uuid
import os

# Pydantic
from pydantic import BaseModel

# AWS SDK
import boto3
from boto3.dynamodb.conditions import Key

# Custom Utilities
from utils.logger import CustomLogger, CustomException

# Initialize logger
logger = CustomLogger(__name__)
dynamodb = boto3.resource("dynamodb")


# ---------------------------
# Pydantic Metadata Model
# ---------------------------
class MetadataModel(BaseModel):
    document_id: str
    chunk_id: Optional[str] = None
    project_name: str
    user_id: str
    session_id: Optional[str] = None

    # Storage
    s3_key: str
    filename: str
    file_type: str
    file_size: int

    # Processing
    embedding_model: str  # ✅ required
    ingest_source: Optional[str] = None
    source_path: Optional[str] = None
    tags: Optional[List[str]] = None

    # Audit
    upload_timestamp: str
    content_hash: str

    # Lifecycle
    status: str = "uploaded"  # uploaded | ingested | failed


# ---------------------------
# Builder
# ---------------------------
def build_metadata(
    s3_key: str,
    project_name: str,
    user_id: str,
    content_hash: str,
    session_id: Optional[str] = None,
    ingest_source: Optional[str] = None,
    source_path: Optional[str] = None,
    embedding_model: str = None,   # ✅ make explicit
    filename: Optional[str] = None,
    file_type: Optional[str] = None,
    file_size: Optional[int] = None,
    chunk_id: Optional[str] = None,
) -> MetadataModel:
    """
    Build metadata object for DynamoDB + Vector DB.
    """
    logger.debug(f"⚙️ Building metadata for s3_key={s3_key}, project={project_name}, user={user_id}")

    if not embedding_model:
        logger.error("❌ embedding_model missing in build_metadata")
        raise CustomException("Missing embedding_model in build_metadata")

    metadata_obj = MetadataModel(
        document_id=str(uuid.uuid4()),
        chunk_id=chunk_id,
        project_name=project_name,
        user_id=user_id,
        session_id=session_id,
        s3_key=s3_key,
        filename=filename or os.path.basename(s3_key),
        file_type=file_type or "unknown",
        file_size=file_size or 0,
        embedding_model=embedding_model,
        ingest_source=ingest_source,
        source_path=source_path,
        tags=[source_path, ingest_source] if source_path or ingest_source else None,
        upload_timestamp=datetime.utcnow().isoformat(),
        content_hash=content_hash,
        status="uploaded",
    )

    logger.info(f"✅ Metadata built successfully for {s3_key}")
    logger.debug(f"Metadata object: {metadata_obj.dict()}")
    return metadata_obj


# ---------------------------
# Duplicate Check
# ---------------------------
def check_metadata_exists(
    content_hash: str,
    ddb_table: str,
    embedding_model: Optional[str] = None,
) -> Tuple[bool, bool]:
    """
    Check if document with same content_hash exists.
    Uses GSI on content_hash (to avoid costly scans).
    Returns: (any_exists, exact_exists)
    """
    logger.debug(f"🔍 Checking duplicates in table={ddb_table} for hash={content_hash}")

    table = dynamodb.Table(ddb_table)

    try:
        response = table.query(
            IndexName="content_hash-index",  # GSI required
            KeyConditionExpression=Key("content_hash").eq(content_hash),
        )
        items = response.get("Items", [])
        logger.debug(f"Query returned {len(items)} items for content_hash={content_hash}")

        any_exists = bool(items)

        exact_exists = False
        if embedding_model:
            exact_exists = any(
                item.get("embedding_model") == embedding_model for item in items
            )
            logger.debug(f"Checked for exact embedding_model={embedding_model}: {exact_exists}")

        logger.info(
            f"Duplicate check result → any_exists={any_exists}, exact_exists={exact_exists}"
        )
        return any_exists, exact_exists

    except Exception as e:
        logger.error(f"❌ Error querying DynamoDB for content_hash={content_hash}: {str(e)}", exc_info=True)
        raise CustomException(f"Error checking metadata: {str(e)}")


# ---------------------------
# Create + Check
# ---------------------------
def create_and_check_metadata(
    s3_key: str,
    project_name: str,
    user_id: str,
    content_hash: str,
    session_id: Optional[str] = None,
    ingest_source: Optional[str] = None,
    source_path: Optional[str] = None,
    embedding_model: Optional[str] = None,
    filename: Optional[str] = None,
    file_type: Optional[str] = None,
    file_size: Optional[int] = None,
    ddb_table: str = None,
) -> Tuple[dict, dict]:
    """
    Build metadata, check duplicates, return both.
    Returns:
        metadata (dict), exists ({"any_exists": bool, "exact_exists": bool})
    """
    logger.info(f"🚀 Creating + checking metadata for file={filename or s3_key}")

    if not embedding_model:
        logger.error("❌ embedding_model missing in create_and_check_metadata")
        raise CustomException("Missing embedding_model in create_and_check_metadata")

    metadata_obj = build_metadata(
        s3_key,
        project_name,
        user_id,
        content_hash,
        session_id,
        ingest_source,
        source_path,
        embedding_model,
        filename,
        file_type,
        file_size,
    )
    metadata = metadata_obj.dict()
    metadata["content_hash"] = content_hash  # Keep top-level for GSI

    logger.debug(f"📦 Metadata prepared → {metadata}")

    any_exists, exact_exists = check_metadata_exists(
        content_hash, ddb_table, embedding_model
    )
    exists = {"any_exists": any_exists, "exact_exists": exact_exists}

    logger.info(f"✅ Final metadata ready (exists={exists}) for file={filename or s3_key}")
    return metadata, exists