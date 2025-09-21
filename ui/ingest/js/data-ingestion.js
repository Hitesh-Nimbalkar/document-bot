



/**
 * Data Ingestion Manager
 * Handles sending uploaded documents to ingestion pipeline
 */
class DataIngestionManager {
    constructor(sessionManager, modelManager, uiManager, uploadManager) {
        this.sessionManager = sessionManager;
        this.modelManager = modelManager;
        this.uiManager = uiManager;
        this.uploadManager = uploadManager; // Add reference to uploadManager
    }
    async processDocuments() {
        const projectName = document.getElementById("projectNameInput")?.value.trim();
        if (!projectName) {
            this.showError("Please enter a project name.");
            return;
        }
        
        if (!this.sessionManager?.isValidSession()) {
            this.showError("No valid session found. Please login again.");
            return;
        }
        // Get uploaded files data from the upload step
        console.log("🔍 Debug - uploadManager exists:", !!this.uploadManager);
        
        // DIRECT localStorage check to bypass potential uploadManager issues
        const directFromStorage = localStorage.getItem('document_bot_upload_responses');
        console.log("🔍 Debug - Direct localStorage check:", directFromStorage);
        
        const lambdaResponses = this.uploadManager?.getUploadedFilesData() || [];
        console.log("🔍 Debug - lambdaResponses length:", lambdaResponses.length);
        console.log("🔍 Debug - lambdaResponses:", lambdaResponses);
        
        // If uploadManager fails, try direct localStorage as backup
        if (!lambdaResponses.length && directFromStorage) {
            console.log("🔍 Using direct localStorage as backup");
            const backupResponses = JSON.parse(directFromStorage);
            console.log("🔍 Backup responses:", backupResponses);
            if (backupResponses.length > 0) {
                console.log("✅ Found data in localStorage directly!");
                
                // Use the backup data - keep it simple
                const payload = {
                    lambda_upload_responses: backupResponses
                };
                console.log("🔄 Processing with direct localStorage data:", payload);
                // Continue with processing...
                const statusDiv = document.getElementById("processingStatus");
                if (statusDiv) {
                    statusDiv.style.display = "block";
                    statusDiv.innerHTML = `<div class="text-info">⚙️ Processing documents from localStorage...</div>`;
                }
                
                try {
                    const response = await makeApiRequest(window.API_ENDPOINTS.INGEST_DATA, payload);
                    const body = typeof response.body === "string" ? JSON.parse(response.body) : response.body || response;
                    
                    // Enhanced debugging information
                    console.log("📊 Full response received:", response);
                    console.log("📊 Response body:", body);
                    console.log("📊 Response status code:", response.statusCode);
                    console.log("📊 Body has summary:", !!body.summary);
                    console.log("📊 Body has results:", !!body.results);
                    
                    // Check for successful response based on statusCode and presence of summary
                    if (response.statusCode === 200 && (body.summary || body.results)) {
                        const summaryText = body.summary ? 
                            (typeof body.summary === 'object' ? 
                                `Total: ${body.summary.total}, Success: ${body.summary.succeeded}, Errors: ${body.summary.errors}` : 
                                body.summary) : 
                            "Completed";
                        
                        if (statusDiv) {
                            statusDiv.innerHTML = `<div class="text-success">✅ Documents processed successfully! ${summaryText}</div>`;
                        }
                        console.log("✅ Ingestion complete:", body);
                    } else {
                        // Enhanced error information
                        const errorDetails = {
                            statusCode: response.statusCode,
                            hasBody: !!body,
                            bodyKeys: body ? Object.keys(body) : [],
                            error: body?.error,
                            fullResponse: response
                        };
                        console.error("❌ Response validation failed:", errorDetails);
                        
                        const errorMessage = body?.error || 
                            `Response validation failed (status: ${response.statusCode}, has summary: ${!!body.summary}, has results: ${!!body.results})`;
                        throw new Error(errorMessage);
                    }
                } catch (error) {
                    console.error("❌ Ingestion failed:", error);
                    if (statusDiv) {
                        statusDiv.innerHTML = `<div class="text-danger">❌ Processing failed: ${error.message}</div>`;
                    }
                }
                return; // Exit early since we processed with backup
            }
        }
        
        if (!lambdaResponses.length) {
            this.showError("No files have been uploaded yet. Please upload files first.");
            return;
        }
        console.log("🔄 Processing with Lambda responses:", lambdaResponses);
        // Pass the EXACT Lambda responses - keep it simple, let Lambda handle the logic
        const payload = {
            lambda_upload_responses: lambdaResponses
        };
        const statusDiv = document.getElementById("processingStatus");
        if (statusDiv) {
            statusDiv.style.display = "block";
            statusDiv.innerHTML = `<div class="text-info">⚙️ Processing documents...</div>`;
        }
        try {
            const response = await makeApiRequest(window.API_ENDPOINTS.INGEST_DATA, payload);
            const body =
                typeof response.body === "string"
                    ? JSON.parse(response.body)
                    : response.body || response;
            // Enhanced debugging information
            console.log("📊 Full response received:", response);
            console.log("📊 Response body:", body);
            console.log("📊 Response status code:", response.statusCode);
            console.log("📊 Body has summary:", !!body.summary);
            console.log("📊 Body has results:", !!body.results);
            // Check for successful response based on statusCode and presence of summary
            if (response.statusCode === 200 && (body.summary || body.results)) {
                const summaryText = body.summary ? 
                    (typeof body.summary === 'object' ? 
                        `Total: ${body.summary.total}, Success: ${body.summary.succeeded}, Errors: ${body.summary.errors}` : 
                        body.summary) : 
                    "Completed";
                
                if (statusDiv) {
                    statusDiv.innerHTML = `<div class="text-success">
                        ✅ Documents processed successfully! ${summaryText}
                    </div>`;
                }
                console.log("✅ Ingestion complete:", body);
                
                // Clear the uploaded files data since processing is complete
                this.uploadManager?.clearUploadedFilesData();
                
            } else {
                // Enhanced error information
                const errorDetails = {
                    statusCode: response.statusCode,
                    hasBody: !!body,
                    bodyKeys: body ? Object.keys(body) : [],
                    error: body?.error,
                    fullResponse: response
                };
                console.error("❌ Response validation failed:", errorDetails);
                
                const errorMessage = body?.error || 
                    `Response validation failed (status: ${response.statusCode}, has summary: ${!!body.summary}, has results: ${!!body.results})`;
                throw new Error(errorMessage);
            }
        } catch (error) {
            console.error("❌ Ingestion failed:", error);
            if (statusDiv) {
                statusDiv.innerHTML = `<div class="text-danger">
                    ❌ Processing failed: ${error.message}
                </div>`;
            }
        }
    }
    // Add error display method
    showError(message) {
        console.error("❌", message);
        const statusDiv = document.getElementById("processingStatus");
        if (statusDiv) {
            statusDiv.style.display = "block";
            statusDiv.innerHTML = `<div class="alert alert-danger">❌ ${message}</div>`;
        } else {
            alert(`Error: ${message}`);
        }
    }
}
// Export globally
window.DataIngestionManager = DataIngestionManager;


