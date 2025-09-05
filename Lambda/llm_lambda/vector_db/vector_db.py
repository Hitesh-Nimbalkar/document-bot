

from utils.utils import CustomLogger, CustomException
logger = CustomLogger("QdrantVectorDB")
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
class QdrantConfig:
    HOST = os.getenv('VECTOR_DB_HOST', 'localhost')
    PORT = int(os.getenv('VECTOR_DB_PORT', '6333'))
    API_KEY = os.getenv('VECTOR_DB_API_KEY', '')
    COLLECTION = os.getenv('COLLECTION_NAME', 'document_embeddings')
    VECTOR_DIM = int(os.getenv('VECTOR_DIMENSION', '1536'))
class QdrantVectorDB:
    def __init__(self, config: QdrantConfig = QdrantConfig()):
        self.config = config
        if self.config.HOST in ['localhost', '127.0.0.1'] or self.config.HOST.startswith('192.168.'):
            self.client = QdrantClient(host=self.config.HOST, port=self.config.PORT)
        else:
            self.client = QdrantClient(url=f"https://{self.config.HOST}:{self.config.PORT}", api_key=self.config.API_KEY)
    def create_collection(self):
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
        try:
            self.create_collection()
            points = []
            for item in embeddings:
                vector = item.get('embedding') or item.get('vector')
                if not vector:
                    logger.warning(f"Missing embedding vector in item: {item}")
                    continue
                payload = {
                    'text': item.get('text', ''),
                    'document_id': item.get('document_id', ''),
                    'chunk_id': item.get('chunk_id', ''),
                    'source': item.get('source', ''),
                    'timestamp': datetime.utcnow().isoformat()
                }
                payload.update(item.get('metadata', {}))
                points.append(PointStruct(
                    id=item.get('id', str(uuid.uuid4())),
                    vector=vector,
                    payload=payload
                ))
            if not points:
                logger.error("No valid embeddings to upsert.")
                return False
            self.client.upsert(collection_name=self.config.COLLECTION, points=points)
            logger.info(f"Upserted {len(points)} embeddings to Qdrant.")
            return True
        except Exception as e:
            logger.error(f"Error upserting embeddings: {e}")
            return False
    def search_by_metadata(self, filters: Dict[str, Any], limit: int = 10) -> List[Dict]:
        from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
        conditions = []
        for key, value in filters.items():
            if isinstance(value, list):
                conditions.append(FieldCondition(key=f"metadata.{key}", match=MatchAny(any=value)))
            else:
                conditions.append(FieldCondition(key=f"metadata.{key}", match=MatchValue(value=value)))
        results = self.client.scroll(
            collection_name=self.config.COLLECTION,
            scroll_filter=Filter(must=conditions) if conditions else None,
            limit=limit,
            with_payload=True,
            with_vectors=False
        )
        return [
            {'id': point.id, 'payload': point.payload}
            for point in results[0]
        ]

