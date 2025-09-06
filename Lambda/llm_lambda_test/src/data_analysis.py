from utils.utils import CustomLogger
from utils.model_loader import ModelLoader
from prompt.prompt_library import PROMPT_MODEL_REGISTRY

logger = CustomLogger(__name__)


class DocumentAnalyzer:
    """
    Analyzes documents using a Bedrock model.
    Provides structured metadata and summary extraction.
    """

    def __init__(self, temperature: float | None = None, max_output_tokens: int | None = None):
        self.llm = None
        self.prompt = None
        self.output_model = None
        self._initialize_llm(temperature, max_output_tokens)

    def _initialize_llm(self, temperature: float | None, max_output_tokens: int | None):
        """
        Initialize the Bedrock LLM and prompt configuration.
        """
        try:
            loader = ModelLoader()

            # Optional model overrides
            llm_kwargs = {}
            if temperature is not None:
                llm_kwargs["temperature"] = temperature
            if max_output_tokens is not None:
                llm_kwargs["max_output_tokens"] = max_output_tokens

            # Load Bedrock LLM
            self.llm = loader.load_llm(**llm_kwargs)

            # Load prompt + output model from registry
            prompt_config = PROMPT_MODEL_REGISTRY["document_analysis"]
            self.prompt = prompt_config["prompt"]
            self.output_model = prompt_config["output_model"]

            logger.info(
                "DocumentAnalyzer initialized",
                extra={
                    "temperature": getattr(self.llm, "temperature", None),
                    "max_output_tokens": getattr(self.llm, "max_output_tokens", None),
                },
            )

        except Exception as e:
            logger.error("Failed to initialize DocumentAnalyzer", exc_info=True)
            raise RuntimeError(f"DocumentAnalyzer initialization failed: {e}") from e

    def analyze_document(self, document_text: str) -> dict:
        """
        Analyze a document's text and extract structured metadata & summary using Bedrock.

        Args:
            document_text (str): Raw text extracted from the document.

        Returns:
            dict: Structured metadata and summary.
        """
        logger.info("Starting document analysis", extra={"text_length": len(document_text)})

        try:
            # Run LLM with prompt
            response = self.llm.invoke({
                "prompt": self.prompt,
                "document_text": document_text,
            })

            # Parse response into structured model
            metadata_obj = self.output_model(**response)

            logger.info(
                "Document analysis complete",
                extra={"response_length": len(str(response))},
            )
            return metadata_obj.dict()

        except Exception as e:
            logger.error("Document analysis failed", exc_info=True)
            raise RuntimeError(f"Document analysis failed: {e}") from e
