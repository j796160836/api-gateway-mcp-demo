FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt ./
RUN grep -E '^(fastapi|uvicorn)==' requirements.txt > /tmp/rest-requirements.txt \
    && python -m pip install --no-cache-dir -r /tmp/rest-requirements.txt \
    && mkdir /data && chown 10001:10001 /data
COPY api.py config.py database.py reset_demo_db.py ./
USER 10001:10001
