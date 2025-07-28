FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (edit paths if your root folder is named differently)
COPY app.py .
COPY db.py .
COPY helpers.py .
COPY routes/ ./routes/
COPY templates/ ./templates/
COPY static/ ./static/

# Expose Flask port
EXPOSE 5000

CMD ["python", "app.py"]