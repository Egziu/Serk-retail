// SERK Retail — Command Center: live KPIs, forecast, stock intelligence, basket science, AI analyst.
frappe.pages["serk-command-center"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Command Center"), single_column: true });
	wrapper.serk = new SerkCommandCenter(page, wrapper);
};
frappe.pages["serk-command-center"].on_page_show = function (wrapper) {
	wrapper.serk && wrapper.serk.ready && wrapper.serk.load();
};

class SerkCommandCenter {
	constructor(page, wrapper) {
		this.page = page;
		this.wrapper = wrapper;
		this.state = { company: null, days: 30, horizon: 14 };
		$(wrapper).find(".page-head").addClass("serk-hide-head");
		this.$root = $(`<div class="serk-cc"></div>`).appendTo(page.main);
		frappe.require("/assets/serk_retail/js/serk_ui.js", () => this.init());
	}

	async init() {
		const ui = (this.ui = window.serk_ui);
		const b = window.serk_brand || frappe.boot.serk_brand || {};
		const analyst = ["System Manager", "SERK Store Manager", "SERK Shift Supervisor"].some((r) => frappe.user.has_role(r));
		if (!analyst) return this.staffHome(b);
		this.$root.html(`
		<section class="serk-hero">
			<div class="serk-hero-grid" aria-hidden="true"></div>
			<div class="serk-hero-row">
				<div class="serk-hero-id">
					<img src="${ui.esc(b.logo_url)}" alt="" />
					<div><small>${ui.esc(b.display_name || b.product_name || "SERK Retail")}</small><h1>${__("Command Center")}</h1></div>
				</div>
				<div class="serk-hero-controls">
					<select class="serk-company"></select>
					<div class="serk-seg serk-days">${[7, 30, 90].map((d) => `<button data-v="${d}">${d}${__("d")}</button>`).join("")}</div>
					<div class="serk-seg serk-horizon">${[14, 30].map((d) => `<button data-v="${d}">+${d}${__("d")}</button>`).join("")}</div>
					<button class="serk-icon-btn serk-refresh" title="${__("Refresh")}">⟳</button>
				</div>
			</div>
			<div class="serk-hero-meta"><span class="live-dot"></span><span class="serk-asof">${__("Loading…")}</span><span class="serk-ai-chip"></span></div>
		</section>
		<section class="serk-kpis"></section>
		<section class="serk-grid">
			<article class="serk-card span-8"><header><div><h3>${__("Revenue & forecast")}</h3><small class="fc-sub"></small></div><div class="fc-badges"></div></header><div class="serk-fc-wrap"></div></article>
			<article class="serk-card span-4 serk-insights-card"><header><div><h3>${__("Insight feed")}</h3><small>${__("Rule-based, from your ledgers")}</small></div></header><div class="serk-insights"></div></article>
			<article class="serk-card span-6"><header><div><h3>${__("When customers buy")}</h3><small>${__("Average net revenue per hour, by weekday")}</small></div></header><div class="serk-heat-wrap"></div></article>
			<article class="serk-card span-6"><header><div><h3>${__("Category momentum")}</h3><small>${__("Share and growth vs previous window")}</small></div></header><div class="serk-cat"></div></article>
			<article class="serk-card span-7"><header><div><h3>${__("Product performance")}</h3><small>${__("ABC class, ledger margin and revenue share")}</small></div></header><div class="serk-products"></div></article>
			<article class="serk-card span-5"><header><div><h3>${__("Stock intelligence")}</h3><small>${__("Days of cover from forecast demand · 95% service")}</small></div></header><div class="serk-stock"></div></article>
			<article class="serk-card span-4"><header><div><h3>${__("Basket science")}</h3><small>${__("Bought together more than chance")}</small></div></header><div class="serk-aff"></div></article>
			<article class="serk-card span-4"><header><div><h3>${__("Registers")}</h3><small>${__("Throughput and basket")}</small></div></header><div class="serk-regs"></div></article>
			<article class="serk-card span-4"><header><div><h3>${__("Team & risk")}</h3><small>${__("Refund-rate outliers are flagged")}</small></div></header><div class="serk-team"></div></article>
			<article class="serk-card span-12 serk-ai-card"><div class="serk-ai-mount"></div></article>
		</section>`);

		const companies = (await frappe.xcall("serk_retail.api.insights.companies", {}, "GET")) || [];
		const $c = this.$root.find(".serk-company");
		$c.html(companies.map((c) => `<option value="${ui.esc(c.name)}">${ui.esc(c.name)}</option>`).join(""));
		const pref = frappe.defaults.get_user_default("Company");
		this.state.company = companies.some((c) => c.name === pref) ? pref : companies[0] && companies[0].name;
		$c.val(this.state.company).on("change", () => { this.state.company = $c.val(); this.load(); });
		const seg = (sel, key) => {
			const $s = this.$root.find(sel);
			$s.find("button").on("click", (e) => { this.state[key] = +e.currentTarget.dataset.v; this.load(); });
		};
		seg(".serk-days", "days");
		seg(".serk-horizon", "horizon");
		this.$root.find(".serk-refresh").on("click", () => this.load());
		this.ai = new ui.AIPanel(this.$root.find(".serk-ai-mount")[0], () => this.state);
		this.ready = true;
		if (!this.state.company) {
			this.$root.find(".serk-kpis").html(`<div class="serk-empty big">${__("No company yet.")} <a href="/app/serk-setup">${__("Set up your company")}</a></div>`);
			return;
		}
		this.load();
	}

