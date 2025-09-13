// common.js
const API_URL = "https://your-api-gateway-id.execute-api.ap-south-1.amazonaws.com/prod";

// Fetch session info from localStorage
function getSessionInfo() {
  return {
    project_name: localStorage.getItem("project_name"),
    user_id: localStorage.getItem("user_id"),
    session_id: localStorage.getItem("session_id")
  };
}

// Redirect to login if no session
function checkSessionOrRedirect() {
  const { project_name, user_id, session_id } = getSessionInfo();
  if (!project_name || !user_id || !session_id) {
    alert("Please login first.");
    window.location.href = "login.html";
  }
}

// Utility: pretty print JSON
function renderJSON(elementId, data) {
  document.getElementById(elementId).innerHTML =
    "<pre>" + JSON.stringify(data, null, 2) + "</pre>";
}
