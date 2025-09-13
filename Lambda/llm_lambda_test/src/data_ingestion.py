import os
import boto3
import hashlib
from botocore.exceptions import ClientError
from typing import List, Dict, Any, Union

from utils.metadata import create_and_check_metadata
from utils.logger import CustomLogger, CustomException
from models.models import IngestionResponse, BatchIngestionResponse
from vector_db.vector_db import PDFIngestionPipeline  # embedding pipeline

logger = CustomLogger(__name__)
import uuid
from typing import Dict, Any, List

from utils.logger import CustomLogger
from .qdrant_vector_db import QdrantVectorDB  # assuming you renamed Qdrant wrapper
from utils.text_splitter import split_into_chunks   # you’ll need a helper
from utils.embedding import get_embeddings          # wrapper for your LLM embeddings
from metadata import MetadataModel
from utils.embeddings import get_embeddings ,split_into_chunks
logger = CustomLogger("PDFIngestionPipeline")



dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")

METADATA_TABLE = os.environ.get("METADATA_TABLE")
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET")
from pydantic import BaseModel
from typing import Optional, List, Dict, Any


# ---------------------------
# Ingestion Payload
# ---------------------------
class IngestionPayload(BaseModel):
    session_id: str
    project_name: str
    user_id: str
    doc_loc: Optional[str] = None              # single file
    doc_locs: Optional[List[str]] = None       # multiple files
    ingest_source: Optional[str] = None
    source_path: Optional[str] = None
    embedding_model: Optional[str] = None


# ---------------------------
# Ingestion Response (per doc)
# ---------------------------
class IngestionResponse(BaseModel):
    statusCode: int
    body: str
    s3_bucket: Optional[str] = None
    s3_key: Optional[str] = None
    ingest_source: Optional[str] = None
    source_path: Optional[str] = None
    embedding_model: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None  # optional extra info


# ---------------------------
# Batch Response (wrapper)
# ---------------------------
class BatchIngestionResponse(BaseModel):
    results: List[IngestionResponse]
    summary: Optional[Dict[str, Any]] = None   # quick stats


class PDFIngestionPipeline:
    def __init__(self):
        self.vector_db = QdrantVectorDB()

    def process_and_store(self, file_bytes: bytes, metadata: Dict[str, Any]) -> bool:
        """
        Extract text, chunk, embed, and store in Qdrant.
        """
        try:
            # 1. Extract text (for now assume input is already text)
            # TODO: use PyPDF2, python-docx, etc. based on file_type in metadata
            text = file_bytes.decode("utf-8", errors="ignore")

            # 2. Chunk text
            chunks = split_into_chunks(text, chunk_size=500)

            embeddings_to_upsert: List[Dict[str, Any]] = []
            for idx, chunk in enumerate(chunks):
                vector = get_embeddings(chunk, model_name=metadata.get("embedding_model"))

                chunk_id = str(idx)
                embeddings_to_upsert.append({
                    "id": f"{metadata['document_id']}_{chunk_id}",
                    "embedding": vector,
                    "metadata": {
                        **metadata,
                        "chunk_id": chunk_id,
                    },
                    "text": chunk,  # optional: controlled by STORE_TEXT_IN_VECTOR_DB
                })

            # 3. Upsert into Qdrant
            self.vector_db.upsert_embeddings(embeddings_to_upsert)
            logger.info(f"Ingested {len(chunks)} chunks into Qdrant for doc {metadata['document_id']}")
            return True

        except Exception as e:
            logger.error(f"Error in PDFIngestionPipeline: {e}", exc_info=True)
            return False

# ---------------------------
# Helper functions
# ---------------------------
def move_file_s3_temp_to_documents(s3_bucket: str, temp_key: str, documents_key: str):
    try:
        logger.info(f"Copying file from {temp_key} to {documents_key} in bucket {s3_bucket}")
        s3.copy_object(Bucket=s3_bucket, CopySource={"Bucket": s3_bucket, "Key": temp_key}, Key=documents_key)
        s3.delete_object(Bucket=s3_bucket, Key=temp_key)
        logger.info(f"Successfully moved file from {temp_key} to {documents_key}")
    except ClientError as e:
        logger.error(f"Error moving file in S3: {str(e)}")
        raise CustomException(f"Error moving file in S3: {str(e)}")


def compute_content_hash(file_bytes: bytes) -> str:
    return hashlib.sha256(file_bytes).hexdigest()


