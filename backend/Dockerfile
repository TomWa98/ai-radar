# Backend image (D11). Secrets are passed at runtime; none belong in this image.
FROM python:3.14.10-slim@sha256:9aaa474097d094040649f2162a627c0049b408f52138d980916788d80f04802f

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# /data is created here so that a new named volume inherits this owner.
RUN useradd --system --uid 10001 --no-create-home app \
    && mkdir /data \
    && chown app /data
USER app

EXPOSE 8000

# One process: the feed scheduler runs inside the application (D2).
CMD ["uvicorn", "ai_radar.main:app", "--host", "0.0.0.0", "--port", "8000"]
