
from models.models import ChatHistoryModel
import boto3
import os
import uuid
from datetime import datetime
from typing import List, Dict, Any
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
# ---------------------------
# Chat message (LangChain compatible)
# ---------------------------
class ChatMessage(BaseModel):
    message_id: str
    timestamp: str
    role: str  # 'user', 'assistant', or 'system'
    content: str
    reply_to: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

    model_config = {
        "populate_by_name": True,  # allows using alias names if needed
    }

# ---------------------------
# Chat history for a session
# ---------------------------
class ChatHistoryModel(BaseModel):
    project_id: str
    user_id: str
    session_id: str
    messages: List[ChatMessage] = Field(default_factory=list)


class ChatHistory:
    @staticmethod
    def as_pydantic_model(history_dict) -> 'ChatHistoryModel':
        """
        Converts a dict (as returned by get_recent_history) to a ChatHistoryModel instance.
        """
        return ChatHistoryModel.parse_obj(history_dict)
    """
    Manages chat history for a session in DynamoDB.
    Table is expected to have 'session_id' as the partition key and store project_id, user_id, and messages.
    """
    def __init__(self, table_name: str = None):
        self.dynamodb = boto3.resource('dynamodb')
        self.table_name = table_name or os.environ.get('CHAT_HISTORY_TABLE')
        self.table = self.dynamodb.Table(self.table_name)
    def append_message(
        self,
        project_id: str,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        message_id: str,
        reply_to: str = None,
        metadata: Dict[str, Any] = None
    ):
        """
        Appends a message to the chat history for the given session_id, project_id, and user_id.
        Uses 'role' (LangChain convention), 'message_id', and optional 'reply_to'.
        """
        timestamp = datetime.utcnow().isoformat() + 'Z'
        message = {
            'message_id': message_id,
            'timestamp': timestamp,
            'role': role,
            'content': content
        }
        if reply_to:
            message['reply_to'] = reply_to
        if metadata:
            message['metadata'] = metadata
        # Ensure the item exists with all three IDs, then append the message
        self.table.update_item(
            Key={'session_id': session_id},
            UpdateExpression='SET #msgs = list_append(if_not_exists(#msgs, :empty_list), :msg), project_id = :pid, user_id = :uid',
            ExpressionAttributeNames={'#msgs': 'messages'},
            ExpressionAttributeValues={
                ':msg': [message],
                ':empty_list': [],
                ':pid': project_id,
                ':uid': user_id
            }
        )
    def get_recent_history(self, session_id: str, limit: int = 10) -> Dict[str, Any]:
        """
        Retrieves a dict with the most recent 'limit' messages for the given session_id,
        along with project_id and user_id for reference. The returned dict always matches the ChatHistoryModel Pydantic schema.
        """
        resp = self.table.get_item(Key={'session_id': session_id})
        item = resp.get('Item', {})
        messages = item.get('messages', [])
        # Build the dict
        history_dict = {
            'project_id': item.get('project_id'),
            'user_id': item.get('user_id'),
            'session_id': session_id,
            'messages': messages[-limit:]
        }
        # Validate and serialize with Pydantic
        model = ChatHistoryModel.parse_obj(history_dict)
        return model.dict()


# -----------------------------
# Chat logging helper
# -----------------------------
def log_chat_history(event, payload, role, content, reply_to=None, metadata=None):
    chat_history = ChatHistory()
    project_id = (
        payload.get("project_id")
        or payload.get("project_name")
        or event.get("project_id")
        or event.get("project_name")
    )
    user_id = payload.get("user_id") or event.get("user_id")
    session_id = payload.get("session_id") or event.get("session_id")
    message_id = str(uuid.uuid4())

    chat_history.append_message(
        project_id=project_id,
        user_id=user_id,
        session_id=session_id,
        role=role,
        content=content,
        message_id=message_id,
        reply_to=reply_to,
        metadata=metadata,
    )
    return message_id