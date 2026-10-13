FROM python:3.13-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY document_chunking/ ./document_chunking/
COPY Analyze-LegalDocumentsUI.py .

# Set ownership and switch to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# Run Streamlit with security settings enabled
ENTRYPOINT ["streamlit", "run", "Analyze-LegalDocumentsUI.py", \
    "--server.port=8501", \
    "--server.address=0.0.0.0", \
    "--server.headless=true", \
    "--server.enableCORS=true", \
    "--server.enableXsrfProtection=true", \
    "--server.enableWebsocketCompression=false", \
    "--browser.gatherUsageStats=false"]
