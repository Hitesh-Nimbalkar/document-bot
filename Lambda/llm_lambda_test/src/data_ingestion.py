import os
import boto3
import hashlib
from botocore.exceptions import ClientError
from typing import List, Dict, Any, Union

from utils.metadata import create_and_check_metadata
from utils.logger import CustomLogger, CustomException
from vector_db.vector_db import QdrantVectorDB
from utils.embeddings import split_into_chunks, get_embeddings
from utils.metadata import MetadataModel
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import uuid

logger = CustomLogger("PDFIngestionPipeline")

dynamodb = boto3.resource("dynamodb")
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
    doc_loc: Optional[str] = None
    doc_locs: Optional[List[str]] = None
    ingest_source: Optional[str] = None
    source_path: Optional[str] = None
    embedding_model: Optional[str] = None


# ---------------------------
# Ingestion Response
# ---------------------------
class IngestionResponse(BaseModel):
    statusCode: int
    body: str
    s3_bucket: Optional[str] = None
    s3_key: Optional[str] = None
    ingest_source: Optional[str] = None
    source_path: Optional[str] = None
    embedding_model: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class BatchIngestionResponse(BaseModel):
    results: List[IngestionResponse]
    summary: Optional[Dict[str, Any]] = None


class PDFIngestionPipeline:
    def __init__(self):
        self.vector_db = QdrantVectorDB()

    def process_and_store(self, file_bytes: bytes, metadata: Dict[str, Any]) -> bool:
        """
        Extract text, chunk, embed, and store in Qdrant.
        """
        try:
            logger.info(
                f"📥 Starting processing for doc_id={metadata.get('document_id')} "
                f"(model={metadata.get('embedding_model')})"
            )

            # 1. Extract text
            text = file_bytes.decode("utf-8", errors="ignore")
            logger.debug(f"📝 Extracted text length={len(text)} characters")

            # 2. Chunk
            chunks = split_into_chunks(text, chunk_size=500)
            logger.info(f"✂️ Split text into {len(chunks)} chunks")

            if not chunks:
                logger.warning("⚠️ No chunks created — skipping ingestion")
                return False

            # 3. Embeddings
            embeddings_to_upsert: List[Dict[str, Any]] = []
            vector_dim: int = None

            for idx, chunk in enumerate(chunks):
                logger.debug(f"🔎 Embedding chunk {idx+1}/{len(chunks)} (len={len(chunk)})")
                vector = get_embeddings(chunk, model_name=metadata.get("embedding_model"))

                if vector is None:
                    logger.error(f"❌ Failed to generate embedding for chunk {idx}")
                    return False

                if vector_dim is None:
                    vector_dim = len(vector)
                    logger.info(
                        f"📐 Embedding dimension detected={vector_dim} "
                        f"(model={metadata.get('embedding_model')})"
                    )

                embeddings_to_upsert.append({
                    "id": str(uuid.uuid4()),
                    "embedding": vector,
                    "metadata": {**metadata, "chunk_id": str(idx)},
                    "text": chunk,
                })

            # 4. Upsert into Qdrant
            success = self.vector_db.upsert_embeddings(embeddings_to_upsert)
            if not success:
                logger.error("❌ Failed to upsert embeddings into Qdrant")
                return False

            logger.info(
                f"✅ Successfully ingested {len(chunks)} chunks into Qdrant "
                f"(doc_id={metadata['document_id']})"
            )
            return True

        except Exception as e:
            logger.error(f"💥 Error in PDFIngestionPipeline: {e}", exc_info=True)
            return False


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
                results.append(IngestionResponse(statusCode=415, body=f"Unsupported file type: {doc_loc}",
                                                 s3_bucket=s3_bucket, s3_key=temp_s3_key))
                continue

            logger.info(f"⬇️ Downloading {temp_s3_key} from {s3_bucket}")
            s3_obj = s3.get_object(Bucket=s3_bucket, Key=temp_s3_key)
            file_bytes = s3_obj["Body"].read()
            logger.info(f"📦 Downloaded {temp_s3_key} (size={len(file_bytes)} bytes)")

            content_hash = compute_content_hash(file_bytes)

            ingest_source = payload.get("ingest_source") or "user_upload"
            source_path = payload.get("source_path") or "UI"
            embedding_model = payload.get("embedding_model") or "dummy-embedding-model"

            logger.debug(f"🛠 Metadata setup → source={ingest_source}, path={source_path}, model={embedding_model}")

            metadata, exists = create_and_check_metadata(
                temp_s3_key, project_name, user_id, content_hash,
                session_id, ingest_source, source_path, embedding_model ,ddb_table=METADATA_TABLE
            )

            if exists.get("exact_exists"):
                logger.warning(f"⚠️ Duplicate detected (same file + same model) → {doc_loc}")
                results.append(IngestionResponse(
                    statusCode=409,
                    body=f"Duplicate data already exists: {doc_loc}",
                    s3_bucket=s3_bucket,
                    s3_key=doc_s3_key
                ))
            elif exists.get("any_exists"):
                logger.info(f"ℹ️ Same file already exists in project (different model) → continuing ingestion")
            else:
                logger.info(f"✅ No duplicates found for {doc_loc}")

            logger.info(f"🗂 Writing metadata to DynamoDB (table={METADATA_TABLE})")
            table = dynamodb.Table(METADATA_TABLE)
            table.put_item(Item=metadata)

            logger.info(f"⚙️ Running embedding pipeline for {doc_loc}")
            pipeline = PDFIngestionPipeline()
            ok = pipeline.process_and_store(file_bytes, metadata)

            if not ok:
                logger.error(f"❌ Embedding pipeline failed for {doc_loc}")
                results.append(IngestionResponse(
                    statusCode=500,
                    body=f"Embedding pipeline failed: {doc_loc}",
                    s3_bucket=s3_bucket,
                    s3_key=doc_s3_key
                ))
                continue  # file stays in /temp

            move_file_s3_temp_to_documents(s3_bucket, temp_s3_key, doc_s3_key)

            results.append(IngestionResponse(statusCode=201,
                                             body=f"✅ Document ingested successfully: {doc_loc}",
                                             s3_bucket=s3_bucket,
                                             s3_key=doc_s3_key,
                                             ingest_source=ingest_source,
                                             source_path=source_path,
                                             embedding_model=embedding_model,
                                             metadata=metadata))

        except Exception as e:
            logger.error(f"💥 Unexpected error ingesting {doc_loc}: {e}", exc_info=True)
            results.append(IngestionResponse(statusCode=500,
                                             body=f"Unexpected error ingesting {doc_loc}: {str(e)}",
                                             s3_bucket=s3_bucket))

    summary = {
        "total": len(results),
        "succeeded": sum(1 for r in results if r.statusCode in (200, 201)),
        "duplicates": sum(1 for r in results if r.statusCode == 409),
        "unsupported": sum(1 for r in results if r.statusCode == 415),
        "errors": sum(1 for r in results if r.statusCode >= 500),
    }
    logger.info(f"📊 Ingestion summary={summary}")

    return BatchIngestionResponse(results=results, summary=summary)
