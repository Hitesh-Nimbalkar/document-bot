
import os
import uuid
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchValue,
)
from utils.utils import CustomLogger
from utils.connection_pool import connection_pool
#from utils.metadata import MetadataModel  # Pydantic metadata model
from utils.dynamodb import DynamoMetadataService  # DynamoDB wrapper
logger = CustomLogger("QdrantVectorDB")
# Flag for whether to store raw text inside vector DB payload
STORE_TEXT_IN_VECTOR_DB = os.getenv("STORE_TEXT_IN_VECTOR_DB", "true").lower() == "true"

# ======================================================
# Qdrant Configuration
# ======================================================
class QdrantConfig:
    """Configuration for Qdrant connection"""
    HOST: str = os.getenv(
        "VECTOR_DB_HOST",
        "03e01705-fc18-488f-ace1-b2008e0423cf.us-west-2-0.aws.cloud.qdrant.io",
    )
    PORT: int = int(os.getenv("VECTOR_DB_PORT", "6333"))
    API_KEY: str = os.getenv("VECTOR_DB_API_KEY", "")
    COLLECTION: str = os.getenv("COLLECTION_NAME", "Demo")
    VECTOR_DIM: int = int(os.getenv("VECTOR_DIMENSION", "1536"))

# ======================================================
# Qdrant Vector DB Wrapper
# ======================================================
class QdrantVectorDB:
    """Handles vector storage and retrieval in Qdrant with DynamoDB metadata integration"""
    def __init__(self, config: QdrantConfig = QdrantConfig()):
        self.config = config
        
        # Use connection pool for Qdrant client (significant performance improvement)
        self.client = connection_pool.get_qdrant_client(
            host=self.config.HOST,
            port=self.config.PORT, 
            api_key=self.config.API_KEY
        )
        # DynamoDB service for metadata (also uses connection pooling internally)
        self.dynamo_service = DynamoMetadataService()
        
        # Cache collection info to avoid repeated API calls
        self._collection_exists = None
        self._collection_dim = None
    # --------------------------------------------------
    # Ensure collection
    # --------------------------------------------------
    def ensure_collection(self, required_dim: int) -> bool:
        """
        Ensure Qdrant collection exists and has the correct vector dimension.
        Uses caching to avoid repeated API calls during Lambda execution.
        """
        # Use cached result if available and dimension matches
        if (self._collection_exists is not None and 
            self._collection_dim is not None and 
            self._collection_dim == required_dim):
            return True
            
        try:
            # Only check collections if not cached
            if self._collection_exists is None:
                collections = self.client.get_collections()
                existing = {col.name: col for col in collections.collections}
                self._collection_exists = self.config.COLLECTION in existing
            if not self._collection_exists:
                self.client.create_collection(
                    collection_name=self.config.COLLECTION,
                    vectors_config=VectorParams(size=required_dim, distance=Distance.COSINE),
                )
                logger.info(
                    f"✅ Created collection {self.config.COLLECTION} with dim={required_dim}"
                )
                self._collection_exists = True
                self._collection_dim = required_dim
                return True
            # Check dimension only if not cached
            if self._collection_dim is None:
                col_info = self.client.get_collection(self.config.COLLECTION)
                self._collection_dim = col_info.config.params.vectors.size
            if self._collection_dim != required_dim:
                # Check if we should auto-fix dimension mismatches
                auto_fix = os.getenv("AUTO_FIX_DIMENSION_MISMATCH", "false").lower() == "true"
                
                if auto_fix:
                    logger.warning(
                        f"⚠️ Collection {self.config.COLLECTION} dimension mismatch: "
                        f"expected={required_dim}, found={self._collection_dim}. "
                        f"Recreating collection with correct dimensions."
                    )
                    try:
                        # Delete existing collection
                        self.client.delete_collection(self.config.COLLECTION)
                        logger.info(f"🗑️ Deleted collection {self.config.COLLECTION}")
                        
                        # Create new collection with correct dimensions
                        self.client.create_collection(
                            collection_name=self.config.COLLECTION,
                            vectors_config=VectorParams(size=required_dim, distance=Distance.COSINE),
                        )
                        logger.info(
                            f"✅ Recreated collection {self.config.COLLECTION} with dim={required_dim}"
                        )
                        return True
                    except Exception as recreate_error:
                        logger.error(f"❌ Failed to recreate collection: {recreate_error}")
                        return False
                else:
                    logger.error(
                        f"❌ Collection {self.config.COLLECTION} dimension mismatch: "
                        f"expected={required_dim}, found={self._collection_dim}. "
                        f"Set AUTO_FIX_DIMENSION_MISMATCH=true to auto-recreate, or manually fix the collection."
                    )
                    return False
            logger.info(
                f"ℹ️ Collection {self.config.COLLECTION} already matches dim={required_dim}"
            )
            return True
        except Exception as e:
            logger.error(f"❌ Error ensuring collection: {e}", exc_info=True)
            return False
    # --------------------------------------------------
    # Upsert
    # --------------------------------------------------
    def upsert_embeddings(self, embeddings: List[Dict[str, Any]]) -> bool:
        """Store embeddings in Qdrant with metadata attached."""
        if not embeddings:
            logger.warning("No embeddings provided to upsert.")
            return False
        try:
            first_vector = embeddings[0].get("embedding") or embeddings[0].get("vector")
            if not first_vector:
                logger.error("❌ First embedding has no vector.")
                return False
            required_dim = len(first_vector)
            logger.debug(f"Detected embedding dimension={required_dim}")
            if not self.ensure_collection(required_dim):
                logger.error("Aborting upsert due to collection dimension mismatch.")
                return False
            points: List[PointStruct] = []
            for item in embeddings:
                vector = item.get("embedding") or item.get("vector")
                metadata_dict = item.get("metadata")
                if not vector:
                    logger.warning(f"Skipping item without vector: {item}")
                    continue
                if not metadata_dict:
                    logger.warning(f"Skipping item without metadata: {item}")
                    continue
                point_id = item.get("id", str(uuid.uuid4()))
                vector_payload = {
                    "project_name": metadata_dict.get("project_name"),
                    "user_id": metadata_dict.get("user_id"),
                    "session_id": metadata_dict.get("session_id"),
                    "document_id": metadata_dict.get("document_id"),
                    "chunk_id": metadata_dict.get("chunk_id"),
                    "filename": metadata_dict.get("filename"),
                    "file_type": metadata_dict.get("file_type"),
                    "embedding_model": metadata_dict.get("embedding_model"),
                    "tags": metadata_dict.get("tags"),
                }
                if STORE_TEXT_IN_VECTOR_DB and item.get("text"):
                    vector_payload["text"] = item["text"]
                points.append(
                    PointStruct(
                        id=point_id,
                        vector=vector,
                        payload=vector_payload,
                    )
                )
            if not points:
                logger.error("No valid embeddings to upsert.")
                return False
            self.client.upsert(collection_name=self.config.COLLECTION, points=points)
            logger.info(f"✅ Upserted {len(points)} embeddings into Qdrant.")
            return True
        except Exception as e:
            logger.error(f"❌ Error upserting embeddings: {e}", exc_info=True)
            return False
    # --------------------------------------------------
    # Search
    # --------------------------------------------------
    def search(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """Search Qdrant for nearest neighbors with optimized performance."""
        try:
            # Optimized: Only check collection if not already verified in this instance
            if not self.ensure_collection(len(query_vector)):
                logger.error("Search aborted due to collection dimension mismatch.")
                return []
            # Use optimized search parameters for better performance
            results = self.client.search(
                collection_name=self.config.COLLECTION,
                query_vector=query_vector,
                limit=top_k,
                with_payload=True,      # Explicitly request payload
                with_vectors=False,     # Don't return vectors to save bandwidth
                score_threshold=0.0,    # No filtering to avoid extra processing
            )
            
            formatted = [
                {"id": str(r.id), "score": float(r.score), "metadata": r.payload} for r in results
            ]
            logger.info(f"🔍 Search returned {len(formatted)} results in collection '{self.config.COLLECTION}'")
            return formatted
        except Exception as e:
            logger.error(f"❌ Error searching Qdrant: {e}", exc_info=True)
            return []
    # --------------------------------------------------
    # Delete by ID
    # --------------------------------------------------
    def delete_by_id(self, point_id: str) -> bool:
        """Delete a single vector by ID"""
        try:
            self.client.delete(
                collection_name=self.config.COLLECTION,
                points_selector={"points": [point_id]},
            )
            logger.info(f"Deleted point {point_id} from Qdrant.")
            return True
        except Exception as e:
            logger.error(f"Error deleting point {point_id}: {e}", exc_info=True)
            return False
    # --------------------------------------------------
    # Delete by Document
    # --------------------------------------------------
    def delete_by_doc(self, doc_id: str) -> bool:
        """Delete all vectors for a given document ID"""
        try:
            self.client.delete(
                collection_name=self.config.COLLECTION,
                points_selector=Filter(
                    must=[FieldCondition(key="document_id", match=MatchValue(value=doc_id))]
                ),
            )
            logger.info(f"Deleted all vectors for doc_id {doc_id}.")
            return True
        except Exception as e:
            logger.error(f"Error deleting vectors for doc_id {doc_id}: {e}", exc_info=True)
            return False
    # --------------------------------------------------
    # Clear Collection
    # --------------------------------------------------
    def clear_collection(self) -> bool:
        """Delete all vectors in the collection"""
        try:
            self.client.delete_collection(collection_name=self.config.COLLECTION)
            logger.info(f"Cleared collection {self.config.COLLECTION}.")
            return True
        except Exception as e:
            logger.error(
                f"Error clearing collection {self.config.COLLECTION}: {e}", exc_info=True
            )
            return False
