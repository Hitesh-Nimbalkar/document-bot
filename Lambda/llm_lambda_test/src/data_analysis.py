# document_analyzer.py
"""
DocumentAnalyzer
----------------
Analyzes documents using a model via ModelLoader.

Features:
- Safe JSON parsing from model output
- Configurable temperature and output tokens
- Prompt and model schema loaded from PROMPT_MODEL_REGISTRY
- Operation cost tracking
- Optional chat history logging
"""

# ======================================================
# Imports
# ======================================================
import json
from typing import Optional, Dict

from utils.utils import CustomLogger
from utils.model_loader import ModelLoader, BedrockProvider
from prompt.prompt_library import PROMPT_MODEL_REGISTRY
from chat_history.chat_history import log_chat_history

# ======================================================
# Logger
# ======================================================
logger = CustomLogger(__name__)


# ======================================================
# Helpers
# ======================================================
def safe_parse_json_output(raw: str | dict) -> dict:
    """Try parsing model output into JSON with fallbacks."""
    if isinstance(raw, dict):
        return raw

    if not isinstance(raw, str):
        raise ValueError("Model output must be string or dict")

    try:
        return json.loads(raw)
    except Exception:
        start, end = raw.find("{"), raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(raw[start:end + 1])
            except Exception:
                pass

    raise ValueError("Model output not valid JSON")


# ======================================================
# Document Analyzer
# ======================================================
class DocumentAnalyzer:
    """Analyzes documents using a model.
    Simplified ModelLoader integration (generate -> (text, meta)).
    """

    # --------------------------------------------------
    # Initialization
    # --------------------------------------------------
    def __init__(
        self,
        loader: Optional[ModelLoader] = None,
        temperature: float = 0.7,
        max_output_tokens: int = 512,
        prompt_config: Optional[Dict] = None,
        enable_chat_logging: bool = True,
    ):
        # Initialize loader (auto-selects first registered provider)
        self.loader = loader or ModelLoader().register("bedrock", BedrockProvider())
        self.temperature = temperature
        self.max_output_tokens = max_output_tokens

        cfg = prompt_config or PROMPT_MODEL_REGISTRY["document_analysis"]
        self.prompt = cfg["prompt"]
        self.output_model = cfg["output_model"]

        self.enable_chat_logging = enable_chat_logging
        self.last_operation_cost: float = 0.0  # Track last analysis cost

        logger.info(
            "DocumentAnalyzer initialized",
            extra={
                "temperature": self.temperature,
                "max_output_tokens": self.max_output_tokens,
            },
        )

    # --------------------------------------------------
    # Analyze Document
    # --------------------------------------------------
    def analyze_document(
        self,
        document_text: str,
        payload: dict = None,
        event: dict = None,
        filename: str = None,
    ) -> dict:
        """Run document analysis pipeline."""
        logger.info(
            "Starting document analysis",
            extra={"text_length": len(document_text), "filename": filename},
        )
        try:
            full_prompt = f"{self.prompt}\n\nDocument:\n{document_text}"

            # Model call (returns (text, meta))
            raw_text, meta = self.loader.generate(
                full_prompt,
                max_tokens=self.max_output_tokens,
                temperature=self.temperature,
            )

            # Parse output
            response_dict = safe_parse_json_output(raw_text)

            # Validate using Pydantic model from registry
            metadata_obj = self.output_model(**response_dict)
            result = metadata_obj.dict()

            # Cost (per-call only)
            operation_cost = float(meta.get("cost", 0.0)) if isinstance(meta, dict) else 0.0
            self.last_operation_cost = operation_cost

            logger.info(
                "Document analysis complete",
                extra={"filename": filename, "operation_cost_usd": operation_cost},
            )

            if operation_cost:
                result["_cost_info"] = {"operation_cost_usd": round(operation_cost, 6)}

            # Chat history logging
            if self.enable_chat_logging and (payload or event):
                msg = "✅ Document analysis completed"
                if filename:
                    msg += f" ({filename})"
                if operation_cost:
                    msg += f" (${operation_cost:.6f})"
                if result.get("title"):
                    msg += f" - Title: {result['title']}"

                try:
                    log_chat_history(
                        event=event or {},
                        payload=payload or {},
                        role="system",
                        content=msg,
                        metadata={
                            "action": "analysis_success",
                            "filename": filename,
                            "cost_usd": operation_cost,
                        },
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to log success to chat history: {e}")

            return result

        except Exception as e:
            logger.error("Document analysis failed", exc_info=True)

            # Log failure to chat history
            if self.enable_chat_logging and (payload or event):
                file_context = f" ({filename})" if filename else ""
                error_message = f"❌ Document analysis failed{file_context}: {str(e)}"

                try:
                    log_chat_history(
                        event=event or {},
                        payload=payload or {},
                        role="system",
                        content=error_message,
                        metadata={
                            "action": "analysis_error",
                            "filename": filename,
                            "error": str(e),
                        },
                    )
                except Exception as chat_error:
                    logger.warning(f"⚠️ Failed to log error to chat history: {chat_error}")

            raise RuntimeError(f"Document analysis failed: {e}") from e

    # --------------------------------------------------
    # Cost Tracking
    # --------------------------------------------------
    def get_cost_summary(self) -> Dict:
        """Return last operation cost (aggregate tracking not supported)."""
        return {"last_operation_cost_usd": round(self.last_operation_cost, 6)}
