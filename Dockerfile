FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt constraints.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home portfolio
COPY --chown=portfolio:portfolio app ./app
COPY --chown=portfolio:portfolio main.py .
USER portfolio
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--ws-max-size", "1024", "--ws-max-queue", "4", "--limit-concurrency", "128", "--timeout-keep-alive", "5", "--no-proxy-headers"]
