# ---------- web build ----------
FROM node:20-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ---------- runtime: Python API + JDK (Java analyzer) + Node (TS analyzer) ----------
FROM python:3.12-slim-bookworm
RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-17-jdk-headless git nodejs npm \
 && rm -rf /var/lib/apt/lists/* \
 && git config --global --add safe.directory '*'
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/analyzers/js/package.json backend/analyzers/js/package.json
RUN cd backend/analyzers/js && npm install --omit=dev
COPY backend/ backend/
COPY samples/ samples/
# A nested .git is not stored when this repo is pushed to GitHub, so rebuild the sample's demo history if it is missing.
RUN [ -d samples/shopverse/.git ] || python samples/build_sample_history.py
COPY --from=web /web/dist frontend/dist
ENV CODETWIN_DATA_DIR=/data PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8000
# Hosts such as Render assign the port through $PORT; 8000 locally.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --app-dir backend"]
