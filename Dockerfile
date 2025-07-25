# Use an official Python 3 slim image (multi-arch, works on ARM)
FROM python:3.11-slim

# Set working directory in container
WORKDIR /app

# Install required Python packages (Flask, yfinance, APScheduler)
RUN pip install --no-cache-dir flask yfinance apscheduler

# Copy application code into the container
COPY app.py .
COPY templates ./templates

# Expose port 5000 for Flask
EXPOSE 5000

# Start the Flask app
CMD ["python", "app.py"]
