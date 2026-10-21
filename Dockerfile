# =============================================================================
# Dockerfile — AI Data Analyst
# =============================================================================
# Build and run both services: docker compose up --build
# =============================================================================

# Use official Python slim image for a smaller footprint
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Create a non-root user for security
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --shell /bin/bash --create-home appuser

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
# NOTE: .env is intentionally excluded via .dockerignore
COPY app.py agent.py analysis_tools.py backend_api.py backend_client.py chart_builder.py \
     config.py data_loader.py database_connectors.py user_services.py evaluation.py ./

# Copy sample data for demo purposes
COPY sample_data/ ./sample_data/

# Copy evaluation files
COPY evaluation/ ./evaluation/

# Copy docs
COPY docs/ ./docs/
COPY assets/ ./assets/

# Set correct file ownership
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Expose Streamlit default port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run the Streamlit application
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]
