# Backend container for the Hedge Fund AI Agent Council API.
# Uses uv for fast, reproducible installs, then runs uvicorn.
FROM python:3.11-slim

# uv (static binary) for dependency management.
COPY --from=ghcr.io/astral-sh/uv:0.7.15 /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_SYSTEM_PYTHON=1 \
    UV_COMPILE_BYTECODE=1

WORKDIR /app

# Install dependencies first (better layer caching).
COPY pyproject.toml ./
RUN uv pip install --system \
    "fastapi==0.115.6" \
    "uvicorn[standard]==0.34.0" \
    "pydantic==2.10.4" \
    "pydantic-settings==2.7.1" \
    "python-dotenv==1.0.1" \
    "exa-py==1.8.7" \
    "youtube-transcript-api==0.6.3" \
    "google-api-python-client==2.157.0" \
    "boto3>=1.43.25" \
    "sqlalchemy>=2.0.50" \
    "psycopg[binary]>=3.3.4" \
    "alembic>=1.18.4"

# App source.
COPY app ./app
COPY scripts ./scripts

EXPOSE 8000

# No .env in the image: config comes from the container environment.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
