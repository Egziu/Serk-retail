// SERK Retail website/login branding. Reads public presentation values only (no secrets).
(function () {
	const HEX = /^#[0-9a-fA-F]{6}$/;
	const esc = (s) =>
		String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

	function applyColors(b) {
		const r = document.documentElement.style;
		if (HEX.test(b.primary_color || "")) r.setProperty("--serk-primary", b.primary_color);
		if (HEX.test(b.accent_color || "")) r.setProperty("--serk-accent", b.accent_color);
		if (HEX.test(b.sidebar_color || "")) r.setProperty("--serk-sidebar", b.sidebar_color);
		if (HEX.test(b.background_color || "")) r.setProperty("--serk-bg", b.background_color);
	}

	function loginPanel(b) {
		if (document.querySelector(".serk-login-panel")) return;
		const section = document.querySelector(".for-login") || document.querySelector(".login-content");
		if (!section) return;
		document.body.classList.add("serk-login");
		const panel = document.createElement("aside");
		panel.className = "serk-login-panel";
		panel.innerHTML = `
			<div class="serk-login-brand">
				<img src="${esc(b.logo_url)}" alt="" />
				<div><strong>${esc(b.display_name || b.product_name)}</strong><span>${esc(b.product_name)}</span></div>
			</div>
			<div class="serk-login-hero">
				<h1>${esc(b.login_tagline || "")}</h1>
				<ul>
					<li><span></span>Live command center for every store and register</li>
					<li><span></span>AI insight, demand forecasts and market analysis</li>
					<li><span></span>Idempotent, audited checkout on a trusted ledger</li>
				</ul>
			</div>
			<div class="serk-login-foot">${esc(b.motto || "")}</div>
			<div class="serk-login-grid" aria-hidden="true"></div>`;
		document.body.prepend(panel);
		const title = document.querySelector(".page-card-head h4, .login-content h4, .page-card-head .text-xl");
		if (title && /login|sign in/i.test(title.textContent)) title.textContent = "Sign in";
	}

	function run() {
		fetch("/api/method/serk_retail.branding.public_brand", { credentials: "same-origin" })
			.then((r) => (r.ok ? r.json() : null))
			.then((d) => {
				const b = (d && d.message) || {};
				applyColors(b);
				const path = window.location.pathname.replace(/\/+$/, "");
				if (path === "/login" || path === "/update-password") loginPanel(b);
			})
			.catch(() => {});
	}
	if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", run);
	else run();
})();
