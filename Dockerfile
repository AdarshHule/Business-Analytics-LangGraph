# Image for the Streamlit application.
# python:3.13-slim is multi-architecture: on an Apple Silicon Mac Docker pulls the arm64 variant automatically.
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Copy requirements FIRST: Docker caches this layer, so code changes don't reinstall packages.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app/ app/
COPY database/seed_data.py database/seed_data.py
COPY tests/ tests/

# Run as a non-root user (good container security practice).
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser

EXPOSE 8501

HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health')"

# 1) load synthetic data (skips if already loaded)  2) start the web app
CMD ["sh", "-c", "python database/seed_data.py && streamlit run app/main.py --server.port=8501 --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false"]
