FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY run.py ./run.py
COPY README.md ./README.md
COPY scripts ./scripts
COPY backfill_exit_prices.py ./backfill_exit_prices.py
COPY ross-cameron-methodology.md ./ross-cameron-methodology.md
COPY ross-cameron-transcripts.txt ./ross-cameron-transcripts.txt
COPY config.example.yaml ./config.example.yaml

RUN mkdir -p /app/logs /app/data /app/config

EXPOSE 8081

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD curl -fsS http://127.0.0.1:8081/api/health || exit 1

CMD ["python", "run.py", "--config", "/app/config/config.yaml"]
