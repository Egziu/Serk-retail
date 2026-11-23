# Copyright (c) 2026 SERK Technologies Group. GPL-3.0.
"""Small, dependency-light forecasting for retail series (numpy only).

Store revenue: Holt's linear trend on a weekday-deseasonalised daily series, smoothing
parameters chosen by one-step-ahead error on the history, with an empirical 80% interval and a
holdout backtest (MAPE) so the UI can state how accurate the model has been, not just predict.
Item demand: weekday-aware mean with Poisson-like dispersion, suited to sparse daily counts.

Pure functions: no database access, so they are unit-tested directly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

Z80 = 1.2816  # two-sided 80% interval
GRID = (0.1, 0.2, 0.3, 0.5, 0.7)
BETAS = (0.01, 0.05, 0.1, 0.2)


@dataclass
class Forecast:
	values: list[float]
	lower: list[float]
	upper: list[float]
	method: str
	mape: float | None  # backtest mean absolute percentage error (0.12 = 12%)
	trend_per_day: float
	weekday_index: list[float]  # Monday..Sunday multiplicative factors


def weekday_index(values: np.ndarray, weekdays: np.ndarray, min_weeks: int = 2) -> np.ndarray:
	"""Multiplicative weekday factors (Mon=0) normalised to mean 1; flat when history is short."""
	idx = np.ones(7)
	if len(values) < 7 * min_weeks or values.mean() <= 0:
		return idx
	overall = values.mean()
	for d in range(7):
		sel = values[weekdays == d]
		if len(sel):
			idx[d] = max(sel.mean() / overall, 0.05)
	return idx / idx.mean()


def _holt(y: np.ndarray, alpha: float, beta: float):
	level, trend = y[0], (y[min(len(y) - 1, 7)] - y[0]) / max(min(len(y) - 1, 7), 1)
	errors = []
	for t in range(1, len(y)):
		pred = level + trend
		errors.append(y[t] - pred)
		new_level = alpha * y[t] + (1 - alpha) * (level + trend)
		trend = beta * (new_level - level) + (1 - beta) * trend
		level = new_level
	return level, trend, np.asarray(errors)


def _fit(y: np.ndarray):
	best = None
	for a in GRID:
		for b in BETAS:
			level, trend, err = _holt(y, a, b)
			sse = float(np.mean(err[-min(len(err), 42):] ** 2)) if len(err) else 0.0
			if best is None or sse < best[0]:
				best = (sse, a, b, level, trend, err)
	return best


def forecast_daily(values, weekdays, horizon: int, start_weekday: int, damp: float = 0.98) -> Forecast:
	"""values: daily totals oldest..newest; weekdays: Mon=0 for each value;
	start_weekday: weekday of the first forecast day."""
	y = np.asarray(values, dtype=float)
	wd = np.asarray(weekdays, dtype=int)
	horizon = max(int(horizon), 0)
	if len(y) == 0:
		zeros = [0.0] * horizon
		return Forecast(zeros, zeros, zeros, "none", None, 0.0, [1.0] * 7)
	if len(y) < 14:
		m = float(y[-7:].mean())
		sd = float(y[-7:].std()) if len(y) > 1 else m * 0.3
		vals = [m] * horizon
		return Forecast(vals, [max(m - Z80 * sd, 0) for _ in vals], [m + Z80 * sd for _ in vals],
						"recent average", None, 0.0, [1.0] * 7)

	idx = weekday_index(y[-56:], wd[-56:])
	deseason = y / idx[wd]
	_sse, _alpha, _beta, level, trend, err = _fit(deseason)
	resid_sd = float(np.std(err[-42:])) if len(err) > 2 else float(deseason.std())

	values_out, lower, upper = [], [], []
	phi_sum = 0.0
	for h in range(1, horizon + 1):
		phi_sum += damp**h  # damped trend: long horizons do not extrapolate a short spurt
		base = level + phi_sum * trend
		factor = idx[(start_weekday + h - 1) % 7]
		point = max(base * factor, 0.0)
		spread = Z80 * resid_sd * math.sqrt(h) * factor
		values_out.append(round(point, 2))
		lower.append(round(max(point - spread, 0.0), 2))
		upper.append(round(point + spread, 2))

	return Forecast(values_out, lower, upper, "Holt trend + weekday seasonality",
					backtest_mape(y, wd), round(float(trend), 2), [round(float(v), 3) for v in idx])


def backtest_mape(y: np.ndarray, wd: np.ndarray, holdout: int = 14) -> float | None:
	"""Fit on all but the last `holdout` days, forecast them, report MAPE on non-zero days."""
	if len(y) < holdout + 21:
		return None
	train, test = y[:-holdout], y[-holdout:]
	fc = forecast_daily(train, wd[:-holdout], holdout, int(wd[-holdout]), damp=0.98) if len(train) >= 14 else None
	if not fc:
		return None
	pred = np.asarray(fc.values)
	mask = test > 0
	if not mask.any():
		return None
	return round(float(np.mean(np.abs(test[mask] - pred[mask]) / test[mask])), 4)


def item_demand(daily_qty, weekdays, horizon: int, start_weekday: int, store_index=None) -> dict:
	"""Expected demand for one item over the horizon, with an 80% upper bound for safety stock."""
	q = np.asarray(daily_qty, dtype=float)
	if len(q) == 0:
		return {"daily_mean": 0.0, "expected": 0.0, "upper80": 0.0, "daily_sd": 0.0}
	recent = q[-28:]
	mean = float(recent.mean())
	sd = float(recent.std()) if len(recent) > 1 else math.sqrt(max(mean, 0))
	sd = max(sd, math.sqrt(max(mean, 0)))  # at least Poisson dispersion
	idx = np.asarray(store_index if store_index is not None else [1.0] * 7)
	expected = sum(mean * idx[(start_weekday + h) % 7] for h in range(horizon))
	upper = expected + Z80 * sd * math.sqrt(max(horizon, 1))
	return {"daily_mean": round(mean, 3), "expected": round(expected, 2), "upper80": round(upper, 2),
			"daily_sd": round(sd, 3)}


def reorder_advice(on_hand: float, daily_mean: float, daily_sd: float, lead_time_days: int = 7,
				   review_days: int = 7, service_z: float = 1.65) -> dict:
	"""Days of cover, projected stock-out day and an order-up-to suggestion (95% service)."""
	if daily_mean <= 0:
		return {"days_of_cover": None, "stockout_in_days": None, "safety_stock": 0.0, "suggested_order": 0.0,
				"status": "no recent demand"}
	cover = on_hand / daily_mean if on_hand > 0 else 0.0
	exposure = lead_time_days + review_days
	safety = service_z * daily_sd * math.sqrt(exposure)
	target = daily_mean * exposure + safety
	order = max(target - max(on_hand, 0), 0.0)
	if cover <= lead_time_days:
		status = "critical"
	elif cover <= exposure:
		status = "reorder"
	elif cover > 90:
		status = "overstock"
	else:
		status = "healthy"
	return {"days_of_cover": round(cover, 1), "stockout_in_days": round(cover, 1), "safety_stock": round(safety, 2),
			"suggested_order": round(math.ceil(order), 0), "status": status}


def abc_classes(revenue_by_item: dict) -> dict:
	"""A = top 80% of revenue, B = next 15%, C = the rest."""
	total = sum(v for v in revenue_by_item.values() if v > 0)
	out, running = {}, 0.0
	for item, rev in sorted(revenue_by_item.items(), key=lambda kv: kv[1], reverse=True):
		share_before = running / total if total else 1
		out[item] = "A" if share_before < 0.80 else "B" if share_before < 0.95 else "C"
		running += max(rev, 0)
	return out


def zscores(values) -> list[float]:
	v = np.asarray(values, dtype=float)
	if len(v) < 3 or v.std() == 0:
		return [0.0] * len(v)
	return [round(float(x), 2) for x in (v - v.mean()) / v.std()]


def pair_lift(baskets: list[set], min_support_count: int = 5, top: int = 12) -> list[dict]:
	"""Market-basket affinity: item pairs bought together more often than chance (lift > 1)."""
	n = len(baskets)
	if n == 0:
		return []
	single: dict = {}
	pairs: dict = {}
	for b in baskets:
		items = sorted(b)
		for i in items:
			single[i] = single.get(i, 0) + 1
		for a_i in range(len(items)):
			for b_i in range(a_i + 1, len(items)):
				key = (items[a_i], items[b_i])
				pairs[key] = pairs.get(key, 0) + 1
	out = []
	for (a, b), c in pairs.items():
		if c < min_support_count:
			continue
		support = c / n
		lift = support / ((single[a] / n) * (single[b] / n))
		conf = c / single[a]
		out.append({"a": a, "b": b, "together": c, "support": round(support, 4), "confidence_a_to_b": round(conf, 3),
					"lift": round(lift, 2)})
	out.sort(key=lambda r: (r["lift"], r["together"]), reverse=True)
	return [r for r in out if r["lift"] > 1.05][:top]
