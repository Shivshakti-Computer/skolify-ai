FROM python:3.11-slim

# HuggingFace non-root user requirement
RUN useradd -m -u 1000 user

USER user

ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    SENTENCE_TRANSFORMERS_HOME=/home/user/app/.cache

WORKDIR $HOME/app

# Dependencies install
COPY --chown=user requirements.txt .

RUN pip install --no-cache-dir --user -r requirements.txt

# Project code copy
COPY --chown=user . .

# Required directories
RUN mkdir -p data/processed data/raw data/chroma_db .cache

EXPOSE 7860

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1"]