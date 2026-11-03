# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl ca-certificates && rm -rf /var/lib/apt/lists/*
# Optional organisation CA certificates (see certs/README.md) for TLS-inspecting networks.
COPY --from=certs . /usr/local/share/ca-certificates/extra/
RUN update-ca-certificates
ENV PIP_CERT=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
COPY requirements.txt .
RUN pip install -r requirements.txt
# Optional JavaScript rendering: build with --build-arg INSTALL_PLAYWRIGHT=true and set PLAYWRIGHT_ENABLED=true
ARG INSTALL_PLAYWRIGHT=false
RUN if [ "$INSTALL_PLAYWRIGHT" = "true" ]; then pip install playwright==1.52.0 && playwright install --with-deps chromium; fi
COPY . .
RUN useradd --create-home --uid 10001 app && chown -R app /app
USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
