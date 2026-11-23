// SERK Retail UI kit: SVG charts, formatting, safe markdown and the AI analyst panel.
// No external libraries; every string from the server is escaped before it reaches the DOM.
(function () {
	const NS = "http://www.w3.org/2000/svg";
	const esc = (s) =>
		String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
	const brand = () => window.serk_brand || (frappe.boot && frappe.boot.serk_brand) || {};
	const palette = () => (brand().chart_colors && brand().chart_colors.length ? brand().chart_colors : ["#166453", "#61AD98", "#E0A526", "#2F6FB5", "#C2553D", "#7A5AA6"]);
	const css = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;

	function money(v, cur, compact) {
		if (v == null || isNaN(v)) return "—";
		const n = Number(v);
		if (compact && Math.abs(n) >= 1000) {
			const units = [[1e9, "B"], [1e6, "M"], [1e3, "K"]];
			for (const [d, s] of units) if (Math.abs(n) >= d) return `${cur || ""} ${(n / d).toFixed(Math.abs(n) >= d * 10 ? 0 : 1)}${s}`.trim();
		}
		return `${cur || ""} ${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`.trim();
	}
	const num = (v, d = 0) => (v == null || isNaN(v) ? "—" : Number(v).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d }));
	function delta(v, suffix = "%", invert = false) {
		if (v == null || isNaN(v)) return `<span class="serk-delta flat">—</span>`;
		const good = invert ? v < 0 : v > 0;
		const cls = v === 0 ? "flat" : good ? "up" : "down";
		const arrow = v > 0 ? "▲" : v < 0 ? "▼" : "■";
		return `<span class="serk-delta ${cls}">${arrow} ${Math.abs(v).toFixed(1)}${suffix}</span>`;
	}

	function svg(w, h, cls) {
		const s = document.createElementNS(NS, "svg");
		s.setAttribute("viewBox", `0 0 ${w} ${h}`);
		s.setAttribute("preserveAspectRatio", "none");
		if (cls) s.setAttribute("class", cls);
		return s;
	}
	function node(parent, tag, attrs) {
		const n = document.createElementNS(NS, tag);
		for (const k in attrs || {}) n.setAttribute(k, attrs[k]);
		parent.appendChild(n);
		return n;
	}

	function sparkline(values, color) {
		const w = 120, h = 34, s = svg(w, h, "serk-spark");
		const v = (values || []).map(Number);
		if (v.length < 2) return s;
		const max = Math.max(...v), min = Math.min(...v), span = max - min || 1;
		const pts = v.map((y, i) => [(i / (v.length - 1)) * w, h - 3 - ((y - min) / span) * (h - 6)]);
		const d = pts.map((p, i) => (i ? "L" : "M") + p[0].toFixed(1) + " " + p[1].toFixed(1)).join(" ");
		const id = "sg" + Math.random().toString(36).slice(2);
		const defs = node(s, "defs");
		const g = node(defs, "linearGradient", { id, x1: 0, y1: 0, x2: 0, y2: 1 });
		node(g, "stop", { offset: "0", "stop-color": color, "stop-opacity": ".35" });
		node(g, "stop", { offset: "1", "stop-color": color, "stop-opacity": "0" });
		node(s, "path", { d: d + ` L${w} ${h} L0 ${h} Z`, fill: `url(#${id})` });
		node(s, "path", { d, fill: "none", stroke: color, "stroke-width": 1.8, "vector-effect": "non-scaling-stroke" });
		return s;
	}

	// Actual daily revenue + forecast with 80% band, today marker and hover readout.
	function forecastChart(el, daily, fc, cur) {
		el.innerHTML = "";
		const [c1, c2] = palette();
		const w = 900, h = 280, pl = 56, pr = 14, pt = 16, pb = 30;
		const actual = daily.map((d) => ({ x: d.date, y: d.revenue }));
		const fut = (fc.dates || []).map((d, i) => ({ x: d, y: fc.values[i], lo: fc.lower[i], hi: fc.upper[i] }));
		const all = actual.concat(fut);
		if (!all.length) { el.innerHTML = `<div class="serk-empty">No sales yet</div>`; return; }
		const maxY = Math.max(1, ...actual.map((p) => p.y), ...fut.map((p) => p.hi)) * 1.08;
		const X = (i) => pl + (i / Math.max(all.length - 1, 1)) * (w - pl - pr);
		const Y = (v) => pt + (1 - v / maxY) * (h - pt - pb);
		const s = svg(w, h, "serk-fc");
		const defs = node(s, "defs");
		const g = node(defs, "linearGradient", { id: "serkArea", x1: 0, y1: 0, x2: 0, y2: 1 });
		node(g, "stop", { offset: "0", "stop-color": c1, "stop-opacity": ".32" });
		node(g, "stop", { offset: "1", "stop-color": c1, "stop-opacity": ".02" });
		for (let k = 0; k <= 4; k++) {
			const v = (maxY / 4) * k, y = Y(v);
			node(s, "line", { x1: pl, x2: w - pr, y1: y, y2: y, class: "grid" });
			const t = node(s, "text", { x: pl - 8, y: y + 4, "text-anchor": "end", class: "axis" });
			t.textContent = money(v, "", true);
		}
		const step = Math.ceil(all.length / 8);
		all.forEach((p, i) => {
			if (i % step === 0) {
				const t = node(s, "text", { x: X(i), y: h - 8, "text-anchor": "middle", class: "axis" });
				t.textContent = frappe.datetime.str_to_user(p.x).slice(0, 5);
			}
		});
		if (fut.length) {
			const off = actual.length - 1;
			const band = fut.map((p, i) => [X(off + 1 + i), Y(p.hi)]).concat(fut.map((p, i) => [X(off + 1 + i), Y(p.lo)]).reverse());
			const last = actual.length ? [[X(off), Y(actual[off].y)]] : [];
			node(s, "path", { d: "M" + last.concat(band).map((p) => p.join(" ")).join(" L") + " Z", class: "band", fill: c2 });
			const fl = (actual.length ? [[X(off), Y(actual[off].y)]] : []).concat(fut.map((p, i) => [X(off + 1 + i), Y(p.y)]));
			node(s, "path", { d: "M" + fl.map((p) => p.join(" ")).join(" L"), class: "fcline", stroke: c2 });
			const tx = X(off);
			node(s, "line", { x1: tx, x2: tx, y1: pt, y2: h - pb, class: "today" });
			const tl = node(s, "text", { x: tx + 6, y: pt + 10, class: "axis today-label" });
			tl.textContent = __("Forecast →");
		}
		if (actual.length) {
			const pts = actual.map((p, i) => [X(i), Y(p.y)]);
			node(s, "path", { d: "M" + pts.map((p) => p.join(" ")).join(" L") + ` L${X(actual.length - 1)} ${Y(0)} L${X(0)} ${Y(0)} Z`, fill: "url(#serkArea)" });
			node(s, "path", { d: "M" + pts.map((p) => p.join(" ")).join(" L"), class: "actual", stroke: c1 });
		}
		const cross = node(s, "line", { y1: pt, y2: h - pb, class: "cross", visibility: "hidden" });
		const dot = node(s, "circle", { r: 4.5, class: "dot", visibility: "hidden", fill: c1 });
		el.appendChild(s);
		const tip = document.createElement("div");
		tip.className = "serk-tip";
		el.appendChild(tip);
		s.addEventListener("mousemove", (e) => {
			const r = s.getBoundingClientRect();
			const xv = ((e.clientX - r.left) / r.width) * w;
			const i = Math.max(0, Math.min(all.length - 1, Math.round(((xv - pl) / (w - pl - pr)) * (all.length - 1))));
			const p = all[i];
			cross.setAttribute("x1", X(i)); cross.setAttribute("x2", X(i)); cross.setAttribute("visibility", "visible");
			dot.setAttribute("cx", X(i)); dot.setAttribute("cy", Y(p.y)); dot.setAttribute("visibility", "visible");
			dot.setAttribute("fill", i >= actual.length ? c2 : c1);
			const isF = i >= actual.length;
			tip.innerHTML = `<b>${esc(frappe.datetime.str_to_user(p.x))}</b><span>${isF ? __("Forecast") : __("Actual")}: ${esc(money(p.y, cur))}</span>` +
				(isF ? `<span class="muted">80%: ${esc(money(p.lo, cur, true))} – ${esc(money(p.hi, cur, true))}</span>` : "");
			tip.style.left = `${Math.min(r.width - 170, Math.max(0, (X(i) / w) * r.width + 10))}px`;
			tip.style.opacity = 1;
		});
		s.addEventListener("mouseleave", () => { tip.style.opacity = 0; cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); });
	}

	function heatmap(el, data, cur) {
		const hours = data.hours.filter((h) => h >= 6 && h <= 22);
		const vals = data.values.map((row) => hours.map((h) => row[h]));
		const max = Math.max(1, ...vals.flat());
		const color = palette()[0];
		let html = `<div class="serk-heat" style="grid-template-columns: 42px repeat(${hours.length}, 1fr)"><span></span>`;
		html += hours.map((h) => `<span class="hh">${h % 3 === 0 ? String(h).padStart(2, "0") : ""}</span>`).join("");
		data.weekdays.forEach((d, r) => {
			html += `<span class="hd">${esc(__(d))}</span>`;
			hours.forEach((h, c) => {
				const v = vals[r][c], a = v / max;
				html += `<span class="cell" title="${esc(__(d))} ${String(h).padStart(2, "0")}:00 · ${esc(money(v, cur))}" style="background:${color};opacity:${(0.06 + a * 0.94).toFixed(3)}"></span>`;
			});
		});
		el.innerHTML = html + "</div>";
	}

	function hbars(el, rows, opts = {}) {
		const max = Math.max(1, ...rows.map((r) => r.value));
		const color = opts.color || palette()[0];
		el.innerHTML = rows.length
			? rows.map((r) => `<div class="serk-hbar">
				<div class="lbl"><span>${esc(r.label)}</span>${r.chip || ""}</div>
				<div class="track"><i style="width:${((r.value / max) * 100).toFixed(1)}%;background:${r.color || color}"></i></div>
				<div class="val">${esc(r.display)}</div></div>`).join("")
			: `<div class="serk-empty">${__("No data in this window")}</div>`;
	}

	function donut(el, slices, centerTop, centerBottom) {
		const total = slices.reduce((a, s) => a + Math.max(s.value, 0), 0) || 1;
		const cols = palette();
		const s = svg(160, 160, "serk-donut");
		s.setAttribute("preserveAspectRatio", "xMidYMid meet");
		let a0 = -Math.PI / 2;
		slices.forEach((sl, i) => {
			const a1 = a0 + (Math.max(sl.value, 0) / total) * Math.PI * 2;
			const large = a1 - a0 > Math.PI ? 1 : 0;
			const R = 70, r = 46, cx = 80, cy = 80;
			const p = (a, rad) => [cx + rad * Math.cos(a), cy + rad * Math.sin(a)];
			const [x0, y0] = p(a0, R), [x1, y1] = p(a1, R), [x2, y2] = p(a1, r), [x3, y3] = p(a0, r);
			const path = node(s, "path", { d: `M${x0} ${y0} A${R} ${R} 0 ${large} 1 ${x1} ${y1} L${x2} ${y2} A${r} ${r} 0 ${large} 0 ${x3} ${y3} Z`, fill: cols[i % cols.length] });
			const t = document.createElementNS(NS, "title"); t.textContent = `${sl.label}: ${sl.display}`; path.appendChild(t);
			a0 = a1;
		});
		const t1 = node(s, "text", { x: 80, y: 78, "text-anchor": "middle", class: "dc-top" }); t1.textContent = centerTop || "";
		const t2 = node(s, "text", { x: 80, y: 96, "text-anchor": "middle", class: "dc-bottom" }); t2.textContent = centerBottom || "";
		el.innerHTML = "";
		el.appendChild(s);
		const legend = document.createElement("div");
		legend.className = "serk-legend";
		legend.innerHTML = slices.map((sl, i) => `<span><i style="background:${cols[i % cols.length]}"></i>${esc(sl.label)} <b>${esc(sl.display)}</b></span>`).join("");
		el.appendChild(legend);
	}

	// Minimal markdown → safe HTML (headings, bullets, numbered, bold, tables, paragraphs).
	function markdown(text) {
		const inline = (t) => esc(t).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>").replace(/`([^`]+)`/g, "<code>$1</code>");
		const lines = String(text || "").replace(/\r/g, "").split("\n");
		let out = "", i = 0;
		while (i < lines.length) {
			const l = lines[i];
			if (/^\s*\|.*\|\s*$/.test(l)) {
				const rows = [];
				while (i < lines.length && /^\s*\|.*\|\s*$/.test(lines[i])) {
					if (!/^\s*\|[\s:|-]+\|\s*$/.test(lines[i])) rows.push(lines[i].trim().slice(1, -1).split("|").map((c) => c.trim()));
					i++;
				}
				if (rows.length) {
					const [head, ...body] = rows;
					out += `<div class="serk-md-table"><table><thead><tr>${head.map((c) => `<th>${inline(c)}</th>`).join("")}</tr></thead><tbody>` +
						body.map((r) => `<tr>${r.map((c) => `<td>${inline(c)}</td>`).join("")}</tr>`).join("") + "</tbody></table></div>";
				}
				continue;
			}
			const hm = l.match(/^\s{0,3}(#{1,6})\s+(.*)$/);
			if (hm) { out += `<h${Math.min(hm[1].length + 2, 6)}>${inline(hm[2])}</h${Math.min(hm[1].length + 2, 6)}>`; i++; continue; }
			if (/^\s*([-*]|\d+\.)\s+/.test(l)) {
				const ordered = /^\s*\d+\./.test(l);
				const items = [];
				while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) items.push(lines[i++].replace(/^\s*([-*]|\d+\.)\s+/, ""));
				out += `<${ordered ? "ol" : "ul"}>${items.map((t) => `<li>${inline(t)}</li>`).join("")}</${ordered ? "ol" : "ul"}>`;
				continue;
			}
			if (!l.trim()) { i++; continue; }
			const para = [];
			while (i < lines.length && lines[i].trim() && !/^\s*(\||#{1,6}\s|[-*]\s|\d+\.\s)/.test(lines[i])) para.push(lines[i++]);
			out += `<p>${inline(para.join(" "))}</p>`;
		}
		return out;
	}

	// AI analyst panel: briefings + grounded Q&A over the current analytics window.
	class AIPanel {
		constructor(el, getContext) {
			this.el = el;
			this.ctx = getContext;
			this.history = [];
			this.render();
		}
		render() {
			this.el.innerHTML = `
			<div class="serk-ai">
				<div class="serk-ai-head">
					<div class="serk-ai-title"><span class="orb"></span><div><b>${__("SERK AI Analyst")}</b><small class="serk-ai-status">${__("Checking…")}</small></div></div>
					<div class="serk-ai-tabs">
						<button data-kind="insights" class="active">${__("Executive briefing")}</button>
						<button data-kind="forecast">${__("Forecast & demand plan")}</button>
						<button data-kind="market">${__("Market analysis")}</button>
						<button data-kind="ask">${__("Ask")}</button>
					</div>
				</div>
				<div class="serk-ai-body"><div class="serk-ai-out"></div>
					<form class="serk-ai-ask" hidden>
						<input type="text" maxlength="1200" placeholder="${__("e.g. Which items should I promote this weekend, and why?")}" />
						<button type="submit" class="btn btn-primary btn-sm">${__("Ask")}</button>
					</form>
				</div>
				<div class="serk-ai-foot">${__("Grounded in your aggregated sales, stock and margin figures only. Customer data is never sent; cashiers are anonymised. The AI advises — it cannot change anything.")}</div>
			</div>`;
			this.out = this.el.querySelector(".serk-ai-out");
			this.form = this.el.querySelector(".serk-ai-ask");
			this.el.querySelectorAll(".serk-ai-tabs button").forEach((b) =>
				b.addEventListener("click", () => {
					this.el.querySelectorAll(".serk-ai-tabs button").forEach((x) => x.classList.toggle("active", x === b));
					this.select(b.dataset.kind);
				})
			);
			this.form.addEventListener("submit", (e) => { e.preventDefault(); this.ask(); });
		}
		setStatus(st) {
			this.status = st || {};
			const el = this.el.querySelector(".serk-ai-status");
			el.textContent = st && st.available ? `${__("Online")} · ${st.model}` : __("Not configured");
			el.classList.toggle("off", !(st && st.available));
			this.select(this.kind || "insights");
		}
		notConfigured() {
			this.out.innerHTML = `<div class="serk-ai-setup"><b>${__("Connect an AI provider to unlock narrative briefings, forecasts and market analysis.")}</b>
				<p>${__("Set SERK_AI_API_KEY on the server (same as SERK Finance), or add a key in")} <a href="/app/serk-ai-settings">${__("SERK AI Settings")}</a>.
				${__("Until then, the rule-based insights on this page keep working.")}</p></div>`;
		}
		select(kind) {
			this.kind = kind;
			this.form.hidden = kind !== "ask";
			if (!(this.status && this.status.available)) return this.notConfigured();
			if (kind === "ask") return this.renderChat();
			this.brief(kind, false);
		}
		brief(kind, refresh) {
			const c = this.ctx();
			this.out.innerHTML = `<div class="serk-ai-loading"><span></span><span></span><span></span> ${__("Analysing your data…")}</div>`;
			frappe.call({
				method: "serk_retail.api.insights.ai_brief",
				args: { kind, company: c.company, days: c.days, horizon: c.horizon, refresh: refresh ? 1 : 0 },
				error: () => (this.out.innerHTML = `<div class="serk-empty">${__("The AI briefing failed. See the message above.")}</div>`),
				callback: (r) => {
					if (this.kind !== kind || !r.message) return;
					const m = r.message;
					this.out.innerHTML = `<div class="serk-md">${markdown(m.text)}</div>
						<div class="serk-ai-meta">${esc(m.provider)} · ${esc(m.model)} · ${esc(frappe.datetime.str_to_user(m.generated_at))}${m.cached ? " · " + __("cached") : ""}
						<a class="serk-ai-refresh">${__("Regenerate")}</a></div>`;
					this.out.querySelector(".serk-ai-refresh").addEventListener("click", () => this.brief(kind, true));
				},
			});
		}
		renderChat() {
			this.out.innerHTML = this.history.length
				? this.history.map((t) => `<div class="serk-chat ${t.role}">${t.role === "assistant" ? markdown(t.content) : esc(t.content)}</div>`).join("")
				: `<div class="serk-ai-suggest">${[
					__("Which products should I reorder before the weekend?"),
					__("Why did revenue change compared with last month?"),
					__("What bundle or promotion would lift the average basket?"),
					__("Where are we losing margin?"),
				].map((q) => `<button>${esc(q)}</button>`).join("")}</div>`;
			this.out.querySelectorAll(".serk-ai-suggest button").forEach((b) =>
				b.addEventListener("click", () => { this.form.querySelector("input").value = b.textContent; this.ask(); })
			);
		}
		ask() {
			const input = this.form.querySelector("input");
			const q = input.value.trim();
			if (!q) return;
			input.value = "";
			const prior = this.history.slice(-6);
			this.history.push({ role: "user", content: q });
			this.renderChat();
			this.out.insertAdjacentHTML("beforeend", `<div class="serk-ai-loading"><span></span><span></span><span></span> ${__("Thinking…")}</div>`);
			const c = this.ctx();
			frappe.call({
				method: "serk_retail.api.insights.ai_ask",
				args: { question: q, company: c.company, days: c.days, history: prior },
				error: () => { this.history.pop(); this.renderChat(); },
				callback: (r) => {
					if (r.message) this.history.push({ role: "assistant", content: r.message.text });
					this.renderChat();
					this.out.scrollTop = this.out.scrollHeight;
				},
			});
		}
	}

	window.serk_ui = { esc, money, num, delta, sparkline, forecastChart, heatmap, hbars, donut, markdown, AIPanel, palette, css };
})();
