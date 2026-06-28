"""
Collector for Taiwan Water Resources Agency (WRA) data.

Open API portal : https://opendata.wra.gov.tw/openapi/swagger/index.html
Key datasets    :
  - Real-time water level            (73c4c3de-4045-4765-abeb-89f9f9cd5ff0)
  - Reservoir daily operations        (51023e88-4c76-4dbc-bbb9-470da690d539)
  - Reservoir water conditions        (2be9044c-6e44-4856-aad5-dd108c2e6679)
  - Groundwater level annual stats    (f3ae2889-ccaf-45a3-a546-0edd8d9fd2da)
  - Water rights statistics           (03be73eb-5da8-45d4-87d9-4e78d476a843)
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import datetime

from aquascope.collectors.base import BaseCollector
from aquascope.schemas.groundwater import GroundwaterLevel
from aquascope.schemas.water_data import (
    DataSource,
    GeoLocation,
    ReservoirStatus,
    WaterLevelReading,
)
from aquascope.utils.http_client import CachedHTTPClient, RateLimiter

logger = logging.getLogger(__name__)

# WRA encodes "no data" as large negative sentinels (e.g. -999998). Any value
# at or below this magnitude is missing, not a real groundwater level.
_GW_SENTINEL_THRESHOLD = -9999.0

# Annual statistic -> field name in the WRA annual-groundwater dataset.
_GW_STATISTIC_FIELDS = {
    "average": "annualaveragewaterlevel",
    "maximum": "annualmaximumdailywaterlevel",
    "minimum": "annualminimumdailywaterlevel",
}


def _parse_gw_value(raw: object) -> float | None:
    """Parse a WRA groundwater value, returning None for missing/sentinel.

    Empty strings and the large-negative no-data sentinels (e.g. -999998)
    map to None so callers can decide how to represent missing data.
    """
    if raw is None or str(raw).strip() == "":
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if val <= _GW_SENTINEL_THRESHOLD:
        return None
    return val

# Coordinate field names seen across WRA dataset variants (TWD97 / WGS84).
_LAT_KEYS = ("Latitude", "latitude", "TWD97Lat", "lat", "LAT", "Y")
_LON_KEYS = ("Longitude", "longitude", "TWD97Lon", "lon", "LON", "X")


def _extract_location(rec: dict) -> GeoLocation | None:
    """Build a GeoLocation from whichever lat/lon keys the record carries.

    WRA's real-time level feed often omits coordinates (station metadata
    lives in a separate dataset), so this returns ``None`` when absent
    rather than dropping the reading.
    """
    lat = next((rec[k] for k in _LAT_KEYS if rec.get(k) not in (None, "")), None)
    lon = next((rec[k] for k in _LON_KEYS if rec.get(k) not in (None, "")), None)
    if lat is None or lon is None:
        return None
    try:
        return GeoLocation(latitude=float(lat), longitude=float(lon))
    except (ValueError, TypeError):
        return None

WRA_BASE = "https://opendata.wra.gov.tw/api/v2"

# ── Dataset UUIDs ────────────────────────────────────────────────────
WATER_LEVEL_DATASET = "73c4c3de-4045-4765-abeb-89f9f9cd5ff0"
RESERVOIR_DAILY_DATASET = "51023e88-4c76-4dbc-bbb9-470da690d539"
RESERVOIR_CONDITION_DATASET = "2be9044c-6e44-4856-aad5-dd108c2e6679"
GROUNDWATER_ANNUAL_DATASET = "f3ae2889-ccaf-45a3-a546-0edd8d9fd2da"


class TaiwanWRAWaterLevelCollector(BaseCollector):
    """
    Collect real-time water-level readings from WRA river stations.
    Updated every 10 minutes at source.
    """

    name = "taiwan_wra_water_level"

    def __init__(self, client: CachedHTTPClient | None = None):
        super().__init__(
            client
            or CachedHTTPClient(
                base_url=WRA_BASE,
                rate_limiter=RateLimiter(max_calls=15, period_seconds=60),
                cache_ttl_seconds=600,  # 10-min TTL to match update freq
                verify=False,
            )
        )

    def fetch_raw(self, **kwargs) -> list[dict]:
        data = self.client.get_json(WATER_LEVEL_DATASET)
        return data if isinstance(data, list) else data.get("responseData", data.get("records", []))

    def normalise(self, raw: list[dict]) -> Sequence[WaterLevelReading]:
        readings: list[WaterLevelReading] = []
        for rec in raw:
            try:
                level_str = (
                    rec.get("WaterLevel")
                    or rec.get("waterLevel")
                    or rec.get("waterlevel")
                )
                if not level_str or str(level_str).strip() in ("", "-", "--"):
                    continue

                readings.append(
                    WaterLevelReading(
                        source=DataSource.TAIWAN_WRA,
                        station_id=rec.get("StationIdentifier", rec.get("ST_NO", rec.get("stationid", "unknown"))),
                        station_name=rec.get("StationName", rec.get("observatoryidentifier")),
                        location=_extract_location(rec),
                        reading_datetime=datetime.fromisoformat(
                            rec.get("RecordTime", rec.get("recordTime", rec.get("datetime", "")))
                        ),
                        water_level=float(level_str),
                        unit="m",
                    )
                )
            except (ValueError, KeyError, TypeError) as exc:
                logger.debug("Skipping WRA record: %s", exc)
        return readings


class TaiwanWRAReservoirCollector(BaseCollector):
    """
    Collect daily reservoir operation data from WRA.
    """

    name = "taiwan_wra_reservoir"

    def __init__(self, client: CachedHTTPClient | None = None):
        super().__init__(
            client
            or CachedHTTPClient(
                base_url=WRA_BASE,
                rate_limiter=RateLimiter(max_calls=15, period_seconds=60),
                cache_ttl_seconds=3600,
                verify=False,
            )
        )

    def fetch_raw(self, **kwargs) -> list[dict]:
        data = self.client.get_json(RESERVOIR_DAILY_DATASET)
        return data if isinstance(data, list) else data.get("responseData", data.get("records", []))

    def normalise(self, raw: list[dict]) -> Sequence[ReservoirStatus]:
        records: list[ReservoirStatus] = []
        for rec in raw:
            try:
                def _float(key: str):
                    v = rec.get(key)
                    return float(v) if v and str(v).strip() not in ("", "-", "--") else None

                capacity = _float("capacity")
                nwlmax = _float("nwlmax")
                pct = round(capacity / nwlmax * 100, 1) if capacity is not None and nwlmax else None

                dt_str = rec.get("datetime", "")
                if not dt_str:
                    continue

                records.append(
                    ReservoirStatus(
                        source=DataSource.TAIWAN_WRA,
                        reservoir_name=rec.get("reservoirname", "unknown"),
                        date=datetime.fromisoformat(dt_str),
                        effective_capacity_m3=nwlmax,
                        current_storage_m3=capacity,
                        storage_percentage=pct,
                        inflow_cms=_float("inflow"),
                        outflow_cms=_float("outflow"),
                        water_level=_float("dwl"),
                    )
                )
            except (ValueError, KeyError, TypeError) as exc:
                logger.debug("Skipping reservoir record: %s", exc)
        return records


class TaiwanWRAGroundwaterCollector(BaseCollector):
    """Collect annual groundwater-level statistics from WRA.

    Source: WRA annual-groundwater dataset (``GROUNDWATER_ANNUAL_DATASET``),
    ~992 wells nationwide, one record per well per year (1992-present), with
    annual average / maximum-daily / minimum-daily water levels.

    Parameters
    ----------
    statistic : str
        Which annual statistic to emit as ``water_level_m``: ``"average"``
        (default), ``"maximum"``, or ``"minimum"``. Use ``"average"`` for
        trend analysis and ``"minimum"`` for drought-severity work.
    na_value : float | None
        How to represent missing values (WRA's ``-999998`` sentinels and
        empty fields). ``None`` (default) drops the record entirely, which is
        the safe choice for trend/drawdown analysis. Pass ``float("nan")`` to
        keep a placeholder year, or a number (e.g. ``0.0``) to substitute a
        constant — but note that substituting ``0`` injects a real-looking
        zero-elevation reading that will distort trend and drawdown results.
    """

    name = "taiwan_wra_groundwater"

    def __init__(
        self,
        statistic: str = "average",
        na_value: float | None = None,
        client: CachedHTTPClient | None = None,
    ):
        if statistic not in _GW_STATISTIC_FIELDS:
            raise ValueError(
                f"statistic must be one of {list(_GW_STATISTIC_FIELDS)}; got {statistic!r}."
            )
        super().__init__(
            client
            or CachedHTTPClient(
                base_url=WRA_BASE,
                rate_limiter=RateLimiter(max_calls=15, period_seconds=60),
                cache_ttl_seconds=86400,  # annual data: cache for a day
                verify=False,
            )
        )
        self.statistic = statistic
        self.na_value = na_value

    def fetch_raw(self, **kwargs) -> list[dict]:
        data = self.client.get_json(GROUNDWATER_ANNUAL_DATASET)
        return data if isinstance(data, list) else data.get("responseData", data.get("records", []))

    def normalise(self, raw: list[dict]) -> Sequence[GroundwaterLevel]:
        field = _GW_STATISTIC_FIELDS[self.statistic]
        readings: list[GroundwaterLevel] = []
        for rec in raw:
            try:
                well = rec.get("wellidentifier")
                year = rec.get("year")
                if not well or not year:
                    continue

                level = _parse_gw_value(rec.get(field))
                if level is None:
                    if self.na_value is None:
                        continue  # drop missing-data well-years
                    level = self.na_value

                readings.append(
                    GroundwaterLevel(
                        source=DataSource.TAIWAN_WRA,
                        station_id=str(well),
                        # Annual value: stamp mid-year as the series centroid.
                        measurement_datetime=datetime(int(year), 7, 1),
                        water_level_m=level,
                        unit="m",
                        location=_extract_location(rec),
                    )
                )
            except (ValueError, KeyError, TypeError) as exc:
                logger.debug("Skipping WRA groundwater record: %s", exc)
        return readings
