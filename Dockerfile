FROM python:3.12.10-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip==26.2.1 \
    && /opt/venv/bin/pip install .

FROM python:3.12.10-slim-bookworm AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=UTC
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app
COPY --from=builder /opt/venv /opt/venv
WORKDIR /app
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app migrations ./migrations
COPY --chown=app:app src ./src
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "shopee_affiliate_agent.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM builder AS test
RUN /opt/venv/bin/pip install '.[dev]'
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=UTC
WORKDIR /app
COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY migrations ./migrations
COPY tests ./tests
CMD ["pytest"]
