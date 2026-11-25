# Contoso Air mock tools service.
# The build context is a staging directory containing the contents of tools/ plus data/.
# scripts/deploy_tools.py prepares it. To build locally with Docker instead:
#   python scripts/deploy_tools.py --stage-only .deploy/tools
#   docker build -t contoso-air-tools .deploy/tools
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CONTOSO_DATA_DIR=/app/data

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --progress-bar off -r requirements.txt
COPY . .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
