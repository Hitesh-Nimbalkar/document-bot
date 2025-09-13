import os
import uuid
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from utils.utils import CustomLogger
from models.metadata_model import MetadataModel  # Pydantic metadata model
from services.dynamo_service import DynamoMetadataService  # DynamoDB wrapper
logger = CustomLogger("QdrantVectorDB")
import os

STORE_TEXT_IN_VECTOR_DB = os.getenv("STORE_TEXT_IN_VECTOR_DB", "true").lower() == "true"


class QdrantConfig:
    """Configuration for Qdrant connection"""
    HOST: str = os.getenv("VECTOR_DB_HOST", "03e01705-fc18-488f-ace1-b2008e0423cf.us-west-2-0.aws.cloud.qdrant.io")
    PORT: int = int(os.getenv("VECTOR_DB_PORT", "6333"))
    API_KEY: str = os.getenv("VECTOR_DB_API_KEY", "")
    COLLECTION: str = os.getenv("COLLECTION_NAME", "Demo")
    VECTOR_DIM: int = int(os.getenv("VECTOR_DIMENSION", "1536"))


class QdrantVectorDB:
    """Handles vector storage and retrieval in Qdrant with DynamoDB metadata integration"""

    def __init__(self, config: QdrantConfig = QdrantConfig()):
        self.config = config

        # Connect to Qdrant (local or remote)
        if self.config.HOST in ["localhost", "127.0.0.1"] or self.config.HOST.startswith("192.168."):
            self.client = QdrantClient(host=self.config.HOST, port=self.config.PORT)
        else:
            self.client = QdrantClient(
                url=f"https://{self.config.HOST}:{self.config.PORT}",
                api_key=self.config.API_KEY,
            )

        # DynamoDB service for metadata
        self.dynamo_service = DynamoMetadataService()

    def create_collection(self) -> None:
        """Ensure Qdrant collection exists"""
        try:
            collections = self.client.get_collections()
            existing = [col.name for col in collections.collections]

            if self.config.COLLECTION not in existing:
                self.client.create_collection(
                    collection_name=self.config.COLLECTION,
                    vectors_config=VectorParams(
                        size=self.config.VECTOR_DIM,
                        distance=Distance.COSINE,
                    ),
                )
                logger.info(f"Created collection: {self.config.COLLECTION}")
            else:
                logger.info(f"Collection already exists: {self.config.COLLECTION}")
        except Exception as e:
            logger.error(f"Error creating collection: {e}", exc_info=True)
            raise

    def upsert_embeddings(self, embeddings: List[Dict[str, Any]]) -> bool:
        """
        Store embeddings in Qdrant with metadata attached.

        Args:
            embeddings: List of dicts with keys:
                - "embedding" or "vector": list[float]
                - "metadata": dict
                - optional "id": str
        """
        if not embeddings:
            logger.warning("No embeddings provided to upsert.")
            return False

        try:
            self.create_collection()
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
                
                # Select relevant metadata
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
                    "text": item.get("text"),
                }

                # Conditionally include text
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

            self.client.upsert(
                collection_name=self.config.COLLECTION,
                points=points,
            )
            logger.info(f"Upserted {len(points)} embeddings into Qdrant.")
            return True

        except Exception as e:
            logger.error(f"Error upserting embeddings: {e}", exc_info=True)
            return False

    def search(self, query_vector: List[float], top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search Qdrant for nearest neighbors.

        Args:
            query_vector: List[float] query embedding
            top_k: number of results to return

        Returns:
            List of dicts with {id, score, metadata}
        """
        try:
            self.create_collection()
            results = self.client.search(
                collection_name=self.config.COLLECTION,
                query_vector=query_vector,
                limit=top_k,
            )
            formatted = [
                {"id": r.id, "score": r.score, "metadata": r.payload}
                for r in results
            ]
            logger.info(f"Search returned {len(formatted)} results.")
            return formatted
        except Exception as e:
            logger.error(f"Error searching Qdrant: {e}", exc_info=True)
            return []

    def delete_by_id(self, point_id: str) -> bool:
        """Delete a single vector by ID"""
        try:
            self.client.delete(
                collection_name=self.config.COLLECTION,
                points_selector=[point_id],
            )
            logger.info(f"Deleted point {point_id} from Qdrant.")
            return True
        except Exception as e:
            logger.error(f"Error deleting point {point_id}: {e}", exc_info=True)
            return False

    def delete_by_doc(self, doc_id: str) -> bool:
        """Delete all vectors for a given document ID"""
        try:
            self.client.delete(
                collection_name=self.config.COLLECTION,
                points_selector=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                ),
            )
            logger.info(f"Deleted all vectors for doc_id {doc_id}.")
            return True
        except Exception as e:
            logger.error(f"Error deleting vectors for doc_id {doc_id}: {e}", exc_info=True)
            return False

    def clear_collection(self) -> bool:
        """Delete all vectors in the collection"""
        try:
            self.client.delete_collection(self.config.COLLECTION)
            logger.info(f"Cleared collection {self.config.COLLECTION}.")
            return True
        except Exception as e:
            logger.error(f"Error clearing collection {self.config.COLLECTION}: {e}", exc_info=True)
            return False
