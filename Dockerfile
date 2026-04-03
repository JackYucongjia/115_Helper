FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Create data directory
RUN mkdir -p /app/data

# Environment
ENV HOST=0.0.0.0
ENV PORT=8115
ENV DATA_DIR=/app/data
ENV COOKIE_PATH=/app/data/115-cookies.txt

EXPOSE 8115

CMD ["python", "backend/run.py"]
