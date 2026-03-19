# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder
WORKDIR /app
ENV PIP_NO_CACHE_DIR=1
COPY requirements.txt .
RUN pip install --upgrade pip && pip wheel --wheel-dir /wheels -r requirements.txt

FROM python:3.11-slim AS runtime
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY --from=builder /wheels /wheels
RUN pip install --no-cache /wheels/* && rm -rf /wheels
COPY . .
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "agentshield.api.server:app", "--host", "0.0.0.0", "--port", "8000"]
