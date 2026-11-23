// SERK Retail theme runtime: applies the company's brand (SERK Brand Settings) to the desk.
// Mirrors SERK Finance's BrandTheme: primary/sidebar colours with derived shades.
(function () {
	const HEX = /^#[0-9a-fA-F]{6}$/;
	const DEFAULTS = {
		primary_color: "#166453",
		accent_color: "#61AD98",
		sidebar_color: "#153335",
		background_color: "#F6F8F7",
		sidebar_style: "Dark",
		corner_style: "Rounded",
	};

	// Mix a colour toward white (amount > 0) or black (amount < 0).
	function shade(hex, amount) {
		const n = parseInt(hex.slice(1), 16);
		const t = amount > 0 ? 255 : 0;
		const ch = [n >> 16, (n >> 8) & 255, n & 255].map((c) =>
			Math.round(c + (t - c) * Math.abs(amount))
		);
		return "#" + ch.map((c) => c.toString(16).padStart(2, "0")).join("");
	}

	function apply(brand) {
		brand = Object.assign({}, DEFAULTS, brand || {});
		const pick = (k) => (HEX.test(brand[k] || "") ? brand[k] : DEFAULTS[k]);
		const primary = pick("primary_color");
		const accent = pick("accent_color");
		const sidebar = pick("sidebar_color");
		const bg = pick("background_color");
		const root = document.documentElement;
		const set = (k, v) => root.style.setProperty(k, v);
		set("--serk-primary", primary);
		set("--serk-primary-dark", shade(primary, -0.22));
		set("--serk-primary-soft", shade(primary, 0.9));
		set("--serk-primary-softer", shade(primary, 0.95));
		set("--serk-accent", accent);
		set("--serk-accent-soft", shade(accent, 0.82));
		set("--serk-sidebar", sidebar);
		set("--serk-sidebar-2", shade(sidebar, 0.06));
		set("--serk-sidebar-3", shade(sidebar, 0.14));
		set("--serk-sidebar-line", shade(sidebar, 0.2));
		set("--serk-bg", bg);
		const radius = { Rounded: "10px", Soft: "16px", Sharp: "4px" }[brand.corner_style] || "10px";
		set("--serk-radius", radius);
		root.classList.toggle("serk-sidebar-dark", brand.sidebar_style !== "Light");
		root.classList.add("serk-theme");
		const meta = document.querySelector('meta[name="theme-color"]');
		if (meta) meta.setAttribute("content", sidebar);
		if (brand.favicon_url) {
			document.querySelectorAll('link[rel~="icon"]').forEach((l) => (l.href = brand.favicon_url));
		}
		window.serk_brand = brand;
	}

	window.serk_apply_brand = apply;
	window.serk_shade = shade;
	const boot = (window.frappe && frappe.boot && frappe.boot.serk_brand) || null;
	apply(boot);
	if (window.$) {
		$(document).on("app_ready", () => apply(frappe.boot && frappe.boot.serk_brand));
	}
	// Browser tab titles: "<page> · <product>" instead of the framework default.
	if (window.frappe && frappe.utils && !frappe._serk_title_patched) {
		frappe._serk_title_patched = true;
		const product = (boot && boot.product_name) || "SERK Retail";
		const original = frappe.utils.set_title;
		frappe.utils.set_title = function (title) {
			const t = title && !String(title).includes(product) ? `${title} · ${product}` : title || product;
			return original ? original.call(this, t) : (document.title = t);
		};
	}
})();