class VectorSearchHelper:
    """Helper class for advanced search operations in Qdrant"""
    
    def __init__(self, vector_db: QdrantVectorDB):
        self.vector_db = vector_db
        self.client = vector_db.client
        self.collection_name = vector_db.config.COLLECTION_NAME
    
    def search_by_metadata(self, filters: Dict[str, Any], limit: int = 10) -> List[Dict]:
        """
        Search vectors using metadata filters
        
        Args:
            filters: Dictionary of filter conditions
            limit: Maximum number of results to return
            
        Example filters:
        {
            "project_id": "project1",
            "document_type": "pdf",
            "search_tags": ["domain:medical", "size:large"],
            "file_extension": "pdf"
        }
        """
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue, MatchAny
            
            conditions = []
            
            for key, value in filters.items():
                if isinstance(value, list):
                    # Handle list values (like search_tags)
                    conditions.append(
                        FieldCondition(key=f"metadata.{key}", match=MatchAny(any=value))
                    )
                else:
                    # Handle single values
                    conditions.append(
                        FieldCondition(key=f"metadata.{key}", match=MatchValue(value=value))
                    )
            
            # Perform the search
            results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(must=conditions) if conditions else None,
                limit=limit,
                with_payload=True,
                with_vectors=False
            )
            
            return [
                {
                    'id': point.id,
                    'score': 1.0,  # Perfect match for metadata search
                    'payload': point.payload
                }
                for point in results[0]
            ]
            
        except Exception as e:
            logger.error(f"Metadata search error: {e}")
            return []
    
    def search_by_content(self, query_text: str, limit: int = 10, filters: Dict[str, Any] = None) -> List[Dict]:
        """
        Search vectors by content similarity (requires query embedding)
        Note: This is a placeholder - you'll need to implement embedding generation for the query
        """
        try:
            # This would require generating an embedding for the query_text
            # You'd need to call your embedding service here
            logger.warning("Content search requires query embedding - implement embedding generation")
            return []
            
        except Exception as e:
            logger.error(f"Content search error: {e}")
            return []
    
    def get_document_stats(self, project_id: str = None) -> Dict[str, Any]:
        """
        Get statistics about documents in the vector database
        """
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            
            # Base filter
            filters = []
            if project_id:
                filters.append(
                    FieldCondition(key="metadata.project_id", match=MatchValue(value=project_id))
                )
            
            # Get all points with metadata
            results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(must=filters) if filters else None,
                limit=1000,  # Adjust based on your data size
                with_payload=True,
                with_vectors=False
            )
            
            points = results[0]
            
            # Calculate statistics
            stats = {
                'total_chunks': len(points),
                'projects': set(),
                'document_types': set(),
                'file_extensions': set(),
                'search_tags': set(),
                'documents': set()
            }
            
            for point in points:
                metadata = point.payload.get('metadata', {})
                stats['projects'].add(metadata.get('project_id', 'unknown'))
                stats['document_types'].add(metadata.get('document_type', 'unknown'))
                stats['file_extensions'].add(metadata.get('file_extension', 'unknown'))
                stats['documents'].add(metadata.get('filename', 'unknown'))
                
                # Collect search tags
                tags = metadata.get('search_tags', [])
                stats['search_tags'].update(tags)
            
            # Convert sets to lists for JSON serialization
            for key in ['projects', 'document_types', 'file_extensions', 'search_tags', 'documents']:
                stats[key] = list(stats[key])
            
            return stats
            
        except Exception as e:
            logger.error(f"Stats calculation error: {e}")
            return {}
    def find_similar_documents(self, document_id: str, limit: int = 5) -> List[Dict]:
        """
        Find documents similar to a given document based on metadata
        """
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            
            # First, get the source document
            source_results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(must=[
                    FieldCondition(key="metadata.filename", match=MatchValue(value=document_id))
                ]),
                limit=1,
                with_payload=True,
                with_vectors=False
            )
            
            if not source_results[0]:
                return []
            
            source_metadata = source_results[0][0].payload.get('metadata', {})
            
            # Find similar documents based on project and type
            similar_results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(must=[
                    FieldCondition(key="metadata.project_id", 
                                 match=MatchValue(value=source_metadata.get('project_id'))),
                    FieldCondition(key="metadata.document_type", 
                                 match=MatchValue(value=source_metadata.get('document_type')))
                ]),
                limit=limit + 1,  # +1 to account for the source document
                with_payload=True,
                with_vectors=False
            )
            
            # Filter out the source document
            similar_docs = [
                {
                    'id': point.id,
                    'filename': point.payload.get('metadata', {}).get('filename'),
                    'similarity_reason': 'same_project_and_type',
                    'metadata': point.payload.get('metadata', {})
                }
                for point in similar_results[0]
                if point.payload.get('metadata', {}).get('filename') != document_id
            ]
            
            return similar_docs[:limit]
            
        except Exception as e:
            logger.error(f"Similar documents search error: {e}")
            return []

