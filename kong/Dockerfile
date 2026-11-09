FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && mkdir /data && chown 10001:10001 /data

COPY api.py config.py database.py demo_mcp.py gateway.py reset_demo_db.py ./
USER 10001:10001
