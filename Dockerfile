# Base común para frontend y backend; ambos pueden ensamblar documentos Word.
FROM node:24-bookworm-slim AS node-deps
WORKDIR /node-deps
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

FROM python:3.11-slim-bookworm AS python-deps
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip wheel --no-cache-dir --wheel-dir /wheels -r requirements.txt

FROM python:3.11-slim-bookworm AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    NODE_PATH=/app/node_modules \
    HOME=/home/app
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libgomp1 libstdc++6 libatomic1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 app \
    && useradd --uid 1000 --gid app --create-home app
COPY --from=python-deps /wheels /wheels
COPY requirements.txt ./
RUN pip install --no-cache-dir --no-index --find-links=/wheels -r requirements.txt \
    && rm -rf /wheels
COPY --from=node-deps /usr/local/bin/node /usr/local/bin/node
COPY --from=node-deps /node-deps/node_modules /app/node_modules
# Lista explícita: no copiar secretos, respaldos ni índices dentro de la imagen.
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY proyecto_tecnico/ ./proyecto_tecnico/
COPY json/ ./json/
COPY scripts_graph/graph.json ./scripts_graph/graph.json
RUN mkdir -p outputs/proyectos scripts_index/chroma_db \
    && chown -R app:app outputs scripts_index /home/app
USER app

FROM runtime AS backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS frontend
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"
CMD ["streamlit", "run", "frontend/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true", "--browser.gatherUsageStats=false"]