# ---------------------------
# Main ingestion function
# ---------------------------
def ingest_document(payload: dict) -> Union[IngestionResponse, BatchIngestionResponse]:
    """
    Validate payload, fetch file(s) from S3 temp, compute hash, check metadata,
    update DB, store embeddings, move file(s).
    Supports single or multiple documents.
    """
    s3_bucket = DOCUMENTS_S3_BUCKET
    session_id = payload.get("session_id")
    project_name = payload.get("project_name")
    user_id = payload.get("user_id")

    # Collect single or multiple file locations
    doc_locs: List[str] = []
    if payload.get("doc_loc"):
        doc_locs.append(payload["doc_loc"])
    if payload.get("doc_locs"):
        doc_locs.extend(payload["doc_locs"])

    if not all([s3_bucket, session_id, project_name, user_id]) or not doc_locs:
        logger.error("Missing required fields in payload.")
        return IngestionResponse(statusCode=400, body="Missing required fields.")

    # Prefixes from environment
    temp_prefix = os.getenv("TEMP_DATA_KEY")
    documents_prefix = os.getenv("DOCUMENTS_DATA_KEY")

    results: List[IngestionResponse] = []

    for doc_loc in doc_locs:
        try:
            # Build S3 keys
            temp_s3_key = f"{temp_prefix}/{project_name}/{doc_loc}"
            doc_s3_key = f"{documents_prefix}/{project_name}/{doc_loc}"
            logger.info(f"Constructed S3 keys: temp={temp_s3_key}, doc={doc_s3_key}")

            # File type validation
            if not doc_loc.lower().endswith((".pdf", ".docx", ".txt")):
                logger.warning(f"Unsupported file type for {doc_loc}")
                results.append(IngestionResponse(
                    statusCode=415,
                    body=f"Unsupported file type: {doc_loc}",
                    s3_bucket=s3_bucket,
                    s3_key=temp_s3_key
                ))
                continue

            # Download file
            logger.info(f"Downloading {temp_s3_key} from bucket {s3_bucket}")
            s3_obj = s3.get_object(Bucket=s3_bucket, Key=temp_s3_key)
            file_bytes = s3_obj["Body"].read()
            logger.info(f"Downloaded {temp_s3_key}")

            # Compute hash
            content_hash = compute_content_hash(file_bytes)

            # Metadata setup
            ingest_source = payload.get("ingest_source") or "user_upload"
            source_path = payload.get("source_path") or "UI"
            embedding_model = payload.get("embedding_model") or "dummy-embedding-model"

            metadata, exists = create_and_check_metadata(
                temp_s3_key, project_name, user_id, content_hash,
                session_id, ingest_source, source_path, embedding_model
            )

            if exists:
                logger.warning(f"Duplicate detected for {doc_loc}")
                results.append(IngestionResponse(
                    statusCode=409,
                    body=f"Duplicate data already exists: {doc_loc}",
                    s3_bucket=s3_bucket,
                    s3_key=doc_s3_key
                ))
                continue

            # Write metadata to DynamoDB
            table = dynamodb.Table(METADATA_TABLE)
            table.put_item(Item=metadata)

            # Embedding pipeline
            try:
                logger.info(f"Embedding {doc_loc} via PDFIngestionPipeline")
                pipeline = PDFIngestionPipeline()
                pipeline.process_and_store(file_bytes, metadata)
            except Exception as e:
                logger.error(f"Embedding pipeline failed for {doc_loc}: {e}")
                results.append(IngestionResponse(
                    statusCode=500,
                    body=f"Embedding pipeline failed: {doc_loc}",
                    s3_bucket=s3_bucket,
                    s3_key=doc_s3_key
                ))
                continue

            # Move file from temp → documents
            move_file_s3_temp_to_documents(s3_bucket, temp_s3_key, doc_s3_key)

            # Success response
            results.append(IngestionResponse(
                statusCode=201,
                body=f"Document ingested successfully: {doc_loc}",
                s3_bucket=s3_bucket,
                s3_key=doc_s3_key,
                ingest_source=ingest_source,
                source_path=source_path,
                embedding_model=embedding_model
            ))

        except Exception as e:
            logger.error(f"Unexpected error ingesting {doc_loc}: {e}")
            results.append(IngestionResponse(
                statusCode=500,
                body=f"Unexpected error ingesting {doc_loc}: {str(e)}",
                s3_bucket=s3_bucket
            ))

    # Summarize results
    summary = {
        "total": len(results),
        "succeeded": sum(1 for r in results if r.statusCode in (200, 201)),
        "duplicates": sum(1 for r in results if r.statusCode == 409),
        "unsupported": sum(1 for r in results if r.statusCode == 415),
        "errors": sum(1 for r in results if r.statusCode >= 500),
    }

    # Return batch response
    return BatchIngestionResponse(results=results, summary=summary)
