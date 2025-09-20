import io
import logging
from typing import List, Optional

# -------------------------------------------------------------------------
# Logger setup
# -------------------------------------------------------------------------
try:
    from .logger import CustomLogger  # relative import for package
    logger = CustomLogger(__name__)
except ImportError:
    # fallback if not in package context
    logger = logging.getLogger(__name__)


# -------------------------------------------------------------------------
# Chunking
# -------------------------------------------------------------------------
def split_into_chunks(text: str, chunk_size: int = 500) -> List[str]:
    """
    Split text into roughly chunk_size word chunks.

    Args:
        text: Input string.
        chunk_size: Approximate number of words per chunk.

    Returns:
        List of chunk strings.
    """
    if not isinstance(text, str) or not text.strip():
        logger.warning("Empty or invalid text provided for chunking")
        return []

    words = text.split()
    chunks = [" ".join(words[i:i + chunk_size]) for i in range(0, len(words), chunk_size)]
    logger.debug(f"Split {len(words)} words into {len(chunks)} chunks (chunk_size={chunk_size})")
    return chunks


# -------------------------------------------------------------------------
# File type detection
# -------------------------------------------------------------------------
def detect_file_type(filename: str, file_bytes: Optional[bytes] = None) -> str:
    """
    Return 'pdf', 'docx', 'txt', or 'unknown' based on extension/magic bytes.
    Consistent with metadata.py expectations.
    """
    if not filename:
        logger.warning("No filename provided for file type detection")
        return "unknown"

    name = filename.lower().strip()
    logger.debug(f"Detecting file type for: {name}")

    # Primary detection by extension
    if name.endswith(".pdf"):
        logger.debug(f"Detected PDF by extension: {name}")
        return "pdf"
    if name.endswith(".docx"):
        logger.debug(f"Detected DOCX by extension: {name}")
        return "docx"
    if name.endswith(".txt"):
        logger.debug(f"Detected TXT by extension: {name}")
        return "txt"

    # Secondary detection by magic bytes if available
    if file_bytes and len(file_bytes) >= 8:
        head = file_bytes[:8]
        if head.startswith(b"%PDF"):
            logger.debug(f"Detected PDF by magic bytes: {name}")
            return "pdf"
        if head.startswith(b"PK") and (".docx" in name or "word" in name.lower()):
            logger.debug(f"Detected DOCX by magic bytes: {name}")
            return "docx"

        # Check if content looks like text
        sample = file_bytes[:min(2048, len(file_bytes))]
        try:
            text_like = sum(1 for b in sample if 9 <= b <= 13 or 32 <= b <= 126)
            if text_like / len(sample) > 0.95:
                logger.debug(f"Detected TXT by content analysis: {name}")
                return "txt"
        except (ZeroDivisionError, TypeError):
            pass

    logger.debug(f"Could not detect file type for: {name}")
    return "unknown"


# -------------------------------------------------------------------------
# Text extraction
# -------------------------------------------------------------------------
def extract_text(file_bytes: bytes, filename: str) -> str:
    """
    Extract text based on detected file type; fallback to UTF-8 decode.
    Returns empty string on failure (consistent with data_ingestion.py expectations).
    """
    if not isinstance(file_bytes, bytes) or not file_bytes:
        logger.warning("Invalid or empty file_bytes provided")
        return ""

    if not filename:
        logger.warning("No filename provided for text extraction")
        filename = "unknown_file"

    ftype = detect_file_type(filename, file_bytes)
    logger.info(f"Extracting text from {filename} (detected type: {ftype})")

    try:
        if ftype == "pdf":
            try:
                from PyPDF2 import PdfReader  # type: ignore
                reader = PdfReader(io.BytesIO(file_bytes))
                pages = []
                for page_num, page in enumerate(reader.pages):
                    try:
                        page_text = page.extract_text() or ""
                        pages.append(page_text)
                    except Exception as e:
                        logger.warning(f"Failed to extract text from PDF page {page_num}: {e}")
                        pages.append("")

                text = "\n".join(pages).strip()
                if text:
                    logger.info(f"PDF extraction successful: {len(text)} chars from {len(pages)} pages")
                    return text
                else:
                    logger.warning("PDF extraction yielded no text")
            except ImportError:
                logger.error("PyPDF2 not available for PDF processing")
            except Exception as e:
                logger.warning(f"PDF parse failed, trying fallback decode: {e}")

        elif ftype == "docx":
            try:
                import docx  # type: ignore
                document = docx.Document(io.BytesIO(file_bytes))
                paragraphs = [para.text for para in document.paragraphs if para.text and para.text.strip()]
                text = "\n".join(paragraphs).strip()
                if text:
                    logger.info(f"DOCX extraction successful: {len(text)} chars from {len(paragraphs)} paragraphs")
                    return text
                else:
                    logger.warning("DOCX extraction yielded no text")
            except ImportError:
                logger.error("python-docx not available for DOCX processing")
            except Exception as e:
                logger.warning(f"DOCX parse failed, trying fallback decode: {e}")

        # Fallback: attempt UTF-8 decode
        try:
            decoded = file_bytes.decode("utf-8", errors="ignore").strip()
            if decoded:
                logger.info(f"Raw decode successful: {len(decoded)} chars (ftype={ftype})")
                return decoded
            else:
                logger.warning("Raw decode yielded no text")
        except Exception as e:
            logger.error(f"UTF-8 decode failed: {e}")

    except Exception as e:
        logger.error(f"extract_text unexpected error for {filename}: {e}")

    logger.warning(f"No text could be extracted from {filename}")
    return ""


__all__ = ["split_into_chunks", "detect_file_type", "extract_text"]
