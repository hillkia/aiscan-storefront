# Hugging Face Spaces menjalankan container ini. Port 7860 = bawaan HF.
FROM python:3.11-slim

# HF Spaces menjalankan container sebagai user non-root (uid 1000).
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH" \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

COPY --chown=user . .

EXPOSE 7860
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "7860"]
