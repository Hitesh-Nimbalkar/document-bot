import boto3
from utils.logger import CustomLogger

logger = CustomLogger("DynamoMetadataService")

class DynamoMetadataService:
    def __init__(self, table_name: str = "document-metadata"):
        self.table = boto3.resource("dynamodb").Table(table_name)

    def save_metadata(self, item: dict):
        try:
            self.table.put_item(Item=item)
            logger.info(f"Saved metadata for doc {item.get('document_id')}")
            return True
        except Exception as e:
            logger.error(f"Error saving metadata: {e}", exc_info=True)
            return False

    def get_metadata(self, document_id: str):
        try:
            response = self.table.get_item(Key={"document_id": document_id})
            return response.get("Item")
        except Exception as e:
            logger.error(f"Error getting metadata for {document_id}: {e}", exc_info=True)
            return None
