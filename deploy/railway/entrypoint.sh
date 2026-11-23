#!/usr/bin/env bash
# SERK Retail container entrypoint (Railway demo/staging).
#
# Required env:  DB_HOST, DB_ROOT_PASSWORD, REDIS_URL
# Optional env:  DB_PORT (3306), SITE_NAME (serk-demo.local), PUBLIC_URL, PORT (8000),
#                SERK_DEMO_SEED (1 = load fictional demo data on first boot),
#                DATA_DIR (/data, a persistent volume), GUNICORN_WORKERS (2),
#                SERK_ADMIN_PASSWORD, SERK_DEMO_PASSWORD (see below), SERK_DEMO_HISTORY_DAYS (0 = off),
#                SERK_AI_PROVIDER / SERK_AI_MODEL / SERK_AI_API_KEY / SERK_AI_BASE_URL (AI analyst, as in SERK Finance)
# Secrets: if SERK_ADMIN_PASSWORD / SERK_DEMO_PASSWORD are set (e.g. Railway variables), they are
# (re)applied on EVERY boot, so rotating the variable rotates the password (and overwrites any
# change made in the app). If unset, random passwords are generated on first boot. Either way the
# current values are written ONLY to $DATA_DIR/secrets/ (0600) and never printed to the logs.
set -euo pipefail

DATA_DIR=${DATA_DIR:-/data}
BENCH=/home/frappe/frappe-bench
IMAGE_SITES=/home/frappe/sites-image
SITE_NAME=${SITE_NAME:-serk-demo.local}
DB_PORT=${DB_PORT:-3306}
PORT=${PORT:-8000}

if [ "$(id -u)" = "0" ]; then
	mkdir -p "$DATA_DIR/sites" "$DATA_DIR/secrets" "$DATA_DIR/logs"
	chown -R frappe:frappe "$DATA_DIR"
	chmod 700 "$DATA_DIR/secrets"
	exec setpriv --reuid=frappe --regid=frappe --init-groups --reset-env env \
		DATA_DIR="$DATA_DIR" SITE_NAME="$SITE_NAME" DB_HOST="${DB_HOST:?DB_HOST is required}" DB_PORT="$DB_PORT" \
		DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:?DB_ROOT_PASSWORD is required}" REDIS_URL="${REDIS_URL:?REDIS_URL is required}" \
		PUBLIC_URL="${PUBLIC_URL:-}" PORT="$PORT" SERK_DEMO_SEED="${SERK_DEMO_SEED:-1}" \
		GUNICORN_WORKERS="${GUNICORN_WORKERS:-2}" SERK_ADMIN_PASSWORD="${SERK_ADMIN_PASSWORD:-}" \
		SERK_DEMO_PASSWORD="${SERK_DEMO_PASSWORD:-}" SERK_DEMO_HISTORY_DAYS="${SERK_DEMO_HISTORY_DAYS:-0}" \
		SERK_AI_PROVIDER="${SERK_AI_PROVIDER:-}" SERK_AI_MODEL="${SERK_AI_MODEL:-}" SERK_AI_API_KEY="${SERK_AI_API_KEY:-}" \
		SERK_AI_BASE_URL="${SERK_AI_BASE_URL:-}" ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY:-}" OPENAI_API_KEY="${OPENAI_API_KEY:-}" HOME=/home/frappe PATH="/home/frappe/.local/bin:/usr/local/bin:/usr/bin:/bin" \
		"$0"
fi

log() { echo "[serk-entrypoint] $*"; }
cd "$BENCH"

# Persistent sites dir on the volume; refresh code-owned files from the image on every boot.
if [ ! -L sites ]; then rm -rf sites; ln -s "$DATA_DIR/sites" sites; fi
cp "$IMAGE_SITES/apps.txt" sites/apps.txt
[ -f "$IMAGE_SITES/apps.json" ] && cp "$IMAGE_SITES/apps.json" sites/apps.json || true
rm -rf sites/assets && cp -a "$IMAGE_SITES/assets" sites/assets
[ -f sites/common_site_config.json ] || echo '{}' > sites/common_site_config.json
rm -rf logs && ln -s "$DATA_DIR/logs" logs

redis_base=${REDIS_URL%/}
bench set-config -g db_host "$DB_HOST" >/dev/null
bench set-config -g db_port "$DB_PORT" >/dev/null
bench set-config -g redis_cache "$redis_base" >/dev/null
bench set-config -g redis_queue "$redis_base" >/dev/null
bench set-config -g redis_socketio "$redis_base" >/dev/null
bench set-config -g serve_default_site true >/dev/null

