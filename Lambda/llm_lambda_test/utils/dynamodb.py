

import boto3
from typing import Dict, List, Any, Optional
from botocore.exceptions import ClientError
from utils.logger import CustomLogger
from utils.connection_pool import connection_pool
logger = CustomLogger(__name__)

# ======================================================
# Enhanced DynamoDB Client
# ======================================================
class EnhancedDynamoDBClient:
    """
    Enhanced DynamoDB client with connection pooling for better performance.
    Uses singleton connection pool to reuse expensive client connections.
    """
    def __init__(self, region_name: str = None):
        """Initialize the DynamoDB client using connection pool"""
        try:
            self.region_name = region_name
            # Use connection pool instead of creating new clients
            self.dynamodb = connection_pool.get_dynamodb_resource(region_name)
            self.client = self.dynamodb.meta.client  # Get client from resource
            logger.info("✅ DynamoDB client initialized with connection pooling")
        except Exception as e:
            logger.error(f"💥 Failed to initialize DynamoDB client: {e}")
            raise
    # --------------------------------------------------
    # Table Access
    # --------------------------------------------------
    def get_table(self, table_name: str):
        """Get a DynamoDB table resource with validation"""
        try:
            table = self.dynamodb.Table(table_name)
            table.load()  # Verify table exists
            logger.debug(f"📋 Connected to table: {table_name}")
            return table
        except ClientError as e:
            if e.response["Error"]["Code"] == "ResourceNotFoundException":
                logger.error(f"💥 Table {table_name} not found")
                raise ValueError(f"Table {table_name} does not exist")
            else:
                logger.error(f"💥 Error connecting to table {table_name}: {e}")
                raise
    # --------------------------------------------------
    # Put Item
    # --------------------------------------------------
    def put_item(
        self,
        table_name: str,
        item: Dict[str, Any],
        condition_expression: str = None,
    ) -> bool:
        """Put an item into a DynamoDB table with optional condition"""
        try:
            table = self.get_table(table_name)
            put_params = {"Item": item}
            if condition_expression:
                put_params["ConditionExpression"] = condition_expression
            table.put_item(**put_params)
            logger.info(f"✅ Item saved to {table_name}")
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning(f"⚠️ Conditional check failed for {table_name}")
                return False
            else:
                logger.error(f"💥 Error saving item to {table_name}: {e}")
                return False
        except Exception as e:
            logger.error(f"💥 Unexpected error saving to {table_name}: {e}")
            return False
    # --------------------------------------------------
    # Get Item
    # --------------------------------------------------
    def get_item(
        self,
        table_name: str,
        key: Dict[str, Any],
        consistent_read: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Get an item from a DynamoDB table"""
        try:
            table = self.get_table(table_name)
            response = table.get_item(Key=key, ConsistentRead=consistent_read)
            item = response.get("Item")
            if item:
                logger.info(f"✅ Item retrieved from {table_name}")
                return item
            else:
                logger.info(f"📭 Item not found in {table_name}")
                return None
        except ClientError as e:
            logger.error(f"💥 Error getting item from {table_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"💥 Unexpected error getting item from {table_name}: {e}")
            return None
    # --------------------------------------------------
    # Update Item
    # --------------------------------------------------
    def update_item(
        self,
        table_name: str,
        key: Dict[str, Any],
        update_expression: str,
        expression_attribute_values: Dict[str, Any] = None,
        expression_attribute_names: Dict[str, str] = None,
        condition_expression: str = None,
    ) -> bool:
        """Update an item in a DynamoDB table"""
        try:
            table = self.get_table(table_name)
            update_params = {
                "Key": key,
                "UpdateExpression": update_expression,
                "ReturnValues": "UPDATED_NEW",
            }
            if expression_attribute_values:
                update_params["ExpressionAttributeValues"] = expression_attribute_values
            if expression_attribute_names:
                update_params["ExpressionAttributeNames"] = expression_attribute_names
            if condition_expression:
                update_params["ConditionExpression"] = condition_expression
            table.update_item(**update_params)
            logger.info(f"✅ Item updated in {table_name}")
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning(f"⚠️ Conditional check failed for update in {table_name}")
                return False
            else:
                logger.error(f"💥 Error updating item in {table_name}: {e}")
                return False
        except Exception as e:
            logger.error(f"💥 Unexpected error updating item in {table_name}: {e}")
            return False
    # --------------------------------------------------
    # Delete Item
    # --------------------------------------------------
    def delete_item(
        self, table_name: str, key: Dict[str, Any], condition_expression: str = None
    ) -> bool:
        """Delete an item from a DynamoDB table"""
        try:
            table = self.get_table(table_name)
            delete_params = {"Key": key}
            if condition_expression:
                delete_params["ConditionExpression"] = condition_expression
            table.delete_item(**delete_params)
            logger.info(f"✅ Item deleted from {table_name}")
            return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                logger.warning(f"⚠️ Conditional check failed for delete in {table_name}")
                return False
            else:
                logger.error(f"💥 Error deleting item from {table_name}: {e}")
                return False
        except Exception as e:
            logger.error(f"💥 Unexpected error deleting item from {table_name}: {e}")
            return False
    # --------------------------------------------------
    # Query Items
    # --------------------------------------------------
    def query_items(
        self,
        table_name: str,
        key_condition_expression: str,
        expression_attribute_values: Dict[str, Any] = None,
        expression_attribute_names: Dict[str, str] = None,
        filter_expression: str = None,
        index_name: str = None,
        limit: int = None,
        scan_index_forward: bool = True,
    ) -> List[Dict[str, Any]]:
        """Query items from a DynamoDB table - matches metadata.py call pattern"""
        try:
            table = self.get_table(table_name)
            if isinstance(key_condition_expression, str):
                query_params = {
                    "KeyConditionExpression": key_condition_expression,
                    "ScanIndexForward": scan_index_forward,
                }
            else:  # fallback for legacy usage
                query_params = {
                    "KeyConditionExpression": str(key_condition_expression),
                    "ScanIndexForward": scan_index_forward,
                }
            if expression_attribute_values:
                query_params["ExpressionAttributeValues"] = expression_attribute_values
            if expression_attribute_names:
                query_params["ExpressionAttributeNames"] = expression_attribute_names
            if filter_expression:
                query_params["FilterExpression"] = filter_expression
            if index_name:
                query_params["IndexName"] = index_name
            if limit:
                query_params["Limit"] = limit
            response = table.query(**query_params)
            items = response.get("Items", [])
            logger.info(f"✅ Query returned {len(items)} items from {table_name}")
            return items
        except ClientError as e:
            logger.error(f"💥 Error querying {table_name}: {e}")
            return []
        except Exception as e:
            logger.error(f"💥 Unexpected error querying {table_name}: {e}")
            return []
    # --------------------------------------------------
    # Scan Items
    # --------------------------------------------------
    def scan_items(
        self,
        table_name: str,
        filter_expression: str = None,
        expression_attribute_values: Dict[str, Any] = None,
        expression_attribute_names: Dict[str, str] = None,
        limit: int = None,
    ) -> List[Dict[str, Any]]:
        """Scan items from a DynamoDB table (use sparingly for large tables)"""
        try:
            table = self.get_table(table_name)
            scan_params = {}
            if filter_expression:
                scan_params["FilterExpression"] = filter_expression
            if expression_attribute_values:
                scan_params["ExpressionAttributeValues"] = expression_attribute_values
            if expression_attribute_names:
                scan_params["ExpressionAttributeNames"] = expression_attribute_names
            if limit:
                scan_params["Limit"] = limit
            response = table.scan(**scan_params)
            items = response.get("Items", [])
            logger.info(f"✅ Scan returned {len(items)} items from {table_name}")
            return items
        except ClientError as e:
            logger.error(f"💥 Error scanning {table_name}: {e}")
            return []
        except Exception as e:
            logger.error(f"💥 Unexpected error scanning {table_name}: {e}")
            return []

# ======================================================
# Metadata Service
# ======================================================
class DynamoMetadataService(EnhancedDynamoDBClient):
    """Enhanced metadata service that inherits from EnhancedDynamoDBClient"""
    def __init__(self, table_name: str = "document-metadata", region_name: str = None):
        super().__init__(region_name)
        self.table_name = table_name
        logger.info(f"✅ DynamoMetadataService initialized for table: {table_name}")
    def save_metadata(self, item: Dict[str, Any]) -> bool:
        """Save document metadata using enhanced put_item"""
        return self.put_item(self.table_name, item)
    def get_metadata(self, document_id: str) -> Optional[Dict[str, Any]]:
        """Get document metadata by document_id"""
        return self.get_item(self.table_name, {"document_id": document_id})
    def update_metadata(self, document_id: str, updates: Dict[str, Any]) -> bool:
        """Update document metadata with provided updates"""
        update_expression_parts = []
        expression_values = {}
        expression_names = {}
        for key, value in updates.items():
            attr_name = f"#attr_{key}"
            attr_value = f":val_{key}"
            update_expression_parts.append(f"{attr_name} = {attr_value}")
            expression_values[attr_value] = value
            expression_names[attr_name] = key
        update_expression = "SET " + ", ".join(update_expression_parts)
        return self.update_item(
            self.table_name,
            {"document_id": document_id},
            update_expression,
            expression_values,
            expression_names,
        )
    def delete_metadata(self, document_id: str) -> bool:
        """Delete document metadata by document_id"""
        return self.delete_item(self.table_name, {"document_id": document_id})
    def find_by_content_hash(self, content_hash: str) -> List[Dict[str, Any]]:
        """Find documents by content hash using GSI - matches MetadataManager structure"""
        return self.query_items(
            self.table_name,
            key_condition_expression="content_hash = :hash",
            expression_attribute_values={":hash": content_hash},
            index_name="content_hash-index",
        )

