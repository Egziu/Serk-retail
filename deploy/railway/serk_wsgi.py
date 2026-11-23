# SERK Retail — WSGI entry for the single-container Railway image.
#
# 1. Static files: Frappe's plain `frappe.app:application` serves no static files (in a normal
#    production install nginx does that). This container has no nginx, so wrap the app with
#    Frappe's own static middleware (/assets from sites/assets, public /files from the site).
# 2. Site pinning: Frappe picks the site from the Host header, so the public *.up.railway.app
#    name and Railway's healthcheck host would 404 ("<host> does not exist"). This container
#    serves exactly one site, so every request is pinned to $SITE_NAME (overriding any
#    client-sent X-Frappe-Site-Name).
# 3. ProxyFix trusts the one proxy hop in front of it (Railway's edge) for scheme/host/client IP.
#
# Run from the bench `sites` directory: gunicorn --pythonpath <dir> serk_wsgi:application
import os

import frappe.app
from werkzeug.middleware.proxy_fix import ProxyFix

SITE_NAME = os.environ.get("SITE_NAME") or "serk-demo.local"


class PinSite:
	def __init__(self, app, site: str):
		self.app = app
		self.site = site

	def __call__(self, environ, start_response):
		environ["HTTP_X_FRAPPE_SITE_NAME"] = self.site
		return self.app(environ, start_response)


application = ProxyFix(
	PinSite(frappe.app.application_with_statics(), SITE_NAME), x_for=1, x_proto=1, x_host=1, x_port=1
)
