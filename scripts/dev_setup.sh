#!/usr/bin/env bash
# SERK Retail — reproducible development setup (Ubuntu 24.04, run as a NON-root user with sudo).
# These are the commands that produced the M0/M1 evidence on 2026-11-22. Review before running.
# Secrets are generated locally and never written into this repository.
set -euo pipefail

FRAPPE_COMMIT=fdb29e699921b59d895586b3dbea3e61baedf137   # frappe/frappe develop, 2026-11-21T19:19Z (time-paired)
ERPNEXT_COMMIT=20b97fa800c5548da786ced57111f51c858aea36  # frappe/erpnext develop == supplied ZIP (verified)
BENCH_DIR=${BENCH_DIR:-$HOME/frappe-bench}

# 1. System packages (MariaDB 10.11, Redis, build deps). Node >= 24 and Python 3.14 are required
#    by this Frappe/ERPNext develop snapshot; install them via your preferred toolchain manager.
sudo apt-get install -y mariadb-server mariadb-client libmariadb-dev pkg-config redis-server cron
python3.14 --version && node --version  # expect 3.14.x and v24.x

# 2. MariaDB: utf8mb4 + a root password kept OUTSIDE the repo.
sudo tee /etc/mysql/mariadb.conf.d/99-frappe.cnf >/dev/null <<'EOF'
[mysqld]
character-set-client-handshake = FALSE
character-set-server = utf8mb4
collation-server = utf8mb4_unicode_ci
[mysql]
default-character-set = utf8mb4
EOF
umask 077; [ -f ~/.db_root ] || python3 -c "import secrets;print(secrets.token_urlsafe(24))" > ~/.db_root
[ -f ~/.admin_pw ] || python3 -c "import secrets;print(secrets.token_urlsafe(16))" > ~/.admin_pw
sudo mariadb -e "ALTER USER 'root'@'localhost' IDENTIFIED VIA unix_socket OR mysql_native_password USING PASSWORD('$(cat ~/.db_root)'); FLUSH PRIVILEGES;"

# 3. Pinned sources (bench needs branch names, so pin local branches at exact commits).
python3.14 -m pip install --user frappe-bench
git clone --filter=blob:none https://github.com/frappe/frappe ~/frappe-src
git -C ~/frappe-src branch -f serk-pin-fdb29e69 $FRAPPE_COMMIT
git clone --filter=blob:none https://github.com/frappe/erpnext ~/erpnext-src
git -C ~/erpnext-src branch -f serk-pin-20b97fa8 $ERPNEXT_COMMIT

bench init --frappe-path ~/frappe-src --frappe-branch serk-pin-fdb29e69 --python "$(command -v python3.14)" \
  --skip-assets --skip-redis-config-generation "$BENCH_DIR"
cd "$BENCH_DIR"
bench get-app --branch serk-pin-20b97fa8 --skip-assets ~/erpnext-src
git -C apps/erpnext checkout -- islands/yarn.lock 2>/dev/null || true   # discard tool-generated lockfile drift (R-13)
bench get-app --skip-assets "${SERK_RETAIL_REPO:?set SERK_RETAIL_REPO to this repository path or URL}"
./env/bin/pip install unittest-xml-reporting freezegun

# 4. Redis + sites. serktest.localhost is DISPOSABLE: the M1 tests commit data.
bench setup redis
redis-server config/redis_cache.conf --daemonize yes
redis-server config/redis_queue.conf --daemonize yes
for site in serk.localhost serktest.localhost; do
  bench new-site $site --db-root-username root --db-root-password "$(cat ~/.db_root)" \
    --admin-password "$(cat ~/.admin_pw)" --install-app erpnext --install-app serk_retail
done
bench --site serktest.localhost set-config allow_tests true

# 5. Synthetic data (fictional) + tests.
bench --site serk.localhost execute serk_retail.setup.demo.seed        # writes ~/.serk_demo_credentials (0600)
bench --site serktest.localhost run-tests --module serk_retail.tests.test_m1_flow
bench --site serktest.localhost execute serk_retail.tests.mutation_check.run   # must print MUTANT KILLED
