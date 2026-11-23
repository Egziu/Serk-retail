# SERK Retail — WSGI entry for the single-container Railway image.
# Frappe's plain `frappe.app:application` serves no static files (in a normal production
# install nginx does that). This container has no nginx, so wrap the app with Frappe's own
# static middleware (/assets from sites/assets, public /files from the site) and trust the
# one proxy hop in front of it (Railway's edge) for scheme/host/client IP.
# Run from the bench `sites` directory: gunicorn serk_wsgi:application
import frappe.app
from werkzeug.middleware.proxy_fix import ProxyFix

application = ProxyFix(frappe.app.application_with_statics(), x_for=1, x_proto=1, x_host=1, x_port=1)