	// Cashiers and receivers: a focused home with their registers and allowed actions.
	async staffHome(b) {
		const ui = this.ui;
		const regs = await frappe.db
			.get_list("POS Profile", { filters: [["POS Profile User", "user", "=", frappe.session.user]], fields: ["name as parent"], limit: 20 })
			.catch(() => []);
		const cashier = frappe.user.has_role("SERK Cashier");
		const actions = cashier
			? [[__("Shifts"), "/app/pos-opening-entry"], [__("Sales & returns"), "/app/sales-invoice"], [__("Shift closing"), "/app/pos-closing-entry"]]
			: [[__("Goods received"), "/app/purchase-receipt"], [__("Products"), "/app/item"]];
		this.$root.html(`
		<section class="serk-hero">
			<div class="serk-hero-grid" aria-hidden="true"></div>
			<div class="serk-hero-row"><div class="serk-hero-id"><img src="${ui.esc(b.logo_url)}" alt="" />
				<div><small>${ui.esc(b.display_name || b.product_name)}</small><h1>${__("Welcome, {0}", [ui.esc(frappe.session.user_fullname || "")])}</h1></div></div></div>
			<div class="serk-hero-meta"><span class="live-dot"></span><span>${cashier ? __("Cashier workspace") : __("Receiving workspace")}</span></div>
		</section>
		<section class="serk-grid">
			<article class="serk-card span-6"><header><div><h3>${__("Your registers")}</h3><small>${__("Assigned by your store manager")}</small></div></header>
				<div class="serk-list">${regs.length ? regs.map((r) => `<div class="serk-list-row"><b>${ui.esc(r.parent)}</b></div>`).join("") : `<div class="serk-empty">${__("No register assigned")}</div>`}</div></article>
			<article class="serk-card span-6"><header><div><h3>${__("Quick actions")}</h3><small>${__("Sales and returns go through the SERK checkout API")}</small></div></header>
				<div class="serk-list">${actions.map(([l, u]) => `<a class="serk-list-row" href="${u}"><b>${l} →</b></a>`).join("")}</div></article>
		</section>`);
	}

	setSeg() {
		this.$root.find(".serk-days button").each((_, b) => b.classList.toggle("active", +b.dataset.v === this.state.days));
		this.$root.find(".serk-horizon button").each((_, b) => b.classList.toggle("active", +b.dataset.v === this.state.horizon));
	}

	load() {
		if (!this.state.company) return;
		this.setSeg();
		this.$root.addClass("loading");
		frappe.call({
			method: "serk_retail.api.insights.dashboard",
			type: "GET",
			args: this.state,
			callback: (r) => {
				this.$root.removeClass("loading");
				if (r.message) this.render(r.message);
			},
			error: () => this.$root.removeClass("loading"),
		});
	}

