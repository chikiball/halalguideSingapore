/**
 * AI Agent routes — Step 10
 * Proxies requests to the Python agent-service and streams SSE back to the frontend.
 *
 * Usage in server.js:  require('./ai-routes')(app);
 *
 * Routes:
 *   POST /api/ai/search        → agent-service /search (SSE stream)
 *   POST /api/ai/place/details → agent-service /place/details (SSE stream)
 *   GET  /api/ai/health        → agent-service /health
 */

var http = require("http");
var https = require("https");

var AGENT_URL = process.env.AGENT_URL || "http://localhost:5000";

module.exports = function (app) {
  console.log("🤖 AI routes loaded | agent: " + AGENT_URL);

  // ─── Health check ────────────────────────────────────────────
  app.get("/api/ai/health", function (req, res) {
    var url = AGENT_URL + "/health";
    var getter = url.startsWith("https") ? https : http;

    getter
      .get(url, function (agentRes) {
        var data = "";
        agentRes.on("data", function (c) { data += c; });
        agentRes.on("end", function () {
          try {
            res.json(JSON.parse(data));
          } catch (e) {
            res.json({ status: "error", raw: data });
          }
        });
      })
      .on("error", function (err) {
        res.status(503).json({ status: "offline", error: err.message });
      });
  });

  // ─── AI Search (Phase 1: Discovery) ──────────────────────────
  app.post("/api/ai/search", function (req, res) {
    _proxySSE(req, res, "/search");
  });

  // ─── AI Place Details (Phase 2+3: Research + Article) ────────
  app.post("/api/ai/place/details", function (req, res) {
    _proxySSE(req, res, "/place/details");
  });

  // ─── SSE proxy helper ────────────────────────────────────────
  function _proxySSE(req, res, path) {
    var body = JSON.stringify(req.body);
    var parsed = new URL(AGENT_URL + path);

    var options = {
      hostname: parsed.hostname,
      port: parsed.port,
      path: parsed.pathname,
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Content-Length": Buffer.byteLength(body),
        Accept: "text/event-stream",
      },
    };

    // Set SSE headers on the client response
    res.setHeader("Content-Type", "text/event-stream");
    res.setHeader("Cache-Control", "no-cache");
    res.setHeader("Connection", "keep-alive");
    res.setHeader("X-Accel-Buffering", "no"); // disable nginx buffering
    res.flushHeaders();

    var requester = parsed.protocol === "https:" ? https : http;

    var agentReq = requester.request(options, function (agentRes) {
      // Pipe the SSE stream directly to the client
      agentRes.on("data", function (chunk) {
        res.write(chunk);
      });

      agentRes.on("end", function () {
        res.end();
      });

      agentRes.on("error", function (err) {
        res.write("event: error\ndata: " + JSON.stringify({ message: err.message }) + "\n\n");
        res.end();
      });
    });

    agentReq.on("error", function (err) {
      console.error("⚠️ Agent connection error:", err.message);
      res.write("event: error\ndata: " + JSON.stringify({ message: "Agent service unavailable: " + err.message }) + "\n\n");
      res.end();
    });

    // Send timeout after 3 minutes
    agentReq.setTimeout(180000, function () {
      res.write("event: error\ndata: " + JSON.stringify({ message: "Agent request timed out" }) + "\n\n");
      res.end();
      agentReq.destroy();
    });

    agentReq.write(body);
    agentReq.end();
  }
};
