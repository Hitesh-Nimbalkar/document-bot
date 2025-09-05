
from vector_db.qdrant import QdrantVectorDB
from vector_db.vector_db import EmbeddingModel
def retrieve_relevant_chunks(query: str, payload: dict, top_k: int = 5):
    """
    Retrieve top_k relevant chunks from the vector DB for the given query.
    """
    # Generate embedding for the query
    embedding_model = EmbeddingModel()
    query_embedding = embedding_model.embed(query)
    # Search in Qdrant
    qdrant_db = QdrantVectorDB()
    # You can add filters from payload if needed
    results = qdrant_db.client.search(
        collection_name=qdrant_db.config.COLLECTION,
        query_vector=query_embedding,
        limit=top_k,
        with_payload=True
    )
    # Return the retrieved chunks (text and metadata)
    return [
        {
            'text': point.payload.get('text', ''),
            'metadata': point.payload
        }
        for point in results
    ]
