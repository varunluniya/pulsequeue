FROM python:3.11-slim
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000 GEN4_DB=/data/pulsequeue.db
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /data && useradd -m app && chown -R app /app /data
USER app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD python -c "import urllib.request,os;urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/health')"
# First boot fills /data with the synthetic demo history (seed.py); set GEN4_SEED=0 to start empty.
CMD ["sh", "-c", "python seed.py --if-empty && uvicorn app:app --host 0.0.0.0 --port ${PORT}"]