class VectorDBManager:
    def __init__(self):
        self.config = VectorDBConfig()
        self.vector_db = QdrantVectorDB(self.config)
        self.search_helper = VectorSearchHelper(self.vector_db)
    def search_documents(self, search_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Unified search interface for documents
        
        search_params can include:
        - filters: metadata filters
        - query_text: text to search for (future implementation)
        - limit: number of results
        - search_type: 'metadata', 'content', or 'hybrid'
        """
        search_type = search_params.get('search_type', 'metadata')
        limit = search_params.get('limit', 10)
        filters = search_params.get('filters', {})
        
        try:
            if search_type == 'metadata':
                results = self.search_helper.search_by_metadata(filters, limit)
            elif search_type == 'content':
                query_text = search_params.get('query_text', '')
                results = self.search_helper.search_by_content(query_text, limit, filters)
            else:
                # Hybrid search - combine metadata and content (future implementation)
                results = self.search_helper.search_by_metadata(filters, limit)
            
            return {
                'success': True,
                'results': results,
                'total_found': len(results),
                'search_params': search_params
            }
            
        except Exception as e:
            logger.error(f"Search error: {e}")
            return {
                'success': False,
                'error': str(e),
                'results': [],
                'total_found': 0
            }
    def get_database_info(self, project_id: str = None) -> Dict[str, Any]:
        """
        Get comprehensive information about the vector database
        """
        try:
            stats = self.search_helper.get_document_stats(project_id)
            collection_info = self.vector_db.client.get_collection(self.config.COLLECTION_NAME)
            
            return {
                'success': True,
                'collection_name': self.config.COLLECTION_NAME,
                'collection_info': {
                    'vectors_count': collection_info.vectors_count,
                    'points_count': collection_info.points_count,
                    'status': collection_info.status.value
                },
                'document_stats': stats,
                'vector_dimension': self.config.VECTOR_DIMENSION
            }
            
        except Exception as e:
            logger.error(f"Database info error: {e}")
            return {
                'success': False,
                'error': str(e)
            }
    def extract_content_metadata(self, text: str, filename: str) -> Dict[str, Any]:
        """
        Extract searchable metadata from content text
        """
        content_metadata = {}
        
        # Basic text analytics
        word_count = len(text.split())
        char_count = len(text)
        
        # Extract potential keywords (simple approach - can be enhanced with NLP)
        words = text.lower().split()
        common_words = {'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must', 'can', 'this', 'that', 'these', 'those'}
        keywords = [word for word in words if len(word) > 3 and word not in common_words][:10]  # Top 10 potential keywords
        
        # File type analysis
        file_extension = filename.split('.')[-1].lower() if '.' in filename else 'unknown'
        
        content_metadata.update({
            'word_count': word_count,
            'char_count': char_count,
            'content_keywords': keywords,
            'file_extension': file_extension,
            'has_numbers': any(char.isdigit() for char in text),
            'has_urls': 'http' in text.lower() or 'www.' in text.lower(),
            'language_detected': 'en',  # Could be enhanced with language detection
        })
        
        return content_metadata
    def create_search_tags(self, project_name: str, doc_type: str, filename: str, content: str) -> List[str]:
        """
        Create comprehensive search tags for better discoverability
        """
        tags = []
        
        # Project-level tags
        tags.append(f"project:{project_name}")
        tags.append(f"type:{doc_type}")
        
        # File-level tags
        file_base = filename.split('.')[0].lower()
        tags.append(f"file:{file_base}")
        
        if '.' in filename:
            file_ext = filename.split('.')[-1].lower()
            tags.append(f"format:{file_ext}")
        
        # Content-based tags
        content_lower = content.lower()
        
        # Domain-specific tagging (customize based on your domain)
        domain_keywords = {
            'medical': ['patient', 'diagnosis', 'treatment', 'medical', 'clinical', 'therapy', 'disease', 'symptom'],
            'technical': ['system', 'software', 'hardware', 'technical', 'specification', 'requirements', 'api'],
            'business': ['revenue', 'profit', 'business', 'strategy', 'market', 'customer', 'sales'],
            'research': ['study', 'research', 'analysis', 'methodology', 'results', 'conclusion', 'findings'],
            'legal': ['contract', 'agreement', 'legal', 'policy', 'compliance', 'regulation', 'terms']
        }
        
        for domain, keywords in domain_keywords.items():
            if any(keyword in content_lower for keyword in keywords):
                tags.append(f"domain:{domain}")
        
        # Size-based tags
        word_count = len(content.split())
        if word_count < 100:
            tags.append("size:small")
        elif word_count < 500:
            tags.append("size:medium")
        else:
            tags.append("size:large")
        
        return tags

