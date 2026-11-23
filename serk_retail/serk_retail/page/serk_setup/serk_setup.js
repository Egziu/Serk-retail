// SERK Retail — Company Setup: company, brand, stores, registers, staff and AI, like the rest of the SERK family.
frappe.pages["serk-setup"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Company Setup"), single_column: true });
	$(wrapper).find(".page-head").addClass("serk-hide-head");
	wrapper.serk = new SerkSetup($(`<div class="serk-cc serk-setup"></div>`).appendTo(page.main));
};
frappe.pages["serk-setup"].on_page_show = function (wrapper) {
	wrapper.serk && wrapper.serk.ready && wrapper.serk.load();
};

class SerkSetup {
	constructor($root) {
		this.$root = $root;
		frappe.require("/assets/serk_retail/js/serk_ui.js", () => { this.ui = window.serk_ui; this.ready = true; this.load(); });
	}

	load() {
		frappe.xcall("serk_retail.api.setup.state", {}, "GET").then((s) => { this.s = s; this.render(); });
	}

	render() {
		const ui = this.ui, s = this.s, b = window.serk_brand || frappe.boot.serk_brand || {};
		const done = s.checklist.filter((c) => c.done).length, total = s.checklist.length;
		const pct = Math.round((done / total) * 100);
		this.$root.html(`
		<section class="serk-hero">
			<div class="serk-hero-grid" aria-hidden="true"></div>
			<div class="serk-hero-row">
				<div class="serk-hero-id"><img src="${ui.esc(b.logo_url)}" alt="" />
					<div><small>${ui.esc(b.product_name || "SERK Retail")}</small><h1>${__("Company Setup")}</h1></div></div>
				<div class="serk-ring" style="--p:${pct}"><b>${done}/${total}</b><small>${__("ready")}</small></div>
			</div>
			<ol class="serk-checklist">${s.checklist.map((c) => `<li class="${c.done ? "done" : ""}"><i>${c.done ? "✓" : ""}</i>${ui.esc(c.label)}</li>`).join("")}</ol>
		</section>
		<section class="serk-grid">
			${this.card("company", 6, __("Companies"), __("Legal entity, currency, fiscal year and VAT"), s.is_admin ? __("New company") : "",
				s.companies.map((c) => this.row(c.name, `${c.abbr} · ${c.default_currency} · ${c.country || ""}${c.tax_id ? " · TIN " + c.tax_id : ""}`)))}
			${this.card("brand", 6, __("Brand & theme"), __("Name, logo, colours — applied everywhere"), __("Customise"),
				[`<div class="serk-brand-preview">
					<div class="sw" style="background:${ui.esc(b.primary_color)}"></div><div class="sw" style="background:${ui.esc(b.accent_color)}"></div>
					<div class="sw" style="background:${ui.esc(b.sidebar_color)}"></div><div class="sw" style="background:${ui.esc(b.background_color)}"></div>
					<div><b>${ui.esc(b.display_name || b.product_name)}</b><small>${ui.esc(b.motto || "")}</small></div></div>`])}
			${this.card("store", 4, __("Stores"), __("Each store is a stock location"), __("Add store"),
				s.stores.map((w) => this.row(w.warehouse_name, w.company)))}
			${this.card("register", 4, __("Registers"), __("Tills with their cashiers, tax and price list"), __("Add register"),
				s.registers.map((r) => this.row(r.name, `${r.warehouse} · ${r.cashiers.length} ${__("cashier(s)")}${r.taxes_and_charges ? " · " + r.taxes_and_charges : ""}`)))}
			${this.card("staff", 4, __("Staff"), __("People with SERK roles"), s.is_admin ? __("Add person") : "",
				s.staff.map((u) => this.row(u.full_name || u.name, `${u.name} · ${u.roles}`)))}
			${this.card("ai", 12, __("AI analyst"), __("Anthropic or OpenAI — the same configuration as SERK Finance"), __("Configure"),
				[`<p class="serk-muted">${s.checklist.find((c) => c.key === "ai").done
					? __("Connected. Briefings, forecasts and market analysis are available in the Command Center and AI Analyst.")
					: __("Not connected yet. Set SERK_AI_API_KEY on the server or add a key in SERK AI Settings. Rule-based insights work without it.")}</p>`])}
		</section>`);
		this.$root.find("[data-act=company]").on("click", () => this.newCompany());
		this.$root.find("[data-act=brand]").on("click", () => frappe.set_route("Form", "SERK Brand Settings"));
		this.$root.find("[data-act=store]").on("click", () => this.newStore());
		this.$root.find("[data-act=register]").on("click", () => this.newRegister());
		this.$root.find("[data-act=staff]").on("click", () => this.newStaff());
		this.$root.find("[data-act=ai]").on("click", () => frappe.set_route("Form", "SERK AI Settings"));
	}

