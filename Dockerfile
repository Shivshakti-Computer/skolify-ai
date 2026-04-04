# Dockerfile
# Root directory mein rakho: skolify-ai/Dockerfile

FROM python:3.11-slim

# Build tools
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Requirements copy + install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Poora project copy karo
COPY . .

# Data directories banao
RUN mkdir -p data/processed data/raw data/chroma_db

# HuggingFace port
EXPOSE 7860

# Start
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]