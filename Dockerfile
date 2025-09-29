FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy application files first
COPY requirements.txt .
COPY app.py .

# Install all dependencies including theHarvester
RUN pip install -r requirements.txt

# Try to install theHarvester from PyPI or source
RUN pip install theHarvester || \
    (git clone https://github.com/laramies/theHarvester.git && \
     cd theHarvester && \
     pip install . && \
     cd .. && \
     rm -rf theHarvester)

# Expose port
EXPOSE 5000

# Start command
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
