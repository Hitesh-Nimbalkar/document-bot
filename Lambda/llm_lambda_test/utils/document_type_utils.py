
import os
import mimetypes
import textract
from typing import Optional

def detect_document_type(s3_bucket: str, s3_key: str, s3_client=None) -> Optional[str]:
    """
    Detects the document type based on file extension or content-type from S3.
    Returns: 'pdf', 'docx', 'txt', etc. or None if unknown.
    """
    if not s3_client:
        import boto3
        s3_client = boto3.client('s3')
    # Try to get content-type from S3 metadata
    try:
        head = s3_client.head_object(Bucket=s3_bucket, Key=s3_key)
        content_type = head.get('ContentType')
        if content_type:
            if 'pdf' in content_type:
                return 'pdf'
            elif 'msword' in content_type or 'docx' in content_type:
                return 'docx'
            elif 'text' in content_type:
                return 'txt'
    except Exception:
        pass
    # Fallback: use file extension
    ext = os.path.splitext(s3_key)[-1].lower()
    if ext == '.pdf': 
        return 'pdf'
    elif ext in ('.doc', '.docx'):
        return 'docx'
    elif ext in ('.txt', '.text'):
        return 'txt'
    return None
def extract_text_from_document(s3_bucket: str, s3_key: str, doc_type: str, s3_client=None) -> str:
    """
    Extracts text from a document in S3 based on its type.
    """
    if not s3_client:
        import boto3
        s3_client = boto3.client('s3')
    obj = s3_client.get_object(Bucket=s3_bucket, Key=s3_key)
    file_bytes = obj['Body'].read()
    if doc_type == 'pdf':
        import io
        from PyPDF2 import PdfReader
        reader = PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or '' for page in reader.pages)
    elif doc_type == 'docx':
        import io
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join([p.text for p in doc.paragraphs])
    elif doc_type == 'txt':
        return file_bytes.decode('utf-8')
    else:
        # Fallback: try textract
        return textract.process(s3_key, input_encoding='utf-8').decode('utf-8')
