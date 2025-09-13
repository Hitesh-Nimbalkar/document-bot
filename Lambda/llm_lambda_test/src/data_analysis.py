from utils.utils import CustomLogger
from utils.model_loader import ModelLoader
from prompt.prompt_library import PROMPT_MODEL_REGISTRY
from pydantic import BaseModel, Field
from typing import List, Optional, Dict

logger = CustomLogger(__name__)


class DocumentAnalyzer:
    """Analyzes documents using a Bedrock model. Provides structured metadata and summary extraction."""

    def __init__(self, temperature: float | None = None, max_output_tokens: int | None = None):
        self.llm = None
        self.prompt = None
        self.output_model = None
        self._initialize_llm(temperature, max_output_tokens)

    def _initialize_llm(self, temperature: float | None, max_output_tokens: int | None):
        try:
            loader = ModelLoader()
            llm_kwargs = {}
            if temperature is not None:
                llm_kwargs["temperature"] = temperature
            if max_output_tokens is not None:
                llm_kwargs["max_output_tokens"] = max_output_tokens

            self.llm = loader.load_llm(**llm_kwargs)
            prompt_config = PROMPT_MODEL_REGISTRY["document_analysis"]
            self.prompt = prompt_config["prompt"]
            self.output_model = prompt_config["output_model"]

            logger.info("DocumentAnalyzer initialized",
                        extra={"temperature": getattr(self.llm, "temperature", None),
                               "max_output_tokens": getattr(self.llm, "max_output_tokens", None)})
        except Exception as e:
            logger.error("Failed to initialize DocumentAnalyzer", exc_info=True)
            raise RuntimeError(f"DocumentAnalyzer initialization failed: {e}") from e

    def analyze_document(self, document_text: str) -> dict:
        """Analyze document text and extract structured metadata & summary using Bedrock."""
        logger.info("Starting document analysis", extra={"text_length": len(document_text)})

        try:
            response = self.llm.invoke({"prompt": self.prompt, "document_text": document_text})
            metadata_obj = self.output_model(**response)
            logger.info("Document analysis complete", extra={"response_length": len(str(response))})
            return metadata_obj.dict()
        except Exception as e:
            logger.error("Document analysis failed", exc_info=True)
            raise RuntimeError(f"Document analysis failed: {e}") from e
