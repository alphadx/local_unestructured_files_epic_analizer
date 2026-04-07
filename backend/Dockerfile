FROM python:3.11-slim

WORKDIR /app

# System dependencies for python-magic and build tools needed by hdbscan
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    python3-dev \
    libmagic1 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Optional: install external deduplication tools (rmlint, jdupes).
# Set ENABLE_DEDUP_TOOLS=true at build time to include them.
# Example: docker build --build-arg ENABLE_DEDUP_TOOLS=true .
ARG ENABLE_DEDUP_TOOLS=false
RUN if [ "$ENABLE_DEDUP_TOOLS" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            rmlint \
            jdupes \
        && rm -rf /var/lib/apt/lists/*; \
    fi

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/

ENV PYTHONPATH=/app
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
