

# =====================================================
# Connection Pool Manager
# =====================================================
"""
Singleton connection pool manager to reuse expensive connections across Lambda invocations.
This reduces cold start times and improves performance by reusing:
- Qdrant client connections
- DynamoDB client connections  
- Bedrock client connections
"""
import os
import boto3
from typing import Optional, Dict, Any
from qdrant_client import QdrantClient
from utils.logger import CustomLogger
logger = CustomLogger(__name__)
class ConnectionPool:
    """Singleton connection pool for reusing expensive client connections"""
    
    _instance = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._qdrant_client = None
            self._dynamodb_resource = None
            self._bedrock_client = None
            self._s3_client = None
            ConnectionPool._initialized = True
            logger.info("🏊 ConnectionPool initialized")
    
    # ====================================================
    # Qdrant Client
    # ====================================================
    def get_qdrant_client(self, host: str = None, port: int = None, api_key: str = None) -> QdrantClient:
        """Get or create a reusable Qdrant client"""
        if self._qdrant_client is None:
            host = host or os.getenv("VECTOR_DB_HOST")
            port = port or int(os.getenv("VECTOR_DB_PORT", "6333"))
            api_key = api_key or os.getenv("VECTOR_DB_API_KEY")
            
            try:
                if host in ["localhost", "127.0.0.1"] or host.startswith("192.168."):
                    self._qdrant_client = QdrantClient(host=host, port=port)
                    logger.info(f"🔗 Qdrant client connected to {host}:{port}")
                else:
                    self._qdrant_client = QdrantClient(
                        url=f"https://{host}:{port}",
                        api_key=api_key,
                        timeout=30,  # Increase timeout for remote connections
                        prefer_grpc=False  # Use HTTP for better Lambda compatibility
                    )
                    logger.info(f"🔗 Qdrant client connected to {host}:{port} (remote)")
            except Exception as e:
                logger.error(f"❌ Failed to create Qdrant client: {e}")
                raise
                
        return self._qdrant_client
    
    # ====================================================
    # DynamoDB Resource
    # ====================================================
    def get_dynamodb_resource(self, region_name: str = None) -> any:
        """Get or create a reusable DynamoDB resource"""
        if self._dynamodb_resource is None:
            region = region_name or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
            try:
                self._dynamodb_resource = boto3.resource("dynamodb", region_name=region)
                logger.info(f"🔗 DynamoDB resource connected to {region}")
            except Exception as e:
                logger.error(f"❌ Failed to create DynamoDB resource: {e}")
                raise
                
        return self._dynamodb_resource
    
    # ====================================================
    # Bedrock Client  
    # ====================================================
    def get_bedrock_client(self, region_name: str = None) -> any:
        """Get or create a reusable Bedrock client"""
        if self._bedrock_client is None:
            region = region_name or os.getenv("BEDROCK_REGION", "ap-south-1")
            try:
                self._bedrock_client = boto3.client(
                    "bedrock-runtime", 
                    region_name=region,
                    config=boto3.session.Config(
                        max_pool_connections=50,  # Connection pooling
                        retries={'max_attempts': 2}
                    )
                )
                logger.info(f"🔗 Bedrock client connected to {region}")
            except Exception as e:
                logger.error(f"❌ Failed to create Bedrock client: {e}")
                raise
                
        return self._bedrock_client
    
    # ====================================================
    # S3 Client
    # ====================================================
    def get_s3_client(self, region_name: str = None) -> any:
        """Get or create a reusable S3 client"""
        if self._s3_client is None:
            region = region_name or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
            try:
                self._s3_client = boto3.client(
                    "s3",
                    region_name=region,
                    config=boto3.session.Config(
                        max_pool_connections=50
                    )
                )
                logger.info(f"🔗 S3 client connected to {region}")
            except Exception as e:
                logger.error(f"❌ Failed to create S3 client: {e}")
                raise
                
        return self._s3_client
    
    # ====================================================
    # Connection Status
    # ====================================================
    def get_status(self) -> Dict[str, bool]:
        """Get connection pool status for debugging"""
        return {
            "qdrant_connected": self._qdrant_client is not None,
            "dynamodb_connected": self._dynamodb_resource is not None,
            "bedrock_connected": self._bedrock_client is not None,
            "s3_connected": self._s3_client is not None,
        }
    
    def reset_connections(self):
        """Reset all connections (useful for testing)"""
        self._qdrant_client = None
        self._dynamodb_resource = None
        self._bedrock_client = None
        self._s3_client = None
        logger.info("🔄 All connections reset")
# Global singleton instance
connection_pool = ConnectionPool()
