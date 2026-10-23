"""Explicitly different *descriptive* and *signal-selected* group estimands.

The descriptive policy conditions on later observed outcomes; the signal policy
never does. Do not compare their constituents as if they were the same cohort.
"""
from __future__ import annotations
import numpy as np
import pandas as pd


def rank_bins(frame: pd.DataFrame, factor: str, quantiles: int = 5,
              policy: str = "signal") -> pd.DataFrame:
    if policy not in {"signal", "complete_case"}:
        raise ValueError("policy must be 'signal' or 'complete_case'")
    if quantiles < 2:
        raise ValueError("quantiles must be >= 2")
    need = {"symbol", factor, "future_price_return"}
    if not need.issubset(frame.columns):
        raise ValueError(f"missing columns: {sorted(need-set(frame.columns))}")
    x = frame.replace([np.inf, -np.inf], np.nan).dropna(subset=[factor]).copy()
    if policy == "complete_case":
        x = x.dropna(subset=["future_price_return"])
    x = x.sort_values([factor, "symbol"]).reset_index(drop=True)
    if x.empty:
        x["bin"] = pd.Series(dtype=int)
        return x
    bins = min(quantiles, len(x))
    x["bin"] = np.arange(len(x)) * bins // len(x) + 1
    return x
