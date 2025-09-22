const express = require("express");
const fetch = require("node-fetch");
const cors = require("cors");

const app = express();
const PORT = process.env.PORT || 4000;

const LAMBDA_HOST = process.env.LAMBDA_HOST || (process.env.DOCKER ? "lambda" : "localhost");
const LAMBDA_PORT = process.env.LAMBDA_PORT || (process.env.DOCKER ? "8080" : "9000");
const LAMBDA_URL = `http://${LAMBDA_HOST}:${LAMBDA_PORT}/2015-03-31/functions/function/invocations`;

console.log(`🚀 Proxy starting...`);
console.log(`🔗 Forwarding requests to: ${LAMBDA_URL}`);

// Enable CORS
app.use(cors({
  origin: "*",
  methods: ["GET", "POST", "OPTIONS"],
  allowedHeaders: ["Content-Type", "Authorization", "X-Session-ID", "X-User-ID"]
}));

// Increase JSON body limit to handle large file uploads (base64 encoded)
app.use(express.json({ limit: "50mb" }));

// Forward POST requests to Lambda (support "/" and "/rag_simple")
app.post(["/", "/rag_simple"], async (req, res) => {
  try {
    const response = await fetch(LAMBDA_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(req.body)
    });

    const text = await response.text();

    res.set("Access-Control-Allow-Origin", "*");
    res.set("Content-Type", "application/json");
    res.status(response.status).send(text);
  } catch (err) {
    console.error("❌ Proxy error:", err);
    res.status(500).json({ error: "Proxy failed", details: err.message });
  }
});

// Health check route
app.get("/health", (req, res) => {
  res.json({
    status: "proxy-ok",
    forwarding_to: LAMBDA_URL,
    port: PORT
  });
});

app.listen(PORT, () => {
  console.log(`✅ Proxy listening on http://localhost:${PORT}`);
});
