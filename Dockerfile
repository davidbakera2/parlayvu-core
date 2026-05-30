FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# curl: healthcheck + nodesource bootstrap.
# nodejs + wrangler: required for Dylan's Cloudflare Pages deploy path
# (deploy_static_directory_to_cloudflare shells out to `wrangler pages
# deploy`). Wrangler is pre-installed globally so the first deploy
# doesn't pay npx's cold-cache download tax inside the container.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g wrangler@latest \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

# client_artifacts is the flat-file fallback source for Nathan's
# get_project_context tool. Must be in the image so the tool finds data
# when the database has no row for the requested client.
COPY client_artifacts ./client_artifacts

# Alembic is required to run database migrations in production
# (e.g. `alembic upgrade head`). These files were previously missing
# from the production image, which is why the conversation_turns table
# was never created.
COPY alembic.ini .
COPY alembic ./alembic

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/health || exit 1

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
