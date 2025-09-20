# import json
# import boto3

# from utils.logger import CustomLogger
# from utils.document_type_utils import extract_text_from_document

# # ======================================================
# # Logger / AWS Clients
# # ======================================================
# logger = CustomLogger(__name__)
# s3 = boto3.client("s3")


# # ======================================================
# # Handlers
# # ======================================================
# def handle_document_preview(event, payload):
#     """
#     Generate document preview with metadata.
#     Returns: text preview, metadata, thumbnail if available.
#     """
#     try:
#         file_path = payload.get("file_path")
#         project_name = payload.get("project_name")
#         preview_length = payload.get("preview_length", 500)

#         if not all([file_path, project_name]):
#             return {
#                 "statusCode": 400,
#                 "body": json.dumps({"error": "file_path and project_name are required"}),
#             }

#         # Extract document preview
#         preview_data = generate_document_preview(file_path, project_name, preview_length)

#         return {
#             "statusCode": 200,
#             "body": json.dumps(
#                 {
#                     "file_path": file_path,
#                     "preview": preview_data["text_preview"],
#                     "metadata": preview_data["metadata"],
#                     "thumbnail_url": preview_data.get("thumbnail_url"),
#                     "total_pages": preview_data.get("total_pages"),
#                     "file_size": preview_data.get("file_size"),
#                 }
#             ),
#         }

#     except Exception as e:
#         logger.error(f"Error generating document preview: {e}")
#         return {
#             "statusCode": 500,
#             "body": json.dumps({"error": str(e)}),
#         }


# def generate_document_preview(file_path, project_name, preview_length):
#     """Generate preview data for a document"""
#     try:
#         # Get document content
#         bucket_name = "your-documents-bucket"  # TODO: Replace with ENV var if needed
#         full_path = f"{project_name}/{file_path}"

#         # Download document from S3
#         response = s3.get_object(Bucket=bucket_name, Key=full_path)

#         # Extract metadata and preview
#         file_extension = file_path.split(".")[-1]
#         text_content = extract_text_from_document(response["Body"].read(), file_extension)

#         preview_text = (
#             text_content[:preview_length] + "..."
#             if len(text_content) > preview_length
#             else text_content
#         )

#         return {
#             "text_preview": preview_text,
#             "metadata": {
#                 "last_modified": response["LastModified"].isoformat(),
#                 "content_type": response.get("ContentType", "unknown"),
#                 "file_extension": file_extension,
#             },
#             "file_size": response["ContentLength"],
#             "total_pages": estimate_page_count(text_content),
#         }

#     except Exception as e:
#         logger.error(f"Error in preview generation: {e}")
#         raise


# def estimate_page_count(text_content):
#     """Estimate page count based on text length"""
#     words_per_page = 250
#     word_count = len(text_content.split())
#     return max(1, word_count // words_per_page)
