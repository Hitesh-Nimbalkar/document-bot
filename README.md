# documrnt-bot
## 4. DynamoDB Metadata Table Structure
**Table Name:** `document_metadata`
**Partition Key:**
- `s3_key` (string) — e.g., `uploads/tmp/projectA/user1/filename.pdf` or `uploads/documents/projectA/user1/filename.pdf`
**Attributes:**
- `project_name` (string)
- `user_id` (string)
- `upload_timestamp` (string or number)
- `content_hash` (string)         # for deduplication
- `embedding_id` (string)         # reference to vector DB (optional)
- `original_filename` (string)    # for user-friendly display (optional)
- `status` (string)               # e.g., 'pending', 'approved', 'error' (optional)
bot-documents-bucket/
└── uploads/
   ├── projectA/
   │   ├── user1/
   │   │   ├── 20250830_abc123_report.pdf
   │   │   └── 20250830_def456_notes.pdf
   │   └── user2/
   │       └── 20250830_xyz789_invoice.pdf
   └── projectB/
      └── user3/
         └── 20250830_ghi321_summary.pdf
# Data Ingestion Flow & S3 Structure
## 1. Folder Structure & Workflow

```text
uploads/
      tmp/
            {project_name}/
                  {user_id}/
                        {filename}
      documents/
            {project_name}/
                  {user_id}/
                        {filename}
```
**Workflow:**
1. UI uploads to `uploads/tmp/{project_name}/{user_id}/{filename}`
2. Ingestion Lambda processes and approves the file
3. Lambda moves file to `uploads/documents/{project_name}/{user_id}/{filename}` if approved
4. Only approved/processed files are in the `documents` folder; temp holds pending/unapproved files
## 2. Example S3 Bucket Structure
```text
bot-documents-bucket/
└── uploads/
      ├── projectA/
      │   ├── user1/
      │   │   ├── 20250830_abc123_report.pdf
      │   │   └── 20250830_def456_notes.pdf
      │   └── user2/
      │       └── 20250830_xyz789_invoice.pdf
      └── projectB/
            └── user3/
                  └── 20250830_ghi321_summary.pdf
```
## 3. Data Ingestion Flow
1. **User uploads document from UI:**
      - The UI uploads the document directly to the S3 bucket using a pre-signed URL.
            - S3 key structure: `uploads/tmp/{project_name}/{user_id}/{timestamp or uuid}_{original_filename}` for uploads, and `uploads/documents/{project_name}/{user_id}/{timestamp or uuid}_{original_filename}` for approved files
2. **Notify backend for processing:**
      - After upload, the UI sends an API request (via API Gateway) to the backend Lambda (LLM Lambda), including:
            - S3 bucket name
            - S3 object key
            - Project name
            - User ID
3. **Backend Lambda processing:**
      - The Lambda receives the request and triggers the ingestion Lambda (synchronously or asynchronously) with the S3 object details for further processing.
## Notes
- S3 event notifications can also be used to trigger Lambda on upload, but for user-driven workflows, the above approach is preferred for more control and metadata.
- Organizing S3 objects by project and user makes management and retrieval easier.
