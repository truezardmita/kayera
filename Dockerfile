# --- Stage 1: Build Next.js Frontend ---
FROM node:18-alpine AS frontend-builder
WORKDIR /app/frontend

# Copy frontend dependency files
COPY frontend/package*.json ./
RUN npm ci

# Copy frontend source files
COPY frontend/ ./

# Build the Next.js static app (generates 'out' folder)
RUN npm run build

# --- Stage 2: Serve API and Frontend via FastAPI ---
FROM python:3.10-slim
WORKDIR /app

# Install system dependencies (needed for compiling certain python packages if any)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application
COPY backend/ ./

# Copy compiled static frontend files into FastAPI's static folder
COPY --from=frontend-builder /app/frontend/out/ ./static/

# Expose port (Railway will set PORT env var)
EXPOSE 8080

# Command to run backend. It will read PORT env var or default to 8080
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
