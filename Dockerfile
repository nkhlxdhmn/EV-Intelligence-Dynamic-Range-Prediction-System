# STEP 11M / STEP 12.1 - Inference API + React dashboard image.
# Builds a slim runtime image containing ONLY the frozen model artifacts,
# the inference package, and the FastAPI app. No training data is copied.
# The container is non-root.

# ---- stage 1: build the React dashboard --------------------------------
FROM node:20-alpine AS frontend-build

WORKDIR /fe
COPY dashboard/package*.json ./
RUN npm install --no-audit --no-fund
COPY dashboard/ ./
RUN npm run build

# ---- stage 2: python runtime -------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ---- install deps first (leverages layer cache) --------------------------
COPY requirements.inference.txt /app/requirements.inference.txt
RUN pip install --no-cache-dir -r /app/requirements.inference.txt

# ---- copy application code and frozen artifacts ---------------------------
COPY src/inference /app/src/inference
COPY src/telemetry /app/src/telemetry
COPY src/data/devrt_parser.py /app/src/data/devrt_parser.py
COPY scripts/comprehensive_feature_engineering.py /app/scripts/comprehensive_feature_engineering.py
COPY api /app/api
COPY models /app/models
COPY --from=frontend-build /fe/dist /app/dashboard/dist

# ---- non-root user --------------------------------------------------------
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"]

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]