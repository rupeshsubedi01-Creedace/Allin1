FROM python:3.12-slim

# ffmpeg is required for merging separate video/audio streams and for MP3
# extraction. It is installed from the Debian repos to keep the image small
# and reproducible.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY scripts/ scripts/

ENV ALLIN1_DATA_DIR=/app/data
ENV PORT=8000
ENV WEB_CONCURRENCY=1

RUN mkdir -p /app/data && chmod +x /app/scripts/start.sh

# 8000 is the default; platforms that inject PORT (Render, Railway, …) will
# override it and scripts/start.sh picks the value up automatically.
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT}/api/health" || exit 1

CMD ["bash", "scripts/start.sh"]
