FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /srv
RUN useradd --system --uid 10001 tessera
COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY backend/ ./backend/
COPY data/schemas/ ./data/schemas/
COPY data/synthetic/ ./data/synthetic/
COPY scripts/ ./scripts/
RUN mkdir -p /srv/data/uploads && chown -R tessera /srv/data/uploads /srv/data/schemas
USER tessera
WORKDIR /srv/backend
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
