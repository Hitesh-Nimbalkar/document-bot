



import os
import boto3
import hashlib
import io  # kept (may be used elsewhere)
from botocore.exceptions import ClientError
from typing import List, Dict, Any, Union, Optional  # added Optional here
from utils.metadata import MetadataManager, create_and_check_metadata
from utils.logger import CustomLogger, CustomException
from vector_db.vector_db import QdrantVectorDB
from utils.split import split_into_chunks, detect_file_type, extract_text
from chat_history.chat_history import log_chat_history  # ensure direct import
from pydantic import BaseModel  # restored
import uuid  # restored
# Model loader imports (OpenAI removed for now)
from utils.model_loader import ModelLoader, BedrockProvider
logger = CustomLogger("PDFIngestionPipeline")
s3 = boto3.client("s3")
METADATA_TABLE = os.environ.get("METADATA_TABLE")
DOCUMENTS_S3_BUCKET = os.environ.get("DOCUMENTS_S3_BUCKET")
# ---------------------------
# Ingestion Payload
# ---------------------------
class IngestionPayload(BaseModel):
    session_id: str
    project_name: str
    user_id: str
    doc_loc: str
    doc_locs: List[str]
    ingest_source: str
    source_path: str
    embedding_provider: str
    embedding_model: str
# ---------------------------
# Ingestion Response
# ---------------------------
class IngestionResponse(BaseModel):
    statusCode: int
    body: str
    s3_bucket: str 
    s3_key: str
    ingest_source: Optional[str] = None
    source_path: Optional[str] = None
    embedding_provider: str
    embedding_model: str
    metadata: Optional[Dict[str, Any]] = None
class BatchIngestionResponse(BaseModel):
    results: List[IngestionResponse]
    summary: Optional[Dict[str, Any]] = None
