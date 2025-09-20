
import boto3
import os
import uuid
import json
from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, validator
from botocore.exceptions import ClientError
from utils.logger import CustomLogger
from utils.dynamodb import EnhancedDynamoDBClient
logger = CustomLogger(__name__)
# ---------------------------
# Chat message (LangChain compatible)
# ---------------------------
class ChatMessage(BaseModel):
    message_id: str = Field(..., description="Unique identifier for the message")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    role: str = Field(..., description="Message role: user, assistant, or system")
    content: str = Field(..., min_length=1, description="Message content")
    reply_to: Optional[str] = Field(None, description="ID of message this replies to")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")
    @validator('role')
    def validate_role(cls, v):
        allowed_roles = ['user', 'assistant', 'system']
        if v not in allowed_roles:
            raise ValueError(f"Role must be one of {allowed_roles}")
        return v
    @validator('timestamp')
    def validate_timestamp(cls, v):
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
            return v
        except ValueError:
            raise ValueError("Timestamp must be valid ISO 8601 format")
    model_config = {
        "populate_by_name": True,
    }
# ---------------------------
# Chat history for a session
# ---------------------------
class ChatHistoryModel(BaseModel):
    project_id: Optional[str] = Field(None, description="Project identifier")
    user_id: Optional[str] = Field(None, description="User identifier")
    session_id: str = Field(..., description="Session identifier")
    messages: List[ChatMessage] = Field(default_factory=list, description="List of chat messages")
    created_at: Optional[str] = Field(None, description="Session creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    @validator('messages')
    def validate_messages(cls, v):
        if len(v) > 1000:  # Prevent extremely large histories
            logger.warning(f"Chat history exceeds recommended size: {len(v)} messages")
        return v

class ChatHistory(EnhancedDynamoDBClient):
    """
    Enhanced chat history manager with improved error handling, validation, and performance.
    Manages chat history for sessions in DynamoDB with comprehensive logging and monitoring.
    Inherits from EnhancedDynamoDBClient for consistent DynamoDB operations.
    """
    
    def __init__(self, table_name: str = None, region_name: str = None):
        try:
            # Initialize the parent EnhancedDynamoDBClient
            super().__init__(region_name)
            
            self.table_name = table_name or os.environ.get('CHAT_HISTORY_TABLE')
            
            if not self.table_name:
                raise ValueError("CHAT_HISTORY_TABLE environment variable must be set")
                
            # Verify the table exists using the parent class method
            self.table = self.get_table(self.table_name)
            logger.info(f"✅ ChatHistory initialized with table: {self.table_name}")
            
        except Exception as e:
            logger.error(f"💥 Failed to initialize ChatHistory: {e}")
            raise
    def _generate_message_id(self) -> str:
        """Generate a unique message ID with timestamp prefix for better sorting"""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        return f"{timestamp}_{uuid.uuid4().hex[:8]}"
    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO 8601 format"""
        return datetime.utcnow().isoformat() + 'Z'
    def append_message(
        self,
        project_id: str,
        user_id: str,
        session_id: str,
        role: str,
        content: str,
        message_id: str = None,
        reply_to: str = None,
        metadata: Dict[str, Any] = None,
        model_meta: Dict[str, Any] = None,  # kept: just stored with the message
    ) -> str:
        """
        Enhanced message appending with validation, error handling, and automatic ID generation.
        Uses the enhanced DynamoDB client for consistent error handling and logging.
        
        Returns:
            str: The message_id of the appended message
        """
        try:
            # Validate inputs
            if not all([project_id, user_id, session_id, role, content]):
                raise ValueError("project_id, user_id, session_id, role, and content are required")
            
            # Generate message ID if not provided
            if not message_id:
                message_id = self._generate_message_id()
            timestamp = self._get_current_timestamp()
            # Merge user metadata + model_meta (simple, no aggregates)
            merged_metadata = (metadata or {}).copy()
            if model_meta:
                merged_metadata["model_meta"] = model_meta  # single key storage
            message_data = {
                'message_id': message_id,
                'timestamp': timestamp,
                'role': role,
                'content': content[:4000],
                'reply_to': reply_to,
                'metadata': merged_metadata
            }
            chat_message = ChatMessage(**message_data)
            message = chat_message.dict(exclude_none=True)
            update_expression = (
                'SET #msgs = list_append(if_not_exists(#msgs, :empty_list), :msg), '
                'project_id = :pid, user_id = :uid, updated_at = :updated, '
                'created_at = if_not_exists(created_at, :created)'
            )
            expr_attr_names = {'#msgs': 'messages'}
            expr_attr_values = {
                ':msg': [message],
                ':empty_list': [],
                ':pid': project_id,
                ':uid': user_id,
                ':updated': timestamp,
                ':created': timestamp
            }
            success = self.update_item(
                table_name=self.table_name,
                key={'session_id': session_id},
                update_expression=update_expression,
                expression_attribute_names=expr_attr_names,
                expression_attribute_values=expr_attr_values
            )
            if success:
                logger.info(f"✅ Message appended: {message_id} to session {session_id}")
                return message_id
            raise Exception("Failed to update chat history in DynamoDB")
        except Exception as e:
            logger.error(f"💥 Error appending message: {e}")
            raise
    def get_recent_history(self, session_id: str, limit: int = 10) -> Dict[str, Any]:
        """
        Retrieves a dict with the most recent 'limit' messages for the given session_id,
        along with project_id and user_id for reference. The returned dict always matches the ChatHistoryModel Pydantic schema.
        Uses the enhanced DynamoDB client for consistent error handling and logging.
        """
        try:
            item = self.get_item(
                table_name=self.table_name,
                key={'session_id': session_id}
            )
            if not item:
                logger.info(f"📭 No chat history found for session: {session_id}")
                # Return empty history structure
                history_dict = {
                    'project_id': None,
                    'user_id': None,
                    'session_id': session_id,
                    'messages': []
                }
            else:
                messages = item.get('messages', [])
                history_dict = {
                    'project_id': item.get('project_id'),
                    'user_id': item.get('user_id'),
                    'session_id': session_id,
                    'messages': messages[-limit:] if messages else [],
                    'created_at': item.get('created_at'),
                    'updated_at': item.get('updated_at')
                }
            model = ChatHistoryModel.parse_obj(history_dict)
            logger.info(f"✅ Retrieved {len(model.messages)} messages for session: {session_id}")
            return model.dict()
        except Exception as e:
            logger.error(f"💥 Error retrieving chat history for session {session_id}: {e}")
            # Return empty structure on error
            return {
                'project_id': None,
                'user_id': None,
                'session_id': session_id,
                'messages': []
            }
    def delete_session(self, session_id: str) -> bool:
        """
        Delete an entire chat session using the enhanced DynamoDB client.
        
        Args:
            session_id: The session to delete
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            success = self.delete_item(
                table_name=self.table_name,
                key={'session_id': session_id}
            )
            
            if success:
                logger.info(f"✅ Chat session deleted: {session_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"💥 Error deleting chat session {session_id}: {e}")
            return False
    def clear_messages(self, session_id: str) -> bool:
        """
        Clear all messages from a chat session while preserving session metadata.
        
        Args:
            session_id: The session to clear messages from
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            current_time = self._get_current_timestamp()
            success = self.update_item(
                table_name=self.table_name,
                key={'session_id': session_id},
                update_expression='SET #msgs = :empty_list, updated_at = :updated',
                expression_attribute_names={'#msgs': 'messages'},
                expression_attribute_values={
                    ':empty_list': [],
                    ':updated': current_time
                }
            )
            
            if success:
                logger.info(f"✅ Messages cleared for session: {session_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"💥 Error clearing messages for session {session_id}: {e}")
            return False
    def get_sessions_for_user(self, user_id: str, project_id: str = None) -> List[Dict[str, Any]]:
        """
        Get all chat sessions for a specific user, optionally filtered by project.
        
        Args:
            user_id: The user to get sessions for
            project_id: Optional project filter
            
        Returns:
            List of session summaries
        """
        try:
            # Use scan to find sessions by user_id (assuming no GSI for user_id)
            filter_expression = "user_id = :uid"
            expression_values = {":uid": user_id}
            
            if project_id:
                filter_expression += " AND project_id = :pid"
                expression_values[":pid"] = project_id
            
            sessions = self.scan_items(
                table_name=self.table_name,
                filter_expression=filter_expression,
                expression_attribute_values=expression_values
            )
            
            # Return session summaries (excluding messages for performance)
            session_summaries = []
            for session in sessions:
                summary = {
                    'session_id': session.get('session_id'),
                    'project_id': session.get('project_id'),
                    'user_id': session.get('user_id'),
                    'created_at': session.get('created_at'),
                    'updated_at': session.get('updated_at'),
                    'message_count': len(session.get('messages', []))
                }
                session_summaries.append(summary)
            
            logger.info(f"✅ Found {len(session_summaries)} sessions for user: {user_id}")
            return session_summaries
            
        except Exception as e:
            logger.error(f"💥 Error getting sessions for user {user_id}: {e}")
            return []
    def update_session_metadata(self, session_id: str, metadata: Dict[str, Any]) -> bool:
        """
        Update session metadata without affecting messages.
        
        Args:
            session_id: The session to update
            metadata: Dictionary of metadata fields to update
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Build update expression dynamically
            update_parts = []
            expression_values = {}
            expression_names = {}
            
            for key, value in metadata.items():
                if key not in ['session_id', 'messages']:  # Protect key fields
                    update_parts.append(f"#{key} = :{key}")
                    expression_values[f":{key}"] = value
                    expression_names[f"#{key}"] = key
            
            if not update_parts:
                logger.warning(f"⚠️ No valid metadata to update for session: {session_id}")
                return False
            
            # Add updated timestamp
            update_parts.append("updated_at = :updated")
            expression_values[":updated"] = self._get_current_timestamp()
            
            update_expression = "SET " + ", ".join(update_parts)
            
            success = self.update_item(
                table_name=self.table_name,
                key={'session_id': session_id},
                update_expression=update_expression,
                expression_attribute_values=expression_values,
                expression_attribute_names=expression_names if expression_names else None
            )
            
            if success:
                logger.info(f"✅ Session metadata updated: {session_id}")
            
            return success
            
        except Exception as e:
            logger.error(f"💥 Error updating session metadata for {session_id}: {e}")
            return False

# -----------------------------
# Chat logging helper
# -----------------------------
def log_chat_history(event, payload, role, content, reply_to=None, metadata=None):
    """
    Enhanced chat logging helper that uses the improved ChatHistory class
    with better error handling and validation.
    """
    try:
        chat_history = ChatHistory()
        project_id = (
            payload.get("project_id")
            or payload.get("project_name")
            or event.get("project_id")
            or event.get("project_name")
        )
        user_id = payload.get("user_id") or event.get("user_id")
        session_id = payload.get("session_id") or event.get("session_id")
        
        # Validate required fields
        if not all([project_id, user_id, session_id]):
            logger.error("💥 Missing required fields for chat logging")
            return None
            
        message_id = str(uuid.uuid4())
        return chat_history.append_message(
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
            role=role,
            content=content,
            message_id=message_id,
            reply_to=reply_to,
            metadata=metadata,
        )
        
    except Exception as e:
        logger.error(f"💥 Error in log_chat_history: {e}")
        return None
# Helper to simplify logging a model-generated assistant message
def log_model_chat_message(event, payload, content, model_meta, reply_to=None):
    """
    Log assistant message with raw model_meta attached per message only.
    """
    try:
        chat_history = ChatHistory()
        project_id = (
            payload.get("project_id")
            or payload.get("project_name")
            or event.get("project_id")
            or event.get("project_name")
        )
        user_id = payload.get("user_id") or event.get("user_id")
        session_id = payload.get("session_id") or event.get("session_id")
        if not all([project_id, user_id, session_id]):
            logger.error("💥 Missing required fields for model chat logging")
            return None
        return chat_history.append_message(
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
            role="assistant",
            content=content,
            reply_to=reply_to,
            model_meta=model_meta
        )
    except Exception as e:
        logger.error(f"💥 Error in log_model_chat_message: {e}")
        return None
