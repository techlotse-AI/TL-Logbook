FROM python:slim

LABEL org.opencontainers.image.title="TL-Logbook-Dashboard" \
      org.opencontainers.image.description="Session-isolated FOCA logbook analytics dashboard" \
      org.opencontainers.image.source="https://github.com/techlotse-AI/TL-Logbook" \
      org.opencontainers.image.licenses="Personal-Use-Only"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
  && apt-get upgrade -y \  
  && rm -rf /var/lib/apt/lists/* \
  && groupadd --gid 10001 appuser \
  && useradd --uid 10001 --gid appuser --home-dir /app --no-create-home appuser \
  && mkdir -p /data

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY . /app
RUN chown -R appuser:appuser /app /data

EXPOSE 8000

USER appuser

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