class PDFIngestionPipeline:
    def __init__(self, embedding_provider: str = "bedrock", embedding_model: Optional[str] = None):
        """
        Initialize ingestion pipeline with explicit embedding provider and model.
        """
        self.vector_db = QdrantVectorDB()
        self.metadata_manager = MetadataManager(vector_db_client=self.vector_db)
        # Default embedding model if not provided
        if not embedding_model:
            if embedding_provider == "bedrock":
                embedding_model = os.getenv("DEFAULT_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
            else:
                raise ValueError(f"Unsupported embedding provider: {embedding_provider}")
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        # Register provider + model with ModelLoader
        self.model_loader = ModelLoader()
        self.model_loader.register(
            name=embedding_provider,
            provider=BedrockProvider(
                region=os.getenv("BEDROCK_REGION", "ap-south-1"),
                embedding_model=embedding_model,
            ),
            model_name=embedding_model,
        )
        logger.info(f"📦 PDFIngestionPipeline initialized | provider={embedding_provider}, model={embedding_model}")


    def process_and_store(self, file_bytes: bytes, metadata: Dict[str, Any]) -> tuple[bool, Dict[str, Any]]:
        """
        Extract text, chunk, embed, and store in Qdrant.
        Uses ModelLoader (embed returns (embedding, meta)).
        Returns: (success: bool, emb_meta: Dict[str, Any])
        """
        # Initialize aggregated embedding metadata
        aggregated_emb_meta = {
            "total_chunks": 0,
            "total_cost": 0.0,
            "total_tokens_in": 0,
            "total_tokens_out": 0,
            "model": self.embedding_model,
            "provider": self.embedding_provider,
            "success": False
        }
        
        try:
            doc_id = metadata.get("document_id")
            logger.info(
                f"📥 Starting processing for doc_id={doc_id} "
                f"(model={self.embedding_model}, provider={self.embedding_provider})"
            )
            # 1. Extract text
            filename = metadata.get("filename", "")
            text = extract_text(file_bytes, filename)
            if not text.strip():
                logger.warning(f"⚠️ No text extracted for doc_id={doc_id}")
                return False, aggregated_emb_meta
            logger.debug(f"📝 Extracted text length={len(text)} characters")
            # 2. Chunk
            chunks = split_into_chunks(text, chunk_size=500)
            logger.info(f"✂️ Split text into {len(chunks)} chunks for doc_id={doc_id}")
            if not chunks:
                return False, aggregated_emb_meta
            # 3. Embeddings via model loader
            embeddings_to_upsert: List[Dict[str, Any]] = []
            vector_dim: Optional[int] = None
            for idx, chunk in enumerate(chunks):
                try:
                    logger.debug(
                        f"🔎 Embedding chunk {idx+1}/{len(chunks)} "
                        f"(len={len(chunk)}) provider={self.embedding_provider} model={self.embedding_model}"
                    )
                    embedding, chunk_emb_meta = self.model_loader.embed(chunk, model_id=self.embedding_model)
                    if not embedding:
                        logger.error(f"❌ Empty embedding returned for chunk {idx}")
                        return False, aggregated_emb_meta
                    if vector_dim is None:
                        vector_dim = len(embedding)
                        logger.info(f"📐 Embedding dimension={vector_dim} (model={self.embedding_model})")
                    embeddings_to_upsert.append({
                        "id": str(uuid.uuid4()),
                        "embedding": embedding,
                        "metadata": {**metadata, "chunk_id": str(idx)},
                        "text": chunk,
                    })
                    # Aggregate metadata from this chunk
                    aggregated_emb_meta["total_chunks"] += 1
                    if chunk_emb_meta.get("cost"):
                        aggregated_emb_meta["total_cost"] += chunk_emb_meta["cost"]
                        logger.debug(f"💲 Embedding cost chunk {idx+1}: {chunk_emb_meta['cost']}")
                    
                    if chunk_emb_meta.get("usage"):
                        usage = chunk_emb_meta["usage"]
                        aggregated_emb_meta["total_tokens_in"] += usage.get("tokens_in", 0)
                        aggregated_emb_meta["total_tokens_out"] += usage.get("tokens_out", 0)
                except Exception as e:
                    logger.error(f"❌ Failed embedding chunk {idx}: {e}")
                    return False, aggregated_emb_meta
            # 4. Upsert into Qdrant
            success = self.vector_db.upsert_embeddings(embeddings_to_upsert)
            if not success:
                logger.error(f"❌ Failed Qdrant upsert for doc_id={doc_id}")
                return False, aggregated_emb_meta
            logger.info(
                f"✅ Successfully ingested {len(chunks)} chunks into Qdrant "
                f"(doc_id={doc_id}, provider={self.embedding_provider}, model={self.embedding_model})"
            )
            
            # Mark success and add final summary to metadata
            aggregated_emb_meta["success"] = True
            aggregated_emb_meta["chunks_processed"] = len(chunks)
            if aggregated_emb_meta["total_cost"] > 0:
                logger.info(f"💰 Total embedding cost: ${aggregated_emb_meta['total_cost']:.6f}")
            
            return True, aggregated_emb_meta
        except Exception as e:
            logger.error(f"💥 Error in PDFIngestionPipeline for doc_id={metadata.get('document_id')}: {e}", exc_info=True)
            return False, aggregated_emb_meta


def move_file_s3_temp_to_documents(s3_bucket: str, temp_key: str, documents_key: str):
    try:
        logger.info(f"📂 Moving file: {temp_key} → {documents_key} (bucket={s3_bucket})")
        s3.copy_object(Bucket=s3_bucket, CopySource={"Bucket": s3_bucket, "Key": temp_key}, Key=documents_key)
        s3.delete_object(Bucket=s3_bucket, Key=temp_key)
        logger.info(f"✅ File moved successfully: {temp_key}")
    except ClientError as e:
        logger.error(f"💥 S3 move failed: {str(e)}", exc_info=True)
        raise CustomException(f"Error moving file in S3: {str(e)}")
def compute_content_hash(file_bytes: bytes) -> str:
    digest = hashlib.sha256(file_bytes).hexdigest()
    logger.debug(f"🔑 Computed content hash={digest}")
    return digest
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
    # --- Embedding provider/model resolution ---
    embedding_provider = (payload.get("embedding_provider") or "bedrock").lower()
    allowed_providers = {"bedrock"}  # Future: add more providers here
    if embedding_provider not in allowed_providers:
        logger.error(f"❌ Unsupported embedding_provider '{embedding_provider}' (allowed={allowed_providers})")
        return BatchIngestionResponse(
            results=[IngestionResponse(
                statusCode=400, 
                body=f"Unsupported embedding_provider: {embedding_provider}",
                s3_bucket="",
                s3_key="",
                embedding_provider=embedding_provider,
                embedding_model=""
            )],
            summary={"total": 1, "succeeded": 0, "duplicates": 0, "unsupported": 0, "errors": 1},
        )
    embedding_model = payload.get("embedding_model")
    if not embedding_model:
        if embedding_provider == "bedrock":
            embedding_model = os.environ.get("DEFAULT_EMBEDDING_MODEL", "amazon.titan-embed-text-v2:0")
        else:  # placeholder for future providers
            embedding_model = "default-model"
        logger.info(f"ℹ️ Using default embedding model '{embedding_model}' for provider '{embedding_provider}'")
    # Initialize pipeline with provider + model
    pipeline = PDFIngestionPipeline(
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
    )
    # Log ingestion start to chat history
    try:
        doc_list = []
        if payload.get("doc_loc"):
            doc_list.append(payload["doc_loc"])
        if payload.get("doc_locs"):
            doc_list.extend(payload["doc_locs"])
        files_text = ", ".join(doc_list) if doc_list else "multiple files"
        start_message = f"🚀 Starting document ingestion for: {files_text} (provider={embedding_provider}, model={embedding_model})"
        log_chat_history(
            event={},
            payload=payload,
            role="system",
            content=start_message,
            metadata={"action": "ingestion_start", "files": doc_list, "embedding_provider": embedding_provider, "embedding_model": embedding_model},
        )
    except Exception as e:
        logger.warning(f"⚠️ Failed to log ingestion start to chat history: {e}")
    logger.debug(f"🌍 Env vars → BUCKET={s3_bucket}, METADATA_TABLE={METADATA_TABLE}")
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
    for doc_loc in doc_locs:
        try:
            temp_s3_key = f"{temp_prefix}/{project_name}/{doc_loc}"
            doc_s3_key = f"{documents_prefix}/{project_name}/{doc_loc}"
            logger.info(f"🔗 Constructed S3 keys: temp={temp_s3_key}, doc={doc_s3_key}")
            if not doc_loc.lower().endswith((".pdf", ".docx", ".txt")):
                logger.warning(f"⚠️ Skipping unsupported file type: {doc_loc}")
                try:
                    unsupported_message = f"⚠️ Unsupported file type: {doc_loc} (only PDF, DOCX, and TXT files are supported)"
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
                        embedding_provider=embedding_provider,
                        embedding_model=embedding_model,
                    )
                )
                continue
            logger.info(f"⬇️ Downloading {temp_s3_key} from {s3_bucket}")
            s3_obj = s3.get_object(Bucket=s3_bucket, Key=temp_s3_key)
            file_bytes = s3_obj["Body"].read()
            logger.info(f"📦 Downloaded {temp_s3_key} (size={len(file_bytes)} bytes)")
            # Detect file type (new)
            detected_type = detect_file_type(doc_loc, file_bytes)
            logger.info(f"🧪 Detected file_type={detected_type} for {doc_loc}")
            content_hash = compute_content_hash(file_bytes)
            ingest_source = payload.get("ingest_source") or "user_upload"
            source_path = payload.get("source_path") or "UI"
            logger.debug(
                f"🛠 Metadata setup → source={ingest_source}, path={source_path}, provider={embedding_provider}, model={embedding_model}"
            )
            # Use the pipeline's metadata_manager which has vector_db_client
            metadata, exists = create_and_check_metadata(
                manager=pipeline.metadata_manager,  # Use pipeline's manager with vector DB client
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
                verify_embeddings=True,  # Enable vector DB verification
            )
            # Enhanced duplicate checking logic
            if exists.get("should_skip"):
                logger.warning(f"⚠️ Document fully processed (metadata + embeddings verified) → {doc_loc}")
                try:
                    duplicate_message = (
                        f"⚠️ Document already fully processed: {doc_loc} (both metadata and embeddings exist in vector database)"
                    )
                    log_chat_history(
                        event={},
                        payload=payload,
                        role="system",
                        content=duplicate_message,
                        metadata={
                            "action": "fully_processed_skip",
                            "filename": doc_loc,
                            "embedding_model": embedding_model,
                            "embedding_provider": embedding_provider,
                        },
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to log fully processed skip to chat history: {e}")
                results.append(
                    IngestionResponse(
                        statusCode=409,
                        body=f"Document already fully processed: {doc_loc}",
                        s3_bucket=s3_bucket,
                        s3_key=doc_s3_key,
                        embedding_provider=embedding_provider,
                        embedding_model=embedding_model,
                    )
                )
                continue
            elif exists.get("exact_exists") and not exists.get("embeddings_verified"):
                logger.warning(f"⚠️ Metadata exists but embeddings missing in vector DB → will reprocess {doc_loc}")
                try:
                    reprocess_message = (
                        f"⚠️ Incomplete processing detected for: {doc_loc} (metadata exists but embeddings missing in vector database, will reprocess)"
                    )
                    log_chat_history(
                        event={},
                        payload=payload,
                        role="system",
                        content=reprocess_message,
                        metadata={
                            "action": "incomplete_reprocess",
                            "filename": doc_loc,
                            "embedding_model": embedding_model,
                            "embedding_provider": embedding_provider,
                        },
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to log reprocess message to chat history: {e}")
            elif exists.get("any_exists"):
                logger.info(
                    f"ℹ️ Same file already exists in project (different model) → continuing ingestion"
                )
            else:
                logger.info(f"✅ No duplicates found for {doc_loc}")
            if exists.get("saved"):
                logger.info(f"✅ Metadata saved successfully to DynamoDB")
            else:
                logger.info(f"ℹ️ Metadata not saved (duplicate or error)")
            logger.info(f"⚙️ Running embedding pipeline for {doc_loc}")
            ok , emb_meta = pipeline.process_and_store(file_bytes, metadata)
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
                            "emb_meta" : emb_meta
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
                        embedding_provider=embedding_provider,
                        embedding_model=embedding_model,
                    )
                )
                continue
            move_file_s3_temp_to_documents(s3_bucket, temp_s3_key, doc_s3_key)
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
                        "emb_meta" : emb_meta
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
                    s3_key=getattr(locals(), 'doc_s3_key', getattr(locals(), 'temp_s3_key', "")),
                    embedding_provider=embedding_provider,
                    embedding_model=embedding_model,
                )
            )
    summary = {
        "total": len(results),
        "succeeded": sum(1 for r in results if r.statusCode in (200, 201)),
        "duplicates": sum(1 for r in results if r.statusCode == 409),
        "unsupported": sum(1 for r in results if r.statusCode == 415),
        "errors": sum(1 for r in results if r.statusCode >= 500),
    }
    logger.info(f"📊 Ingestion summary={summary}")
    try:
        summary_message = (
            f"📊 Document ingestion completed! "
            f"Total: {summary['total']}, "
            f"Succeeded: {summary['succeeded']}, "
            f"Duplicates: {summary['duplicates']}, "
            f"Unsupported: {summary['unsupported']}, "
            f"Errors: {summary['errors']}"\
        )
        log_chat_history(
            event={},
            payload=payload,
            role="system",
            content=summary_message,
            metadata={
                "action": "ingestion_summary",
                "summary": summary,
                "embedding_provider": embedding_provider,
                "embedding_model": embedding_model,
            },
        )
    except Exception as e:
        logger.warning(f"⚠️ Failed to log ingestion summary to chat history: {e}")
    return BatchIngestionResponse(results=results, summary=summary)



