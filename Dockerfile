FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy application files
COPY requirements.txt .
COPY app.py .

# Install Flask dependencies
RUN pip install -r requirements.txt

# Install theHarvester properly from source
RUN git clone https://github.com/laramies/theHarvester.git && \
    cd theHarvester && \
    python3 -m pip install --upgrade pip setuptools wheel && \
    python3 -m pip install . && \
    chmod +x theHarvester.py && \
    cd ..

# Add theHarvester to PATH
ENV PATH="/app/theHarvester:${PATH}"
ENV PYTHONPATH="${PYTHONPATH}:/app/theHarvester"

# Expose port
EXPOSE 5000

# Start command  
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
