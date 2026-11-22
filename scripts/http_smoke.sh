#!/usr/bin/env bash
# HTTP smoke test against a running dev server (bench serve): receive -> open -> sell (x2, same
# key) -> rejected client price -> blind close. Uses synthetic users from ~/.serk_demo_credentials
# (written by demo.seed). Never prints passwords. Adds synthetic data: dev/test sites only.
# Usage: scripts/http_smoke.sh serk.localhost http://127.0.0.1:8000
set -euo pipefail
SITE=$1; BASE=$2; RUN=$$-$(date +%s)
pw() { awk -v u="$1" '$1==u{print $2}' ~/.serk_demo_credentials; }

session() {  # $1 user -> prints cookie jar path
	local jar; jar=$(mktemp)
	python3 -c 'import json,sys;print(json.dumps({"usr":sys.argv[1],"pwd":sys.argv[2]}))' "$1" "$(pw "$1")" |
		curl -s -o /dev/null -w "login $1 -> %{http_code}\n" -H "Host: $SITE" -H "Content-Type: application/json" \
			-c "$jar" -X POST "$BASE/api/method/login" --data-binary @- >&2
	echo "$jar"
}
post() {  # $1 jar $2 method $3 json -> prints compact summary
	curl -s -H "Host: $SITE" -H "Content-Type: application/json" -b "$1" -X POST "$BASE/api/method/$2" --data-binary "$3" |
		python3 -c 'import json,sys
d=json.load(sys.stdin); m=d.get("message")
if m is not None: print("OK", json.dumps({k:m[k] for k in m if k in ("reference_name","grand_total","change_amount","idempotent_replay","variances","status")}))
else: print("ERR", d.get("exc_type"), "-", (d.get("exception") or "").split(": ",1)[-1][:140])'
}

R=$(session receiver@serk.test); C=$(session cashier1@serk.test)
trap 'rm -f "$R" "$C"' EXIT
echo "receive:      $(post "$R" serk_retail.api.inventory.receive_stock '{"company":"SERK Demo Mart","supplier":"SERK Synthetic Supplier PLC","warehouse":"Stores - SDM","items":[{"item_code":"SERK-WATER-500","qty":48,"rate":12}],"idempotency_key":"smoke-recv-'$RUN'"}')"
OPEN=$(curl -s -H "Host: $SITE" -H "Content-Type: application/json" -b "$C" -X POST "$BASE/api/method/serk_retail.api.pos.open_shift" \
	--data-binary '{"pos_profile":"SDM Lane 1","opening_cash":300,"idempotency_key":"smoke-open-'$RUN'"}')
OE=$(python3 -c "import json,sys;print(json.loads(sys.argv[1])['message']['pos_opening_entry'])" "$OPEN"); echo "open_shift:   OK $OE"
SALE='{"pos_opening_entry":"'$OE'","items":[{"barcode":"0012345678905","qty":2}],"payments":[{"mode_of_payment":"Cash","amount":100}],"idempotency_key":"smoke-sale-'$RUN'"}'
echo "sale #1:      $(post "$C" serk_retail.api.pos.submit_sale "$SALE")"
echo "sale #2 same: $(post "$C" serk_retail.api.pos.submit_sale "$SALE")"
echo "client price: $(post "$C" serk_retail.api.pos.submit_sale '{"pos_opening_entry":"'$OE'","items":[{"item_code":"SERK-WATER-500","qty":1,"rate":1}],"payments":[{"mode_of_payment":"Cash","amount":50}],"idempotency_key":"smoke-bad-'$RUN'"}')"
echo "close:        $(post "$C" serk_retail.api.pos.close_shift '{"pos_opening_entry":"'$OE'","counted":[{"mode_of_payment":"Cash","amount":357.5}],"idempotency_key":"smoke-close-'$RUN'"}')"
