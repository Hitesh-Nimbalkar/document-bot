
import os
import boto3
from botocore.exceptions import ClientError
from datetime import datetime
from utils import CustomLogger, CustomException
from models.models import MetadataModel
logger = CustomLogger(__name__)
dynamodb = boto3.resource('dynamodb')
DDB_TABLE = os.environ.get('METADATA_TABLE')
CONTENT_HASH_KEY = os.environ.get('CONTENT_HASH_KEY', 'content_hash')

def build_metadata_dict(s3_key: str, project_name: str, user_id: str, content_hash: str, session_id: str, ingest_source: str, source_path: str, embedding_model: str = None):
    """
    Build and validate a metadata dictionary for DynamoDB using MetadataModel.
    All fields are required. Optionally include embedding_model.
    """
    logger.info(f"Building metadata for s3_key={s3_key}, project_name={project_name}, user_id={user_id}, content_hash={content_hash}, session_id={session_id}, ingest_source={ingest_source}, source_path={source_path}, embedding_model={embedding_model}")
    metadata_dict = {
        's3_key': s3_key,
        'project_name': project_name,
        'user_id': user_id,
        'upload_timestamp': datetime.utcnow().isoformat(),
        'content_hash': content_hash,
        'session_id': session_id,
        'ingest_source': ingest_source,
        'source_path': source_path,
        'embedding_model': embedding_model,
    }
    logger.info(f"Metadata dict before validation: {metadata_dict}")
    metadata_obj = MetadataModel(**metadata_dict)
    logger.info(f"Validated metadata object: {metadata_obj}")
    return metadata_obj
def check_metadata_exists(content_hash: str, ddb_table=None, content_hash_key=None, embedding_model=None):
    """
    Check if (1) any document with the same content_hash exists, and (2) if a document with the same content_hash and embedding_model exists.
    Returns (any_exists, exact_exists)
    """
    if ddb_table is None:
        ddb_table = DDB_TABLE
    if content_hash_key is None:
        content_hash_key = CONTENT_HASH_KEY
    table = dynamodb.Table(ddb_table)
    try:
        logger.info(f"Checking for any metadata in DynamoDB for content_hash: {content_hash}")
        response_any = table.scan(
            FilterExpression=f"{content_hash_key} = :h",
            ExpressionAttributeValues={':h': content_hash}
        )
        any_exists = bool(response_any['Items'])
        logger.info(f"Any metadata exists: {any_exists}")
        exact_exists = False
        if embedding_model is not None:
            logger.info(f"Checking for exact metadata in DynamoDB for content_hash: {content_hash} and embedding_model: {embedding_model}")
            response_exact = table.scan(
                FilterExpression=f"{content_hash_key} = :h AND embedding_model = :e",
                ExpressionAttributeValues={':h': content_hash, ':e': embedding_model}
            )
            exact_exists = bool(response_exact['Items'])
            logger.info(f"Exact metadata exists: {exact_exists}")
    except Exception as e:
        logger.error(f"Error querying DynamoDB: {str(e)}")
        raise CustomException(f"Error querying DynamoDB: {str(e)}")
    return any_exists, exact_exists
def create_and_check_metadata(s3_key: str, project_name: str, user_id: str, content_hash: str, session_id: str = None, ingest_source: str = None, source_path: str = None, embedding_model: str = None, ddb_table=None, content_hash_key=None):
    """
    Build metadata and check if it exists in DynamoDB by content_hash and embedding_model.
    Returns (metadata_dict, (any_exists, exact_exists))
    """
    metadata_obj = build_metadata_dict(s3_key, project_name, user_id, content_hash, session_id, ingest_source, source_path, embedding_model)
    # Convert to dict for DynamoDB, but use the correct content_hash_key
    metadata = metadata_obj.dict()
    if content_hash_key is None:
        content_hash_key = CONTENT_HASH_KEY
    if content_hash_key != 'content_hash':
        metadata[content_hash_key] = metadata.pop('content_hash')
    any_exists, exact_exists = check_metadata_exists(content_hash, ddb_table, content_hash_key=content_hash_key, embedding_model=embedding_model)
    logger.info(f"Final metadata dict for DynamoDB: {metadata}")
    return metadata, (any_exists, exact_exists)
