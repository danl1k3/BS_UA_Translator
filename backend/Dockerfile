FROM nvidia/cuda:12.2.2-runtime-ubuntu22.04

# Prevent interactive prompts during apt-get
ENV DEBIAN_FRONTEND=noninteractive

# Install Python 3.10, pip, and system dependencies needed for CTranslate2 (OpenMP)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.10 \
    python3.10-venv \
    python3-pip \
    libgomp1 \
    && ln -sf /usr/bin/python3.10 /usr/bin/python \
    && ln -sf /usr/bin/pip3 /usr/bin/pip \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code (DLLs and virtual env are excluded by .dockerignore)
COPY . .

# Expose the backend port
EXPOSE 8000

# Set environment variables for the model location
ENV MODEL_PATH=/app/models/nllb_int8
ENV TOKENIZER_PATH=/app/models/nllb_int8/sentencepiece.bpe.model
ENV PYTHONUNBUFFERED=1

# NVIDIA Container Toolkit environment variables
ENV NVIDIA_VISIBLE_DEVICES=all
ENV NVIDIA_DRIVER_CAPABILITIES=compute,utility

# Run FastAPI app with uvicorn binding to 0.0.0.0
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
