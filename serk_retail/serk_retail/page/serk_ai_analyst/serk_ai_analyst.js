// SERK Retail — AI Analyst: full-screen briefings, demand plan, market analysis and Q&A.
frappe.pages["serk-ai-analyst"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("AI Analyst"), single_column: true });
	$(wrapper).find(".page-head").addClass("serk-hide-head");
	const state = { company: null, days: 30, horizon: 14 };
	const $root = $(`<div class="serk-cc serk-ai-page"></div>`).appendTo(page.main);
	frappe.require("/assets/serk_retail/js/serk_ui.js", async () => {
		const ui = window.serk_ui;
		const b = window.serk_brand || frappe.boot.serk_brand || {};
		$root.html(`
			<section class="serk-hero compact">
				<div class="serk-hero-grid" aria-hidden="true"></div>
				<div class="serk-hero-row">
					<div class="serk-hero-id"><img src="${ui.esc(b.logo_url)}" alt="" />
						<div><small>${ui.esc(b.display_name || b.product_name)}</small><h1>${__("AI Analyst")}</h1></div></div>
					<div class="serk-hero-controls">
						<select class="serk-company"></select>
						<div class="serk-seg serk-days">${[7, 30, 90].map((d) => `<button data-v="${d}">${d}${__("d")}</button>`).join("")}</div>
					</div>
				</div>
				<div class="serk-hero-meta"><span class="live-dot"></span><span>${__("Insight · Prediction · Market analysis — grounded in your own ledgers")}</span></div>
			</section>
			<section class="serk-grid"><article class="serk-card span-12 serk-ai-card tall"><div class="serk-ai-mount"></div></article></section>`);
		const companies = (await frappe.xcall("serk_retail.api.insights.companies", {}, "GET")) || [];
		const $c = $root.find(".serk-company").html(companies.map((c) => `<option>${ui.esc(c.name)}</option>`).join(""));
		state.company = companies[0] && companies[0].name;
		const panel = new ui.AIPanel($root.find(".serk-ai-mount")[0], () => state);
		const refresh = () => {
			$root.find(".serk-days button").each((_, x) => x.classList.toggle("active", +x.dataset.v === state.days));
			frappe.xcall("serk_retail.api.insights.dashboard", state, "GET").then((d) => panel.setStatus(d.ai));
		};
		$c.on("change", () => { state.company = $c.val(); refresh(); });
		$root.find(".serk-days button").on("click", (e) => { state.days = +e.currentTarget.dataset.v; refresh(); });
		if (state.company) refresh();
	});
};
