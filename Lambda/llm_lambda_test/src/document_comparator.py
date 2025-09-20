# # document_comparator.py
# from utils.utils import CustomLogger
# from utils.model_loader import ModelLoader
# from prompt.prompt_library import PROMPT_MODEL_REGISTRY
# from chat_history.chat_history import log_chat_history
# try:
#     from langchain.output_parsers import JsonOutputParser, OutputFixingParser
# except ImportError:
#     from langchain.output_parsers.json import JsonOutputParser
#     from langchain.output_parsers.fix import OutputFixingParser
# from pydantic import BaseModel
# from typing import Any, Dict
# logger = CustomLogger(__name__)

# class DocumentComparisonInput(BaseModel):
#     document_1: str
#     document_2: str
#     project_id: str | None = None
#     user_id: str | None = None
#     session_id: str | None = None

# class DocumentComparisonResult(BaseModel):
#     similarity_score: float
#     differences: str
#     summary: str
#     metadata: Dict[str, Any] | None = None

# class DocumentComparator:
#     """Compares two documents using a pre-defined LLM prompt and output model."""
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
#             logger.error(f"Error initializing DocumentComparator: {e}", exc_info=True)
#             raise RuntimeError(f"Error in DocumentComparator initialization: {e}")
#     def compare_documents(self, input_data: DocumentComparisonInput, payload: dict = None, event: dict = None) -> Dict[str, Any]:
#         """Compare two documents and return structured comparison results with minimal chat history logging."""
#         logger.info("Starting document comparison.")
        
#         try:
#             chain = self.prompt | self.llm | self.fixing_parser
#             response = chain.invoke({
#                 "format_instructions": self.parser.get_format_instructions(),
#                 "document_1": input_data.document_1,
#                 "document_2": input_data.document_2,
#             })
#             comparison_obj = self.output_model.parse_obj(response)
#             result = comparison_obj.dict()
            
#             logger.info(f"Document comparison complete. Response length: {len(str(response))}")
            
#             # Log successful comparison to chat history - ONLY critical success info
#             if payload or event:
#                 try:
#                     similarity = result.get('similarity_score', 'N/A')
#                     success_message = f"✅ Document comparison completed - Similarity: {similarity}"
                    
#                     log_chat_history(
#                         event=event or {}, 
#                         payload=payload or {}, 
#                         role="system", 
#                         content=success_message,
#                         metadata={"action": "comparison_success", "similarity_score": similarity}
#                     )
#                 except Exception as e:
#                     logger.warning(f"⚠️ Failed to log comparison success to chat history: {e}")
            
#             return result
            
#         except Exception as e:
#             logger.error(f"Error during document comparison: {e}", exc_info=True)
            
#             # Log comparison failure to chat history - ONLY critical errors
#             if payload or event:
#                 try:
#                     error_message = f"❌ Document comparison failed: {str(e)}"
#                     log_chat_history(
#                         event=event or {}, 
#                         payload=payload or {}, 
#                         role="system", 
#                         content=error_message,
#                         metadata={"action": "comparison_error", "error": str(e)}
#                     )
#                 except Exception as chat_error:
#                     logger.warning(f"⚠️ Failed to log comparison error to chat history: {chat_error}")
            
#             raise RuntimeError(f"Document comparison failed: {e}")
