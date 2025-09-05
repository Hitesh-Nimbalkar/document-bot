
from utils.utils import CustomLogger
from langchain_core.output_parsers import JsonOutputParser
from langchain.output_parsers import OutputFixingParser
from prompt.prompt_library import PROMPT_MODEL_REGISTRY
from utils.model_loader import ModelLoader
logger = CustomLogger(__name__)

class DocumentAnalyzer:
    """
    Analyzes documents using a pre-trained model.
    Automatically logs all actions and supports session-based organization.
    """
    def __init__(self):
        try:
            self.loader = ModelLoader()
            self.llm = self.loader.load_llm()
            # Get prompt and output model from the registry
            prompt_config = PROMPT_MODEL_REGISTRY["document_analysis"]
            self.prompt = prompt_config["prompt"]
            self.output_model = prompt_config["output_model"]
            self.parser = JsonOutputParser(pydantic_object=self.output_model)
            self.fixing_parser = OutputFixingParser.from_llm(parser=self.parser, llm=self.llm)
            logger.info("DocumentAnalyzer initialized successfully")
        except Exception as e:
            logger.error(f"Error initializing DocumentAnalyzer: {e}")
            raise Exception(f"Error in DocumentAnalyzer initialization: {e}")
    def analyze_document(self, document_text: str) -> dict:
        """
        Analyze a document's text and extract structured metadata & summary.
        """
        logger.info("Starting document analysis.")
        try:
            chain = self.prompt | self.llm | self.fixing_parser
            response = chain.invoke({
                "format_instructions": self.parser.get_format_instructions(),
                "document_text": document_text
            })
            metadata_obj = self.output_model(**response)
            logger.info(f"Document analysis complete. Length: {len(response)}")
            return metadata_obj.dict()
        except Exception as e:
            logger.error(f"Error during document analysis: {str(e)}")
            raise Exception(f"Metadata extraction failed: {e}")
