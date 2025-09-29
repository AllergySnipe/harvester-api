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

# Install Flask dependencies ONLY (remove theHarvester from requirements.txt)
RUN pip install -r requirements.txt

# Install theHarvester from source
RUN git clone https://github.com/laramies/theHarvester.git && \
    cd theHarvester && \
    pip install -r requirements.txt && \
    pip install . && \
    cd .. && \
    chmod +x theHarvester/theHarvester.py

# Add theHarvester to PATH
ENV PATH="/app/theHarvester:${PATH}"
ENV PYTHONPATH="${PYTHONPATH}:/app/theHarvester"

# Expose port
EXPOSE 5000

# Start command
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
