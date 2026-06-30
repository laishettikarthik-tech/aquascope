"""Tests for the Standardized Precipitation Index."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from aquascope.climate.indices import spi as compute_spi


def _monthly_precip(n_years: int = 30, seed: int = 0) -> pd.Series:
    idx = pd.date_range("1990-01-01", periods=n_years * 12, freq="MS")
    rng = np.random.default_rng(seed)
    # Seasonal gamma-ish precip (wet summers), always non-negative.
    seasonal = 80 + 60 * np.sin(2 * np.pi * (np.arange(len(idx)) % 12) / 12)
    precip = rng.gamma(shape=2.0, scale=seasonal / 2.0)
    return pd.Series(precip, index=idx)


class TestSPI:
    def test_standard_normal_distribution(self):
        result = compute_spi(_monthly_precip(), scale=3)
        values = result.spi.dropna()
        assert abs(values.mean()) < 0.2
        assert 0.7 < values.std() < 1.3

    def test_dry_period_is_negative(self):
        precip = _monthly_precip()
        dry = (precip.index.year >= 2010) & (precip.index.year <= 2011)
        precip[dry] *= 0.1  # strong dry anomaly
        result = compute_spi(precip, scale=6)
        values = result.spi.dropna()
        dry_spi = values[values.index.year.isin([2010, 2011])]
        assert dry_spi.mean() < -0.8

    def test_scale_changes_output(self):
        precip = _monthly_precip()
        result3 = compute_spi(precip, scale=3)
        result12 = compute_spi(precip, scale=12)
        # Different accumulation -> different series (and SPI-12 starts later).
        assert result12.spi.dropna().index.min() > result3.spi.dropna().index.min()

    def test_bad_scale_raises(self):
        with pytest.raises(ValueError, match="scale"):
            compute_spi(_monthly_precip(), scale=0)

    def test_handles_zeros(self):
        precip = _monthly_precip()
        precip.iloc[::5] = 0.0  # inject dry months
        result = compute_spi(precip, scale=1)
        assert np.isfinite(result.spi.dropna()).all()
