
"""enhanced_retriever.py
Encapsulates EnhancedRetriever responsible for vector + metadata retrieval.
"""
from typing import List, Dict
from utils.logger import CustomLogger
from vector_db.vector_db import QdrantVectorDB
logger = CustomLogger(__name__)
class EnhancedRetriever:
    """Handles metadata-aware document retrieval with fallback strategies"""
    def __init__(self):
        self.retriever = QdrantVectorDB()
        logger.info("📚 EnhancedRetriever initialized")
    def retrieve_with_metadata(self, query_embedding: List[float], filters: dict, top_k: int = 5) -> List[Dict]:
        """Enhanced retrieval using metadata filters and vector similarity"""
        try:
            results = self.retriever.search(
                query_vector=query_embedding,
                top_k=top_k * 2,
                filter=filters if filters["must"] or filters["should"] else None
            )
            if not results and (filters["must"] or filters["should"]):
                logger.info("🔄 No results with filters, trying without filters...")
                results = self.retriever.search(query_vector=query_embedding, top_k=top_k)
            return results[:top_k]
        except Exception as e:
            logger.error(f"💥 Error in metadata-aware retrieval: {e}")
            return self.retriever.search(query_vector=query_embedding, top_k=top_k)

