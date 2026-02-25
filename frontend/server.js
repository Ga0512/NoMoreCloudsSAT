/**
 * Servidor Express (Node.js) para o frontend.
 * - Serve arquivos estáticos de ./public
 * - Faz proxy de /api/* para o backend FastAPI (porta 8000)
 */
const express = require("express");
const { createProxyMiddleware } = require("http-proxy-middleware");
const path = require("path");

const app = express();
const PORT = process.env.PORT || 3000;
const API_TARGET = process.env.API_TARGET || "http://localhost:8000";

// ── Proxy para o backend FastAPI ────────────────────────
app.use(
  "/api",
  createProxyMiddleware({
    target: API_TARGET,
    changeOrigin: true,
    timeout: 300000,        // 5 min (uploads grandes)
    proxyTimeout: 300000,
    onError: (err, req, res) => {
      console.error(`[Proxy Error] ${req.method} ${req.url}:`, err.message);
      res.status(502).json({
        error: "Backend não disponível",
        detail: "Certifique-se de que o backend FastAPI está rodando na porta 8000.",
      });
    },
  })
);

// ── Arquivos estáticos ──────────────────────────────────
app.use(express.static(path.join(__dirname, "public")));

// ── Fallback para SPA ───────────────────────────────────
app.get("*", (req, res) => {
  res.sendFile(path.join(__dirname, "public", "index.html"));
});

// ── Start ───────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n╔══════════════════════════════════════════════╗`);
  console.log(`║   Satellite Image Compositor — Frontend      ║`);
  console.log(`╠══════════════════════════════════════════════╣`);
  console.log(`║   URL:     http://localhost:${PORT}             ║`);
  console.log(`║   API:     ${API_TARGET}              ║`);
  console.log(`╚══════════════════════════════════════════════╝\n`);
});
