# --- Technical Services Fault Diagnosis Intelligence Pill -------------
FROM python:3.11-slim AS base

WORKDIR /app

# Install deps first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code only
COPY technical_services_pill/ ./technical_services_pill/

EXPOSE 8000

# Default: run the API server. Override CMD to run demo.
CMD ["uvicorn", "technical_services_pill.app:app", "--host", "0.0.0.0", "--port", "8000"]