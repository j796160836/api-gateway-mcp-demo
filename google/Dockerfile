FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY api.py config.py database.py cloud_run.py ./
ENV SQLITE_PATH=/tmp/order-demo.sqlite3
USER 65532:65532
CMD ["sh", "-c", "exec python -m uvicorn cloud_run:app --host 0.0.0.0 --port \"${PORT:-8080}\""]
