FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./

RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./backend/

WORKDIR /app/backend

EXPOSE 8000

CMD ["sh", "-c", "uv run --project /app --no-sync alembic upgrade head && uv run --project /app --no-sync uvicorn app.main:app --host 0.0.0.0 --port 8000"]
