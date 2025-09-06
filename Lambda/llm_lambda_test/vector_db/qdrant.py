import os
import uuid
from datetime import datetime
from typing import List, Dict, Any

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from utils.utils import CustomLogger
from models.metadata_model import MetadataModel  # Pydantic metadata model
from services.dynamo_service import DynamoMetadataService  # DynamoDB wrapper

logger = CustomLogger("QdrantVectorDB")


class QdrantConfig:
    HOST = os.getenv("VECTOR_DB_HOST", "localhost")
    PORT = int(os.getenv("VECTOR_DB_PORT", "6333"))
    API_KEY = os.getenv("VECTOR_DB_API_KEY", "")
    COLLECTION = os.getenv("COLLECTION_NAME", "document_embeddings")
    VECTOR_DIM = int(os.getenv("VECTOR_DIMENSION", "1536"))


class QdrantVectorDB:
    """Handles vector storage and retrieval in Qdrant with DynamoDB metadata integration"""

    def __init__(self, config: QdrantConfig = QdrantConfig()):
        self.config = config

        # Connect to Qdrant (local vs remote)
        if self.config.HOST in ["localhost", "127.0.0.1"] or self.config.HOST.startswith("192.168."):
            self.client = QdrantClient(host=self.config.HOST, port=self.config.PORT)
        else:
            self.client = QdrantClient(
                url=f"https://{self.config.HOST}:{self.config.PORT}",
                api_key=self.config.API_KEY
            )

        # DynamoDB service (optional here if you also save metadata in Dynamo)
        self.dynamo_service = DynamoMetadataService()

    def create_collection(self):
        """Ensure Qdrant collection exists"""
        try:
            collections = self.client.get_collections()
            if self.config.COLLECTION not in [col.name for col in collections.collections]:
                self.client.create_collection(
                    collection_name=self.config.COLLECTION,
                    vectors_config=VectorParams(size=self.config.VECTOR_DIM, distance=Distance.COSINE)
                )
                logger.info(f"Created collection: {self.config.COLLECTION}")
            else:
                logger.info(f"Collection already exists: {self.config.COLLECTION}")
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            raise

    def upsert_embeddings(self, embeddings: List[Dict[str, Any]]) -> bool:
        """
        Store embeddings in Qdrant with the full metadata dictionary attached.
        """
        try:
            self.create_collection()
            points = []

            for item in embeddings:
                vector = item.get("embedding") or item.get("vector")
                if not vector:
                    logger.warning(f"Skipping item without vector: {item}")
                    continue

                metadata_dict = item.get("metadata")
                if not metadata_dict:
                    logger.warning(f"Skipping item without metadata: {item}")
                    continue

                # Optional: ensure each point has a unique id
                point_id = item.get("id", str(uuid.uuid4()))

                points.append(PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=metadata_dict  # attach the entire metadata dict
                ))

            if not points:
                logger.error("No valid embeddings to upsert.")
                return False

            self.client.upsert(collection_name=self.config.COLLECTION, points=points)
            logger.info(f"Upserted {len(points)} embeddings to Qdrant with full metadata attached.")
            return True

        except Exception as e:
            logger.error(f"Error upserting embeddings: {e}")
            return False
