# ── Stage: backend image ───────────────────────────────────────────────────────
FROM python:3.12-slim

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl sqlite3 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies (all services combined)
COPY deploy/azure/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy application code
COPY shared/ /app/shared/
COPY migrations/ /app/lib-management-app/migrations/
COPY scripts/ /app/lib-management-app/scripts/
COPY db/ /app/lib-management-app/db/
COPY services/api-gateway/        /app/services/api-gateway/
COPY services/library-data-service/ /app/services/library-data-service/
COPY services/scraper-service/    /app/services/scraper-service/
COPY services/comparison-service/ /app/services/comparison-service/
COPY services/recommendation-service/ /app/services/recommendation-service/
COPY services/notification-service/  /app/services/notification-service/
COPY services/scheduler-service/  /app/services/scheduler-service/

# entrypoint
COPY deploy/azure/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Persistent data volume for SQLite
VOLUME ["/data/db"]

# api-gateway is the external-facing port
EXPOSE 8000

ENV DATABASE_URL="sqlite+aiosqlite:////data/db/library_management.db" \
    INTERNAL_SERVICE_KEY="change-in-prod" \
    JWT_SECRET_KEY="change-in-prod" \
    JWT_EXPIRE_MINUTES="480" \
    DEFAULT_ADMIN_PASSWORD="admin123" \
    LLM_PROVIDER="" \
    LLM_MODEL="gpt-4o-mini" \
    LLM_API_KEY="" \
    SMTP_HOST="smtp.office365.com" \
    SMTP_PORT="587" \
    SMTP_USERNAME="" \
    SMTP_PASSWORD="" \
    SCHEDULE_ENABLED="true"

ENTRYPOINT ["/entrypoint.sh"]