	render(d) {
		const ui = this.ui, cur = d.meta.currency, k = d.kpis, col = ui.palette();
		this.data = d;
		this.$root.find(".serk-asof").text(
			`${__("Live")} · ${frappe.datetime.str_to_user(d.meta.from)} – ${frappe.datetime.str_to_user(d.meta.to)} · ${d.meta.invoices_in_window} ${__("invoices")} · ${__("updated")} ${frappe.datetime.str_to_user(d.meta.generated_at).slice(-8, -3)}`
		);
		this.$root.find(".serk-ai-chip").html(d.ai.available ? `<b>AI</b> ${ui.esc(d.ai.model)}` : `<b>AI</b> ${__("off")}`).toggleClass("off", !d.ai.available);

		const daily = d.daily.map((x) => x.revenue);
		const tx = d.daily.map((x) => x.transactions);
		const tiles = [
			[__("Net revenue"), ui.money(k.revenue, cur, true), ui.delta(k.revenue_change_pct), daily, col[0]],
			[__("Transactions"), ui.num(k.transactions), ui.delta(k.transactions_change_pct), tx, col[3] || col[0]],
			[__("Average basket"), ui.money(k.avg_basket, cur), ui.delta(k.avg_basket_change_pct), null, col[1]],
			[__("Gross margin"), k.gross_margin_pct == null ? "—" : `${k.gross_margin_pct}%`, ui.delta(k.gross_margin_change_pts, " pts"), null, col[2] || col[0]],
			[__("Units per basket"), ui.num(k.items_per_basket, 2), `<span class="serk-delta flat">${ui.num(k.units)} ${__("units")}</span>`, null, col[4] || col[0]],
			[__("Returns rate"), `${ui.num(k.returns_rate_pct, 2)}%`, `<span class="serk-delta ${k.returns_rate_pct > 3 ? "down" : "flat"}">${ui.money(k.refund_amount, cur, true)} ${__("refunded")}</span>`, null, col[5] || col[0]],
		];
		const $k = this.$root.find(".serk-kpis").empty();
		tiles.forEach(([label, value, dlt, spark, c]) => {
			const $t = $(`<div class="serk-kpi"><span class="lbl">${label}</span><b class="val">${ui.esc(value)}</b><div class="foot">${dlt}</div><div class="spark"></div></div>`);
			if (spark) $t.find(".spark")[0].appendChild(ui.sparkline(spark, c));
			$t.css("--kpi-accent", c);
			$k.append($t);
		});

		const f = d.forecast;
		this.$root.find(".fc-sub").text(`${f.method}`);
		this.$root.find(".fc-badges").html(
			`<span class="serk-badge">${__("Next 7d")} <b>${ui.esc(ui.money(f.next7_total, cur, true))}</b></span>` +
			`<span class="serk-badge">+${d.meta.horizon}${__("d")} <b>${ui.esc(ui.money(f.next_horizon_total, cur, true))}</b></span>` +
			(f.backtest_mape_pct != null ? `<span class="serk-badge acc" title="${__("Mean absolute % error when the model forecast the last 14 days it had not seen")}">${__("Accuracy")} <b>${(100 - f.backtest_mape_pct).toFixed(1)}%</b></span>` : "")
		);
		ui.forecastChart(this.$root.find(".serk-fc-wrap")[0], d.daily, f, cur);

		const sev = { good: "good", info: "info", warn: "warn", danger: "danger" };
		this.$root.find(".serk-insights").html(
			d.insights.length
				? d.insights.map((i) => `<div class="serk-insight ${sev[i.severity] || "info"}"><b>${ui.esc(i.title)}</b><p>${ui.esc(i.detail)}</p></div>`).join("")
				: `<div class="serk-empty">${__("Insights appear once there are sales in this window.")}</div>`
		);

		ui.heatmap(this.$root.find(".serk-heat-wrap")[0], d.heatmap, cur);
		const top = d.categories.slice(0, 6);
		const $cat = this.$root.find(".serk-cat").html(`<div class="serk-cat-row"><div class="serk-donut-wrap"></div><div class="serk-cat-bars"></div></div>`);
		ui.donut($cat.find(".serk-donut-wrap")[0], top.map((c) => ({ label: c.group, value: c.revenue, display: `${c.share_pct}%` })),
			ui.money(k.revenue, cur, true), __("net revenue"));
		ui.hbars($cat.find(".serk-cat-bars")[0], top.map((c) => ({
			label: c.group, value: c.revenue, display: ui.money(c.revenue, cur, true),
			chip: c.growth_pct == null ? `<em class="chip new">${__("new")}</em>` : `<em class="chip ${c.growth_pct >= 0 ? "up" : "down"}">${c.growth_pct >= 0 ? "+" : ""}${c.growth_pct}%</em>`,
		})));

		this.$root.find(".serk-products").html(this.table(
			[__("Product"), __("Class"), __("Units"), __("Revenue"), __("Margin"), __("Share")],
			d.top_items.slice(0, 10).map((i) => [
				`<b>${ui.esc(i.item_name)}</b><small>${ui.esc(i.item_group || "")}</small>`,
				`<span class="abc abc-${i.abc}">${i.abc}</span>`,
				ui.num(i.qty, i.qty % 1 ? 1 : 0),
				ui.money(i.revenue, cur),
				i.margin_pct == null ? "—" : `<span class="${i.margin_pct < 10 ? "neg" : ""}">${i.margin_pct}%</span>`,
				`<div class="share"><i style="width:${Math.min(i.share_pct * 2.5, 100)}%"></i><span>${i.share_pct}%</span></div>`,
			])
		));

		const st = d.stock.filter((s) => s.status !== "no recent demand").slice(0, 8);
		this.$root.find(".serk-stock").html(
			st.length ? st.map((s) => {
				const cover = s.days_of_cover == null ? 0 : Math.min(s.days_of_cover / 30, 1);
				return `<div class="serk-stock-row ${s.status}">
					<div class="nm"><b>${ui.esc(s.item_name)}</b><small>${ui.num(s.on_hand, s.on_hand % 1 ? 1 : 0)} ${ui.esc(s.uom || "")} ${__("on hand")} · ${ui.num(s.demand_daily, 1)}/${__("day")}</small></div>
					<div class="gauge"><i style="width:${(cover * 100).toFixed(0)}%"></i></div>
					<div class="dc"><b>${s.days_of_cover == null ? "—" : ui.num(s.days_of_cover, 1)}</b><small>${__("days")}</small></div>
					<div class="act">${s.suggested_order ? `${__("Order")} <b>${ui.num(s.suggested_order)}</b>` : `<span class="tag">${ui.esc(__(s.status))}</span>`}</div>
				</div>`;
			}).join("") : `<div class="serk-empty">${__("No stock signals yet.")}</div>`
		);

		this.$root.find(".serk-aff").html(
			d.affinity.length ? d.affinity.slice(0, 6).map((p) => `<div class="serk-pair">
				<div><b>${ui.esc(p.a_name)}</b><span>+</span><b>${ui.esc(p.b_name)}</b></div>
				<div class="lift"><b>${p.lift}×</b><small>${p.together} ${__("baskets")} · ${(p.confidence_a_to_b * 100).toFixed(0)}% ${__("attach")}</small></div>
			</div>`).join("") : `<div class="serk-empty">${__("Needs more multi-item baskets.")}</div>`
		);

		ui.hbars(this.$root.find(".serk-regs")[0], d.registers.map((r) => ({
			label: r.register, value: r.revenue, display: ui.money(r.revenue, cur, true),
			sub: `${r.transactions} ${__("transactions")} · ${__("basket")} ${ui.money(r.avg_basket, cur)}`,
		})), { color: col[3] || col[0] });

		this.$root.find(".serk-team").html(this.table(
			[__("Cashier"), __("Tx"), __("Basket"), __("Refunds")],
			d.cashiers.slice(0, 6).map((c) => [
				ui.esc(c.name), ui.num(c.transactions), ui.money(c.avg_basket, cur, true),
				`<span class="${c.refund_z >= 2 ? "flag" : ""}">${c.refund_rate_pct}%${c.refund_z >= 2 ? " ⚑" : ""}</span>`,
			])
		));

		this.ai.setStatus(d.ai);
	}

	table(head, rows) {
		if (!rows.length) return `<div class="serk-empty">${__("No data in this window")}</div>`;
		return `<table class="serk-table"><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows
			.map((r) => `<tr>${r.map((c) => `<td>${c}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
	}
}