log "waiting for MariaDB at $DB_HOST:$DB_PORT"
for i in $(seq 1 60); do
	if mariadb-admin --host="$DB_HOST" --port="$DB_PORT" --user=root --password="$DB_ROOT_PASSWORD" ping --silent 2>/dev/null; then break; fi
	[ "$i" = 60 ] && { log "MariaDB not reachable"; exit 1; }
	sleep 3
done

umask 077
ADMIN_PW_FILE="$DATA_DIR/secrets/administrator_password"
if [ ! -d "sites/$SITE_NAME" ]; then
	log "first boot: creating site $SITE_NAME (this takes a few minutes)"
	if [ -n "$SERK_ADMIN_PASSWORD" ]; then printf '%s\n' "$SERK_ADMIN_PASSWORD" > "$ADMIN_PW_FILE"
	elif [ ! -f "$ADMIN_PW_FILE" ]; then python3 -c "import secrets;print(secrets.token_urlsafe(18))" > "$ADMIN_PW_FILE"; fi
	bench new-site "$SITE_NAME" --db-host "$DB_HOST" --db-port "$DB_PORT" \
		--db-root-username root --db-root-password "$DB_ROOT_PASSWORD" \
		--mariadb-user-host-login-scope='%' --admin-password "$(cat "$ADMIN_PW_FILE")" \
		--install-app erpnext --install-app serk_retail --set-default
	if [ "${SERK_DEMO_SEED}" = "1" ]; then
		log "loading FICTIONAL demo data (SERK Demo Mart)"
		# Keep HOME=/home/frappe: bench is a pip --user install, so a different HOME hides it
		# from Python. The seed writes ~/.serk_demo_credentials (0600); move it to the volume.
		# The seed reads SERK_DEMO_PASSWORD from the environment (random per user if unset).
		bench --site "$SITE_NAME" execute serk_retail.setup.demo.seed >/dev/null
		mv -f "$HOME/.serk_demo_credentials" "$DATA_DIR/secrets/demo_user_credentials"
	fi
	log "site created; credentials are in $DATA_DIR/secrets/ (not logged)"
else
	# Re-apply passwords managed by variables (rotation). Values go via env, never argv/logs.
	if [ -n "$SERK_ADMIN_PASSWORD" ]; then
		bench --site "$SITE_NAME" execute serk_retail.setup.demo.apply_env_password \
			--kwargs '{"user": "Administrator", "env_var": "SERK_ADMIN_PASSWORD"}' >/dev/null
		printf '%s\n' "$SERK_ADMIN_PASSWORD" > "$ADMIN_PW_FILE"
	fi
	if [ -n "$SERK_DEMO_PASSWORD" ] && [ "${SERK_DEMO_SEED}" = "1" ]; then
		bench --site "$SITE_NAME" execute serk_retail.setup.demo.apply_env_password \
			--kwargs '{"user": "demo", "env_var": "SERK_DEMO_PASSWORD"}' >/dev/null
		mv -f "$HOME/.serk_demo_credentials" "$DATA_DIR/secrets/demo_user_credentials"
	fi
fi
umask 022

bench use "$SITE_NAME" >/dev/null
[ -n "$PUBLIC_URL" ] && bench --site "$SITE_NAME" set-config host_name "$PUBLIC_URL" >/dev/null
bench --site "$SITE_NAME" set-config developer_mode 0 >/dev/null
bench --site "$SITE_NAME" migrate
bench --site "$SITE_NAME" enable-scheduler >/dev/null || true

# Fictional trading history for the demo dashboard (background job; idempotent, runs once).
if [ "${SERK_DEMO_SEED}" = "1" ] && [ "${SERK_DEMO_HISTORY_DAYS:-0}" -gt 0 ] 2>/dev/null; then
	log "queueing FICTIONAL demo history (${SERK_DEMO_HISTORY_DAYS} days) as a background job"
	bench --site "$SITE_NAME" execute serk_retail.setup.demo_history.enqueue \
		--kwargs "{\"days\": ${SERK_DEMO_HISTORY_DAYS}}" >/dev/null || log "demo history not queued"
fi

log "starting worker, scheduler and web on :$PORT"
bench worker --queue short,default,long &
bench schedule &
# sites is a symlink to the volume, so a relative ../env would resolve under $DATA_DIR: use $BENCH.
(cd sites && exec "$BENCH/env/bin/gunicorn" --bind "0.0.0.0:$PORT" --workers "${GUNICORN_WORKERS}" \
	--timeout 120 --graceful-timeout 30 --worker-tmp-dir /dev/shm \
	--access-logfile - --error-logfile - --pythonpath /home/frappe/serk-deploy serk_wsgi:application --preload) &
# If any process exits, exit the container so Railway restarts it.
wait -n
log "a process exited; stopping container"
exit 1
