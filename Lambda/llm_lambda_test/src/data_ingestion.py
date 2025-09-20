# ingestion_pipeline.py
"""
PDF Ingestion Pipeline
----------------------
Handles document ingestion into Qdrant:
- Extract text, split into chunks
- Embed using Bedrock (via ModelLoader)
- Upsert into Qdrant
- Metadata handling + duplication check
- File management in S3
- Chat history logging
"""

# ======================================================
# Imports
# ======================================================
import os
import io
import uuid
import boto3
import hashlib
from typing import List, Dict, Any, Union, Optional

from botocore.exceptions import ClientError
from pydantic import BaseModel

from utils.metadata import MetadataManager, create_and_check_metadata
from utils.logger import CustomLogger, CustomException
from utils.split import split_into_chunks, detect_file_type, extract_text
from utils.model_loader import ModelLoader, BedrockProvider

from vector_db.vector_db import QdrantVectorDB
from chat_history.chat_history import log_chat_history

# ======================================================
# Logger / AWS Clients / Env Vars
# ======================================================
logger = CustomLogger("PDFIngestionPipeline")
s3 = boto3.client("s3")

METADATA_TABLE = os.environ.get("METADATA_TABLE")
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET")


# ======================================================
# Data Models
# ======================================================
class IngestionPayload(BaseModel):
    session_id: str
    project_name: str
    user_id: str
    doc_loc: Optional[str] = None
    doc_locs: Optional[List[str]] = None
    ingest_source: Optional[str] = None
    source_path: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None


class IngestionResponse(BaseModel):
    statusCode: int
    body: str
    s3_bucket: Optional[str] = None
    s3_key: Optional[str] = None
    ingest_source: Optional[str] = None
    source_path: Optional[str] = None
    embedding_provider: Optional[str] = None
    embedding_model: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class BatchIngestionResponse(BaseModel):
    results: List[IngestionResponse]
    summary: Optional[Dict[str, Any]] = None


# ======================================================
# PDF Ingestion Pipeline
# ======================================================
class PDFIngestionPipeline:
    def __init__(self):
        self.vector_db = QdrantVectorDB()
        self.metadata_manager = MetadataManager()
        self.model_loader = ModelLoader()
        self.model_loader.register(
            "bedrock",
            BedrockProvider(region=os.getenv("BEDROCK_REGION", "us-east-1")),
        )  # Auto-selected on first register

    def process_and_store(self, file_bytes: bytes, metadata: Dict[str, Any]) -> bool:
        """
        Extract text, chunk, embed, and store in Qdrant.
        Uses ModelLoader (embed returns (embedding, meta)).
        """
        try:
            logger.info(
                f"📥 Starting processing for doc_id={metadata.get('document_id')} "
                f"(model={metadata.get('embedding_model')}, "
                f"provider={metadata.get('embedding_provider')})"
            )

            # ---------------------------
            # Provider selection
            # ---------------------------
            provider_name = metadata.get("embedding_provider") or "bedrock"
            if provider_name != "bedrock":
                logger.warning(
                    f"⚠️ Provider '{provider_name}' requested but only 'bedrock' available; using bedrock"
                )
                provider_name = "bedrock"

            # ---------------------------
            # 1. Extract text
            # ---------------------------
            filename = metadata.get("filename", "")
            text = extract_text(file_bytes, filename)

            if not text.strip():
                logger.warning("⚠️ No text extracted; aborting ingestion for this document")
                return False

            logger.debug(f"📝 Extracted text length={len(text)} characters")

            # ---------------------------
            # 2. Split into chunks
            # ---------------------------
            chunks = split_into_chunks(text, chunk_size=500)
            logger.info(f"✂️ Split text into {len(chunks)} chunks")

            if not chunks:
                logger.warning("⚠️ No chunks created — skipping ingestion")
                return False

            # ---------------------------
            # 3. Generate embeddings
            # ---------------------------
            embeddings_to_upsert: List[Dict[str, Any]] = []
            vector_dim: Optional[int] = None
            embedding_model = metadata.get("embedding_model")

            for idx, chunk in enumerate(chunks):
                logger.debug(
                    f"🔎 Embedding chunk {idx+1}/{len(chunks)} (len={len(chunk)}) "
                    f"provider={provider_name} model={embedding_model}"
                )
                try:
                    embedding, emb_meta = self.model_loader.embed(chunk, model_id=embedding_model)

                    if not isinstance(embedding, list) or not embedding:
                        logger.error(f"❌ Invalid embedding returned for chunk {idx}")
                        return False

                    if vector_dim is None:
                        vector_dim = len(embedding)
                        logger.info(
                            f"📐 Embedding dimension detected={vector_dim} "
                            f"(model={embedding_model}, provider={provider_name})"
                        )

                    if isinstance(emb_meta, dict) and emb_meta.get("cost"):
                        logger.debug(f"💲 Embedding cost chunk {idx+1}: {emb_meta['cost']}")

                    embeddings_to_upsert.append(
                        {
                            "id": str(uuid.uuid4()),
                            "embedding": embedding,
                            "metadata": {**metadata, "chunk_id": str(idx)},
                            "text": chunk,
                        }
                    )
                except Exception as e:
                    logger.error(f"❌ Failed embedding chunk {idx}: {e}")
                    return False

            # ---------------------------
            # 4. Upsert into Qdrant
            # ---------------------------
            success = self.vector_db.upsert_embeddings(embeddings_to_upsert)
            if not success:
                logger.error("❌ Failed to upsert embeddings into Qdrant")
                return False

            logger.info(
                f"✅ Successfully ingested {len(chunks)} chunks into Qdrant "
                f"(doc_id={metadata['document_id']}, provider={provider_name})"
            )
            return True

        except Exception as e:
            logger.error(f"💥 Error in PDFIngestionPipeline: {e}", exc_info=True)
            return False


