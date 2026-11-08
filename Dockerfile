# LeadStack's production image: the API (default command) and, with
# `crm-app-worker` / `crm-app-migrate` as the command, the worker and the
# migrations. One image for all three, built from the locked dependencies.
#
# - No secret is baked in: settings and secrets come from the environment at
#   run time (SaaS-OS ADR-0012). `.dockerignore` keeps `.env*`, `.git` and
#   local build output out of the build context.
# - Base images are pinned by digest as well as tag, as SaaS-OS pins its own;
#   a moved tag cannot change what is built. The Python base is the digest
#   SaaS-OS v0.10.0's Dockerfile uses.
# - The SaaS-OS dependency is installed from `uv.lock`, so the image carries
#   exactly the approved pin (decision K3.9); `--locked` fails the build if
#   the lock and the manifest disagree.
# - Runs as a non-root user. No compiler, git or uv in the final image.

# --- Frontend: the single-page app, served by the API at /app -------------------------
FROM node:24-slim@sha256:01d566e8d94d8c619591d78652babfccd3c6992a3dffa9ed5ab39e11cf6c70e9 AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --ignore-scripts
COPY frontend/ ./
RUN npm run build

# --- Python: the locked environment, the product installed non-editable ---------------
FROM python:3.13-slim@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc AS python
COPY --from=ghcr.io/astral-sh/uv:0.12.3@sha256:2d890623d310b57771ce840f0da5eed5fc6d657da05ffaa45d82797b53fa3abc /uv /usr/local/bin/uv
# git: the SaaS-OS dependency is a pinned git commit.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev --no-editable \
    && rm -rf /app/src

# --- Runtime -------------------------------------------------------------------------
FROM python:3.13-slim@sha256:09a17cad02668ae61ece136b4fd36ac3849e14f670ebedb637ea3e15580525bc
# pip is never used at run time (SaaS-OS removes it for the same reason: its
# vendored copies show up in image scans). Debian's security updates are
# applied first: the pinned base can lag them (staging scan, 2026-11-08:
# zlib1g CVE-2026-85091 and CVE-2026-76844, fixed in deb13u1).
RUN apt-get update \
    && apt-get upgrade --yes --no-install-recommends \
    && rm -rf /var/lib/apt/lists/* \
    && pip uninstall --yes pip \
    && rm -rf /usr/local/lib/python3.13/ensurepip \
    && groupadd --system app \
    && useradd --system --gid app --home /app app
WORKDIR /app
COPY --from=python --chown=app:app /app/.venv /app/.venv
COPY --from=frontend --chown=app:app /build/dist /app/frontend/dist
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CRM_APP_FRONTEND_DIST=/app/frontend/dist
USER app
EXPOSE 8000
# Readiness, not liveness: a process whose database or Redis is unreachable
# is reported unhealthy (as SaaS-OS's image does). python:3.13-slim has no
# curl or wget.
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/readyz', timeout=3)"]
# The forwarded client address is SaaS-OS's to read (`TRUST_PROXY_HEADERS`,
# last hop): uvicorn does not rewrite it.
CMD ["uvicorn", "crm_app.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers", "--no-server-header"]
