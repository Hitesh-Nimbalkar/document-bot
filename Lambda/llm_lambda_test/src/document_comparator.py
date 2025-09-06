
# # document_comparator.py - Module for comparing two documents using LLMs
# # Usage:
# #   from document_comparator import DocumentComparator
# #   comparator = DocumentComparator()
# #   result = comparator.compare_documents(input_data)
# from prompt.prompt_library import PROMPT_MODEL_REGISTRY
# from models.models import DocumentComparisonInput, DocumentComparisonResult
# from utils.utils import CustomLogger
# from langchain_core.output_parsers import JsonOutputParser
# from langchain.output_parsers import OutputFixingParser
# from utils.model_loader import ModelLoader
# from ..utils.utils import CustomLogger
# from langchain_core.output_parsers import JsonOutputParser
# from langchain.output_parsers import OutputFixingParser
# from prompt.prompt_library import PROMPT_MODEL_REGISTRY
# from utils.model_loader import ModelLoader
# logger = CustomLogger(__name__)

# logger = CustomLogger(__name__)
# class DocumentComparator:
#     """
#     Compares two documents using a pre-defined LLM prompt and output model.
#     Use DocumentComparisonInput for input and DocumentComparisonResult for output.
#     """
#     def __init__(self):
#         try:
#             self.loader = ModelLoader()
#             self.llm = self.loader.load_llm()
#             prompt_config = PROMPT_MODEL_REGISTRY.get("document_comparator")
#             if not prompt_config:
#                 raise ValueError("No prompt/model registered for 'document_comparator'")
#             self.prompt = prompt_config["prompt"]
#             self.output_model = prompt_config["output_model"]
#             self.parser = JsonOutputParser(pydantic_object=self.output_model)
#             self.fixing_parser = OutputFixingParser.from_llm(parser=self.parser, llm=self.llm)
#             logger.info("DocumentComparator initialized successfully")
#         except Exception as e:
#             logger.error(f"Error initializing DocumentComparator: {e}")
#             raise Exception(f"Error in DocumentComparator initialization: {e}")
#     def compare_documents(self, input_data: DocumentComparisonInput) -> dict:
#         """
#         Compare two documents and return structured comparison results.
#         input_data: DocumentComparisonInput
#         returns: dict (DocumentComparisonResult as dict)
#         """
#         logger.info("Starting document comparison.")
#         try:
#             chain = self.prompt | self.llm | self.fixing_parser
#             response = chain.invoke({
#                 "format_instructions": self.parser.get_format_instructions(),
#                 "document_1": input_data.document_1,
#                 "document_2": input_data.document_2
#             })
#             comparison_obj = self.output_model(**response)
#             logger.info(f"Document comparison complete. Length: {len(response)}")
#             return comparison_obj.dict()
#         except Exception as e:
#             logger.error(f"Error during document comparison: {str(e)}")
#             raise Exception(f"Document comparison failed: {e}")
