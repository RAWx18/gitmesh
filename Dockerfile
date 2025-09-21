# Multi-stage Dockerfile for Cosmos Web Chat Integration Production Deployment

# ========================
# Stage 1: Base Python Environment
# ========================
FROM python:3.11-slim as base

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser appuser

# ========================
# Stage 2: Dependencies
# ========================
FROM base as dependencies

# Set working directory
WORKDIR /app

# Copy requirements
COPY backend/requirements.txt .
COPY backend/integrations/cosmos/v1/requirements.txt ./cosmos_requirements.txt

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r cosmos_requirements.txt

# ========================
# Stage 3: Application
# ========================
FROM dependencies as application

# Copy application code
COPY backend/ ./backend/
COPY ui/ ./ui/

# Create necessary directories
RUN mkdir -p /app/logs /app/data /app/cache && \
    chown -R appuser:appuser /app

# Copy production configuration
COPY backend/.env.production /app/.env

# ========================
# Stage 4: Production
# ========================
FROM application as production

# Switch to non-root user
USER appuser

# Set working directory
WORKDIR /app/backend

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/cosmos/health/liveness || exit 1

# Default command
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]

# ========================
# Stage 5: Development (optional)
# ========================
FROM application as development

# Install development dependencies
RUN pip install --no-cache-dir pytest pytest-asyncio httpx

# Switch to non-root user
USER appuser

# Set working directory
WORKDIR /app/backend

# Development command with hot reload
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]