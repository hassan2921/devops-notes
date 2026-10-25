# ---- Custom image for the Flask web app ----
# Small official Python base image
FROM python:3.12-slim

# Don't write .pyc files; flush logs straight to `docker logs`
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy requirements first so this layer is cached when only code changes
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Good practice: don't run as root inside the container
RUN useradd -m appuser && chown -R appuser /app
USER appuser

EXPOSE 5000

# Container-level health check (shows "healthy" in `docker ps`)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')" || exit 1

# Production WSGI server instead of Flask's dev server
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
