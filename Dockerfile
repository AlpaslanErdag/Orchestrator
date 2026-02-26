# ──────────────────────────────────────────────────────────────────────────────
# AgentFlow Local — Dockerfile
# Builds a minimal production image for the FastAPI application.
# Ollama must run separately (on the host or in a companion container).
# ──────────────────────────────────────────────────────────────────────────────

FROM python:3.12-slim

# System deps (gcc for some compiled wheels; curl for health-checks)
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache friendly)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy source
COPY . .

# Runtime directories (will be volume-mounted in production)
RUN mkdir -p reports uploads

# Non-root user for security
RUN addgroup --system agentflow && adduser --system --ingroup agentflow agentflow
RUN chown -R agentflow:agentflow /app
USER agentflow

# ── Environment (override at runtime) ──
# OLLAMA_BASE_URL  — default: http://host.docker.internal:11434/v1
# OLLAMA_API_KEY   — default: ollama
# AGENTFLOW_PDF_FONT_PATH — path to a TTF font for UTF-8 PDF support

ENV OLLAMA_BASE_URL=http://host.docker.internal:11434/v1 \
    OLLAMA_API_KEY=ollama \
    PYTHONUNBUFFERED=1

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000", "--workers", "1"]
