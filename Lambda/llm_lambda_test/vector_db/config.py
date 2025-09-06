
# """
# Combined Embedding and Vector Database Lambda Function
# This module combines the functionality of both embedding generation and vector database
# operations in a single file with proper class organization. It can process documents,
# generate embeddings, and store them directly in Qdrant Vector DB.
# """
# import json
# import boto3
# import os
# import logging
# import uuid
# import traceback
# from datetime import datetime
# from typing import List, Dict, Any, Optional
# import fitz  # PyMuPDF - version 1.22.5 uses direct fitz import
# from langchain_text_splitters import RecursiveCharacterTextSplitter
# # Qdrant Imports
# from qdrant_client import QdrantClient
# from qdrant_client.models import Distance, VectorParams, PointStruct
# # Configure Logging
# logger = logging.getLogger()
# logger.setLevel(logging.INFO)

# class VectorDBConfig:
#     """Configuration class for vector database settings"""
    
#     VECTOR_DB_HOST = os.getenv('VECTOR_DB_HOST', 'localhost')
#     VECTOR_DB_PORT = os.getenv('VECTOR_DB_PORT', '6333')
#     VECTOR_DB_API_KEY = os.getenv('VECTOR_DB_API_KEY', '')
#     COLLECTION_NAME = os.getenv('COLLECTION_NAME', 'document_embeddings')
#     VECTOR_DIMENSION = int(os.getenv('VECTOR_DIMENSION', '1536'))

