# Full Argus deploy (incl. Predict tab + live rescore) — for Hugging Face Spaces (Docker SDK).
# HF free tier = 16GB RAM, so torch runs fine here (unlike Render free / 512MB).
FROM python:3.13-slim

WORKDIR /app
ENV PYTHONPATH=src \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Core API deps
COPY requirements.txt .
RUN pip install -r requirements.txt

# ML deps (CPU torch + torch_geometric) — the heavy part HF can handle
RUN pip install torch==2.12.1 --index-url https://download.pytorch.org/whl/cpu \
 && pip install torch_geometric==2.8.0

# App code + the committed cache/model (datasets are excluded via .dockerignore)
COPY . .

# HF Spaces routes to port 7860 by default
EXPOSE 7860
CMD ["sh", "-c", "uvicorn backend.api.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