	card(key, span, title, sub, action, rows) {
		return `<article class="serk-card span-${span}"><header><div><h3>${title}</h3><small>${sub}</small></div>
			${action ? `<button class="btn btn-primary btn-sm" data-act="${key}">${action}</button>` : ""}</header>
			<div class="serk-list">${rows.length ? rows.join("") : `<div class="serk-empty">${__("Nothing yet")}</div>`}</div></article>`;
	}
	row(title, sub) {
		return `<div class="serk-list-row"><b>${this.ui.esc(title)}</b><small>${this.ui.esc(sub)}</small></div>`;
	}
	companies() { return this.s.companies.map((c) => c.name); }
	done(msg) { frappe.show_alert({ message: msg, indicator: "green" }); this.load(); }

	newCompany() {
		const d = new frappe.ui.Dialog({
			title: __("New company"), size: "large",
			fields: [
				{ fieldtype: "Section Break", label: __("Company") },
				{ fieldname: "company_name", label: __("Company name"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "abbr", label: __("Abbreviation"), fieldtype: "Data", reqd: 1, description: __("Short code, e.g. SDM") },
				{ fieldname: "legal_name", label: __("Legal name"), fieldtype: "Data" },
				{ fieldtype: "Column Break" },
				{ fieldname: "currency", label: __("Currency"), fieldtype: "Link", options: "Currency", default: "ETB", reqd: 1 },
				{ fieldname: "country", label: __("Country"), fieldtype: "Link", options: "Country", default: "Ethiopia", reqd: 1 },
				{ fieldname: "fiscal_calendar", label: __("Fiscal year"), fieldtype: "Select", options: ["Ethiopian (Hamle 1 – Sene 30)", "Gregorian (January – December)"], default: "Ethiopian (Hamle 1 – Sene 30)" },
				{ fieldtype: "Section Break", label: __("Tax") },
				{ fieldname: "tax_id", label: __("TIN"), fieldtype: "Data" },
				{ fieldname: "vat_registration", label: __("VAT registration no."), fieldtype: "Data" },
				{ fieldtype: "Column Break" },
				{ fieldname: "vat_rate", label: __("VAT rate %"), fieldtype: "Float", default: 15, description: __("0 for no VAT template. Confirm your tax treatment with your advisor.") },
				{ fieldtype: "Section Break", label: __("First store & identity") },
				{ fieldname: "first_store", label: __("First store"), fieldtype: "Data", default: "Main Store", reqd: 1 },
				{ fieldname: "motto", label: __("Motto"), fieldtype: "Data" },
				{ fieldname: "address", label: __("Address"), fieldtype: "Small Text" },
				{ fieldtype: "Column Break" },
				{ fieldname: "phone", label: __("Phone"), fieldtype: "Data" },
				{ fieldname: "email", label: __("Email"), fieldtype: "Data", options: "Email" },
				{ fieldname: "website", label: __("Website"), fieldtype: "Data" },
				{ fieldname: "set_as_brand", label: __("Use as the system brand"), fieldtype: "Check", default: 1 },
			],
			primary_action_label: __("Create company"),
			primary_action: (v) => {
				d.disable_primary_action();
				frappe.xcall("serk_retail.api.setup.create_company", v)
					.then((r) => { d.hide(); this.done(__("Company {0} is ready with store {1}", [r.company, r.store])); })
					.finally(() => d.enable_primary_action());
			},
		});
		d.show();
	}

	newStore() {
		const d = new frappe.ui.Dialog({
			title: __("Add store"),
			fields: [
				{ fieldname: "company", label: __("Company"), fieldtype: "Select", options: this.companies(), reqd: 1, default: this.companies()[0] },
				{ fieldname: "store_name", label: __("Store name"), fieldtype: "Data", reqd: 1, description: __("e.g. Mekelle Kebele 14") },
			],
			primary_action_label: __("Add store"),
			primary_action: (v) => frappe.xcall("serk_retail.api.setup.create_store", v).then((r) => { d.hide(); this.done(__("Store {0} added", [r.warehouse])); }),
		});
		d.show();
	}

	newRegister() {
		const s = this.s;
		const storesFor = (c) => s.stores.filter((w) => w.company === c).map((w) => w.name);
		const taxesFor = (c) => [""].concat(s.taxes.filter((t) => t.company === c).map((t) => t.name));
		const cashierOptions = s.staff.map((u) => ({ label: u.full_name || u.name, value: u.name }));
		const first = this.companies()[0];
		const d = new frappe.ui.Dialog({
			title: __("Add register"),
			fields: [
				{ fieldname: "company", label: __("Company"), fieldtype: "Select", options: this.companies(), default: first, reqd: 1,
					onchange: () => { const c = d.get_value("company"); d.set_df_property("warehouse", "options", storesFor(c)); d.set_df_property("tax_template", "options", taxesFor(c)); } },
				{ fieldname: "warehouse", label: __("Store"), fieldtype: "Select", options: storesFor(first), reqd: 1 },
				{ fieldname: "register_name", label: __("Register name"), fieldtype: "Data", reqd: 1, description: __("Unique, e.g. MKL Lane 3") },
				{ fieldname: "tax_template", label: __("Tax template"), fieldtype: "Select", options: taxesFor(first) },
				{ fieldname: "rounding", label: __("Cash rounding"), fieldtype: "Select", options: ["Exact", "Round to whole"], default: "Exact" },
				{ fieldname: "cashiers", label: __("Cashiers"), fieldtype: "MultiCheck", options: cashierOptions, columns: 2 },
			],
			primary_action_label: __("Add register"),
			primary_action: (v) => frappe.xcall("serk_retail.api.setup.create_register", v).then((r) => { d.hide(); this.done(__("Register {0} added", [r.register])); }),
		});
		d.show();
	}

	newStaff() {
		const d = new frappe.ui.Dialog({
			title: __("Add person"),
			fields: [
				{ fieldname: "full_name", label: __("Full name"), fieldtype: "Data", reqd: 1 },
				{ fieldname: "email", label: __("Email (login)"), fieldtype: "Data", options: "Email", reqd: 1 },
				{ fieldname: "role", label: __("Role"), fieldtype: "Select", options: this.s.role_options, default: "Cashier", reqd: 1 },
				{ fieldname: "registers", label: __("Registers"), fieldtype: "MultiCheck", options: this.s.registers.map((r) => ({ label: r.name, value: r.name })), columns: 2 },
			],
			primary_action_label: __("Create login"),
			primary_action: (v) => frappe.xcall("serk_retail.api.setup.create_staff", v).then((r) => {
				d.hide();
				const ui = this.ui;
				frappe.msgprint({
					title: __("Login created — shown once"),
					indicator: "green",
					message: `<p>${__("Give these details to {0} privately. They should change the password after signing in.", [ui.esc(r.user)])}</p>
						<table class="serk-table"><tr><td>${__("Username")}</td><td><b>${ui.esc(r.user)}</b></td></tr>
						<tr><td>${__("Temporary password")}</td><td><code>${ui.esc(r.temporary_password)}</code></td></tr>
						<tr><td>${__("Role")}</td><td>${ui.esc(r.role)}</td></tr></table>`,
				});
				this.load();
			}),
		});
		d.show();
	}
}
