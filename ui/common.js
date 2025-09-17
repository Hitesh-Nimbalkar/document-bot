// Lambda endpoint (local dev with docker-lambda)
const API_URL = "http://localhost:9000/2015-03-31/functions/function/invocations";

// ============================
// Helpers
// ============================
function getSessionInfo() {
  // Stub: in real app, read from localStorage/sessionStorage or backend
  return {
    session_id: "sess_123",
    project_name: "demo_project",
    user_id: "user_1"
  };
}

function checkSessionOrRedirect() {
  const info = getSessionInfo();
  if (!info.project_name || !info.user_id) {
    alert("Missing session info");
    window.location.href = "login.html"; // optional
  }
  return info;
}

function renderJSON(elementId, obj) {
  const el = document.getElementById(elementId);
  if (!el) return;
  el.textContent = JSON.stringify(obj, null, 2);
}

// ============================
// Core Upload + Ingest
// ============================
async function uploadFilesAndIngest(files, statusDiv) {
  const { project_name, user_id, session_id } = getSessionInfo();
  const docLocs = [];

  for (const file of files) {
    try {
      statusDiv.innerText += `\n📡 Getting presigned URL for: ${file.name}...`;

      // Step 1: Get presigned URL
      const presignPayload = {
        route: "/get_presigned_url",
        payload: {
          project_name,
          filename: file.name,
          content_type: file.type || "application/octet-stream",
          file_size: file.size
        }
      };

      const presignRes = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(presignPayload)
      });
      const presignData = await presignRes.json();

      if (!presignRes.ok || !presignData.url) {
        throw new Error(`Presign failed: ${presignData.body || presignRes.status}`);
      }

      const { url, doc_loc } = presignData;

      // Step 2: Upload file to S3
      statusDiv.innerText += `\n⬆️ Uploading ${file.name}...`;
      const uploadRes = await fetch(url, {
        method: "PUT",
        headers: { "Content-Type": file.type || "application/octet-stream" },
        body: file
      });
      if (!uploadRes.ok) throw new Error(`Upload failed: ${file.name}`);

      statusDiv.innerText += `\n✅ Uploaded: ${file.name}`;
      docLocs.push(doc_loc);

    } catch (err) {
      statusDiv.innerText += `\n❌ Error with ${file.name}: ${err.message}`;
      return; // stop on first error
    }
  }

  // Step 3: Trigger ingestion
  try {
    statusDiv.innerText += `\n🚀 Triggering ingestion for ${docLocs.length} file(s)...`;

    const ingestPayload = {
      route: "/ingest_data",
      payload: {
        session_id,
        project_name,
        user_id,
        doc_locs: docLocs,
        ingest_source: "ui",
        source_path: "browser_upload",
        embedding_model: "bedrock_default"
      }
    };

    const ingestRes = await fetch(API_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(ingestPayload)
    });

    const ingestData = await ingestRes.json();
    if (!ingestRes.ok) throw new Error(JSON.stringify(ingestData));

    statusDiv.innerText += `\n🎉 Ingestion complete:\n${JSON.stringify(ingestData, null, 2)}`;
  } catch (err) {
    statusDiv.innerText += `\n❌ Ingestion error: ${err.message}`;
  }
}
