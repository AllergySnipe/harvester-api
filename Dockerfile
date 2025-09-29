FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install theHarvester
RUN git clone https://github.com/laramies/theHarvester.git
WORKDIR /app/theHarvester

# Install theHarvester dependencies - CORRECTED PATH
RUN pip install -r requirements.txt

# Alternative method if requirements.txt doesn't work
# RUN pip install -r requirements/base.txt || pip install -r requirements.txt

# Go back to app directory
WORKDIR /app

# Copy application files
COPY requirements.txt .
COPY app.py .

# Install Flask dependencies
RUN pip install -r requirements.txt

# Add theHarvester to Python path
ENV PYTHONPATH="${PYTHONPATH}:/app"

# Expose port
EXPOSE 5000

# Start command
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
