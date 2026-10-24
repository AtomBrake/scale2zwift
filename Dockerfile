FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATA_DIR=/data \
    PORT=8080

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY scale2zwift ./scale2zwift

RUN useradd --uid 1000 --create-home app \
    && mkdir -p /data && chown app:app /data
USER app
VOLUME /data
EXPOSE 8080

HEALTHCHECK --interval=60s --timeout=5s \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ['PORT'])"

CMD ["python", "-m", "scale2zwift"]
