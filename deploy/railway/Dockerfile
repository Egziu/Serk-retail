# SERK Retail — demo/staging image for Railway (Frappe + ERPNext + serk_retail).
# DEVELOPER PREVIEW: synthetic data only; not production-ready (see docs/releases).
# Build context = repository root. Railway: set Dockerfile path to deploy/railway/Dockerfile.
FROM python:3.14-slim-bookworm

ARG FRAPPE_COMMIT=fdb29e699921b59d895586b3dbea3e61baedf137
ARG ERPNEXT_COMMIT=20b97fa800c5548da786ced57111f51c858aea36
ARG NODE_VERSION=24.22.3

ENV DEBIAN_FRONTEND=noninteractive PIP_DISABLE_PIP_VERSION_CHECK=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
		git curl ca-certificates xz-utils build-essential pkg-config libmariadb-dev mariadb-client \
		libffi-dev libssl-dev libjpeg62-turbo-dev zlib1g-dev fonts-dejavu-core util-linux cron procps \
	&& rm -rf /var/lib/apt/lists/* \
	&& curl -fsSL https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz \
		| tar -xJ -C /usr/local --strip-components=1 \
	&& npm install -g yarn@1.22.22 && node --version && python3 --version

RUN useradd -m -s /bin/bash frappe
USER frappe
WORKDIR /home/frappe
ENV PATH=/home/frappe/.local/bin:$PATH

# Pinned upstream sources (bench requires branch names, so pin local branches at exact commits).
RUN pip install --user --no-cache-dir frappe-bench==5.31.1 \
	&& git clone --filter=blob:none --no-checkout https://github.com/frappe/frappe src/frappe \
	&& git -C src/frappe branch -f serk-pin ${FRAPPE_COMMIT} && git -C src/frappe checkout -q serk-pin \
	&& git clone --filter=blob:none --no-checkout https://github.com/frappe/erpnext src/erpnext \
	&& git -C src/erpnext branch -f serk-pin ${ERPNEXT_COMMIT} && git -C src/erpnext checkout -q serk-pin

RUN bench init --frappe-path /home/frappe/src/frappe --frappe-branch serk-pin --python "$(command -v python3)" \
		--skip-assets --skip-redis-config-generation frappe-bench \
	&& cd frappe-bench \
	&& bench get-app --branch serk-pin --skip-assets /home/frappe/src/erpnext \
	&& git -C apps/erpnext checkout -- islands/yarn.lock

# SERK app from this repository (installed the same way bench does for a local app).
COPY --chown=frappe:frappe . /home/frappe/frappe-bench/apps/serk_retail
RUN cd frappe-bench \
	&& rm -rf apps/serk_retail/.git \
	&& ./env/bin/pip install --no-cache-dir -e apps/serk_retail \
	&& printf "frappe\nerpnext\nserk_retail\n" > sites/apps.txt \
	&& bench build --production \
	&& mv sites /home/frappe/sites-image

USER root
COPY deploy/railway/entrypoint.sh /usr/local/bin/serk-entrypoint
# WSGI wrapper: serves /assets and public /files (no nginx in this image) behind Railway's proxy.
COPY deploy/railway/serk_wsgi.py /home/frappe/serk-deploy/serk_wsgi.py
RUN chmod 755 /usr/local/bin/serk-entrypoint && chmod 644 /home/frappe/serk-deploy/serk_wsgi.py
ENV PORT=8000
EXPOSE 8000
# Starts as root only to fix ownership of the mounted volume, then drops to the frappe user.
CMD ["/usr/local/bin/serk-entrypoint"]