# ======================================================
# Utilities
# ======================================================
def move_file_s3_temp_to_documents(s3_bucket: str, temp_key: str, documents_key: str):
    """Move file from temp S3 location to documents bucket"""
    try:
        logger.info(f"📂 Moving file: {temp_key} → {documents_key} (bucket={s3_bucket})")
        s3.copy_object(Bucket=s3_bucket, CopySource={"Bucket": s3_bucket, "Key": temp_key}, Key=documents_key)
        s3.delete_object(Bucket=s3_bucket, Key=temp_key)
        logger.info(f"✅ File moved successfully: {temp_key}")
    except ClientError as e:
        logger.error(f"💥 S3 move failed: {str(e)}", exc_info=True)
        raise CustomException(f"Error moving file in S3: {str(e)}")


def compute_content_hash(file_bytes: bytes) -> str:
    """Compute SHA256 content hash of file"""
    digest = hashlib.sha256(file_bytes).hexdigest()
    logger.debug(f"🔑 Computed content hash={digest}")
    return digest


# ======================================================
# Ingestion Entry Point
# ======================================================
def ingest_document(payload: dict) -> Union[IngestionResponse, BatchIngestionResponse]:
    """
    Validate payload, fetch file(s) from S3 temp, compute hash, check metadata,
    update DB, store embeddings, move file(s).
    """
    logger.info(f"🚀 Starting ingestion with payload={payload}")

    s3_bucket = DOCUMENTS_S3_BUCKET
    session_id = payload.get("session_id")
    project_name = payload.get("project_name")
    user_id = payload.get("user_id")

    # ---------------------------
    # Embedding provider/model resolution
    # ---------------------------
    embedding_provider = (payload.get("embedding_provider") or "bedrock").lower()
    allowed_providers = {"bedrock"}  # Future: add more providers here

    if embedding_provider not in allowed_providers:
        logger.error(
            f"❌ Unsupported embedding_provider '{embedding_provider}' (allowed={allowed_providers})"
        )
        return BatchIngestionResponse(
            results=[
                IngestionResponse(
                    statusCode=400,
                    body=f"Unsupported embedding_provider: {embedding_provider}",
                )
            ],
            summary={"total": 1, "succeeded": 0, "duplicates": 0, "unsupported": 0, "errors": 1},
        )

    embedding_model = payload.get("embedding_model")
    if not embedding_model:
        if embedding_provider == "bedrock":
            embedding_model = os.environ.get("DEFAULT_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
        else:  # placeholder for future providers
            embedding_model = "default-model"
        logger.info(
            f"ℹ️ Using default embedding model '{embedding_model}' for provider '{embedding_provider}'"
        )

    # ---------------------------
    # Initialize pipeline
    # ---------------------------
    pipeline = PDFIngestionPipeline()

    # ---------------------------
    # Log ingestion start
    # ---------------------------
    try:
        doc_list = []
        if payload.get("doc_loc"):
            doc_list.append(payload["doc_loc"])
        if payload.get("doc_locs"):
            doc_list.extend(payload["doc_locs"])

        files_text = ", ".join(doc_list) if doc_list else "multiple files"
        start_message = (
            f"🚀 Starting document ingestion for: {files_text} "
            f"(provider={embedding_provider}, model={embedding_model})"
        )
        log_chat_history(
            event={},
            payload=payload,
            role="system",
            content=start_message,
            metadata={
                "action": "ingestion_start",
                "files": doc_list,
                "embedding_provider": embedding_provider,
                "embedding_model": embedding_model,
            },
        )
    except Exception as e:
        logger.warning(f"⚠️ Failed to log ingestion start to chat history: {e}")

    logger.debug(f"🌍 Env vars → BUCKET={s3_bucket}, METADATA_TABLE={METADATA_TABLE}")

    # ---------------------------
    # File list setup
    # ---------------------------
    doc_locs: List[str] = []
    if payload.get("doc_loc"):
        doc_locs.append(payload["doc_loc"])
    if payload.get("doc_locs"):
        doc_locs.extend(payload["doc_locs"])

    logger.debug(f"📄 Files to ingest={doc_locs}")

    temp_prefix = os.getenv("TEMP_DATA_KEY")
    documents_prefix = os.getenv("DOCUMENTS_DATA_KEY")
    logger.debug(f"📂 Prefixes → TEMP={temp_prefix}, DOCS={documents_prefix}")

    results: List[IngestionResponse] = []

    # ---------------------------
    # Process each document
    # ---------------------------
    for doc_loc in doc_locs:
        try:
            # Construct S3 keys
            temp_s3_key = f"{temp_prefix}/{project_name}/{doc_loc}"
            doc_s3_key = f"{documents_prefix}/{project_name}/{doc_loc}"
            logger.info(f"🔗 Constructed S3 keys: temp={temp_s3_key}, doc={doc_s3_key}")

            # File type check
            if not doc_loc.lower().endswith((".pdf", ".docx", ".txt")):
                logger.warning(f"⚠️ Skipping unsupported file type: {doc_loc}")
                try:
                    unsupported_message = (
                        f"⚠️ Unsupported file type: {doc_loc} "
                        f"(only PDF, DOCX, and TXT files are supported)"
                    )
                    log_chat_history(
                        event={},
                        payload=payload,
                        role="system",
                        content=unsupported_message,
                        metadata={"action": "unsupported_file_type", "filename": doc_loc},
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to log unsupported file type to chat history: {e}")

                results.append(
                    IngestionResponse(
                        statusCode=415,
                        body=f"Unsupported file type: {doc_loc}",
                        s3_bucket=s3_bucket,
                        s3_key=temp_s3_key,
                    )
                )
                continue

            # Download file
            logger.info(f"⬇️ Downloading {temp_s3_key} from {s3_bucket}")
            s3_obj = s3.get_object(Bucket=s3_bucket, Key=temp_s3_key)
            file_bytes = s3_obj["Body"].read()
            logger.info(f"📦 Downloaded {temp_s3_key} (size={len(file_bytes)} bytes)")

            # Detect file type
            detected_type = detect_file_type(doc_loc, file_bytes)
            logger.info(f"🧪 Detected file_type={detected_type} for {doc_loc}")

            # Compute content hash
            content_hash = compute_content_hash(file_bytes)

            # Setup metadata
            ingest_source = payload.get("ingest_source") or "user_upload"
            source_path = payload.get("source_path") or "UI"
            logger.debug(
                f"🛠 Metadata setup → source={ingest_source}, path={source_path}, "
                f"provider={embedding_provider}, model={embedding_model}"
            )

            metadata_manager = MetadataManager()
            metadata, exists = create_and_check_metadata(
                manager=metadata_manager,
                s3_key=temp_s3_key,
                project_name=project_name,
                user_id=user_id,
                content_hash=content_hash,
                session_id=session_id or "unknown_session",
                ingest_source=ingest_source or "unknown_source",
                source_path=source_path or "unknown_path",
                embedding_provider=embedding_provider or "unknown_provider",
                embedding_model=embedding_model or "unknown_model",
                filename=doc_loc,
                file_type=detected_type or "unknown",
                file_size=len(file_bytes),
            )

            # Duplicate check
            if exists.get("exact_exists"):
                logger.warning(f"⚠️ Duplicate detected (same file + same model) → {doc_loc}")
                try:
                    duplicate_message = (
                        f"⚠️ Duplicate document detected: {doc_loc} "
                        f"(same file with same embedding model already exists)"
                    )
                    log_chat_history(
                        event={},
                        payload=payload,
                        role="system",
                        content=duplicate_message,
                        metadata={
                            "action": "duplicate_detected",
                            "filename": doc_loc,
                            "embedding_model": embedding_model,
                            "embedding_provider": embedding_provider,
                        },
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to log duplicate detection to chat history: {e}")

                results.append(
                    IngestionResponse(
                        statusCode=409,
                        body=f"Duplicate data already exists: {doc_loc}",
                        s3_bucket=s3_bucket,
                        s3_key=doc_s3_key,
                    )
                )
                continue
            elif exists.get("any_exists"):
                logger.info(f"ℹ️ Same file already exists in project (different model) → continuing ingestion")
            else:
                logger.info(f"✅ No duplicates found for {doc_loc}")

            if exists.get("saved"):
                logger.info("✅ Metadata saved successfully to DynamoDB")
            else:
                logger.info("ℹ️ Metadata not saved (duplicate or error)")

            # Run embedding pipeline
            logger.info(f"⚙️ Running embedding pipeline for {doc_loc}")
            ok = pipeline.process_and_store(file_bytes, metadata)
            if not ok:
                logger.error(f"❌ Embedding pipeline failed for {doc_loc}")
                try:
                    error_message = f"❌ Failed to process embeddings for: {doc_loc}"
                    log_chat_history(
                        event={},
                        payload=payload,
                        role="system",
                        content=error_message,
                        metadata={
                            "action": "embedding_error",
                            "filename": doc_loc,
                            "embedding_model": embedding_model,
                            "embedding_provider": embedding_provider,
                        },
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to log embedding error to chat history: {e}")

                results.append(
                    IngestionResponse(
                        statusCode=500,
                        body=f"Embedding pipeline failed: {doc_loc}",
                        s3_bucket=s3_bucket,
                        s3_key=doc_s3_key,
                    )
                )
                continue

            # Move file from temp to documents
            move_file_s3_temp_to_documents(s3_bucket, temp_s3_key, doc_s3_key)

            # Log success
            try:
                success_message = f"✅ Successfully ingested document: {doc_loc}"
                log_chat_history(
                    event={},
                    payload=payload,
                    role="system",
                    content=success_message,
                    metadata={
                        "action": "ingestion_success",
                        "filename": doc_loc,
                        "s3_key": doc_s3_key,
                        "embedding_model": embedding_model,
                        "embedding_provider": embedding_provider,
                        "content_hash": content_hash,
                    },
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to log successful ingestion to chat history: {e}")

            results.append(
                IngestionResponse(
                    statusCode=201,
                    body=f"✅ Document ingested successfully: {doc_loc}",
                    s3_bucket=s3_bucket,
                    s3_key=doc_s3_key,
                    ingest_source=ingest_source,
                    source_path=source_path,
                    embedding_provider=embedding_provider,
                    embedding_model=embedding_model,
                    metadata=metadata,
                )
            )

        except Exception as e:
            logger.error(f"💥 Unexpected error ingesting {doc_loc}: {e}", exc_info=True)
            try:
                error_message = f"💥 Unexpected error occurred while ingesting: {doc_loc} - {str(e)}"
                log_chat_history(
                    event={},
                    payload=payload,
                    role="system",
                    content=error_message,
                    metadata={"action": "unexpected_error", "filename": doc_loc, "error": str(e)},
                )
            except Exception as chat_error:
                logger.warning(f"⚠️ Failed to log unexpected error to chat history: {chat_error}")

            results.append(
                IngestionResponse(
                    statusCode=500,
                    body=f"Unexpected error ingesting {doc_loc}: {str(e)}",
                    s3_bucket=s3_bucket,
                )
            )

    # ---------------------------
    # Ingestion summary
    # ---------------------------
    summary = {
        "total": len(results),
        "succeeded": sum(1 for r in results if r.statusCode in (200, 201)),
        "duplicates": sum(1 for r in results if r.statusCode == 409),
        "unsupported": sum(1 for r in results if r.statusCode == 415),
        "errors": sum(1 for r in results if r.statusCode >= 500),
    }

