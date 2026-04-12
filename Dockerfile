FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
# db.py, models.py, interceptor.py, session_loader.py live at /app/ (top level)
# main.py, config.py, llm.py, persona_router.py live at /app/app/
COPY . .

# Non-root user for security
RUN useradd -m -u 1000 openclaw && chown -R openclaw:openclaw /app
USER openclaw

EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--log-level", "info"]
