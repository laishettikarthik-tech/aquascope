"""Interoperability: AquaScope records -> xarray / GeoPandas.

AquaScope normalises every source into unified Pydantic records. This example
shows how to hand those records to the scientific-Python geo stack so they can
feed downstream tools (NeuralHydrology, the Pangeo stack, GIS).

Requires the interop extra:  pip install 'aquascope[interop]'

Run:  python examples/11_interop_xarray.py
"""

from __future__ import annotations

from datetime import datetime

from aquascope.io.interop import records_to_geodataframe, records_to_xarray
from aquascope.schemas.water_data import (
    DataSource,
    GeoLocation,
    WaterQualitySample,
)


def demo_records() -> list[WaterQualitySample]:
    """A few synthetic samples (in practice these come from a collector)."""
    tamsui = GeoLocation(latitude=25.17, longitude=121.41)
    gaoping = GeoLocation(latitude=22.55, longitude=120.43)
    rows = [
        ("TAMSUI", datetime(2026, 1, 1), "DO", 8.5, tamsui),
        ("TAMSUI", datetime(2026, 1, 2), "DO", 8.1, tamsui),
        ("TAMSUI", datetime(2026, 1, 1), "pH", 7.3, tamsui),
        ("GAOPING", datetime(2026, 1, 1), "DO", 7.9, gaoping),
        ("GAOPING", datetime(2026, 1, 2), "DO", 7.6, gaoping),
    ]
    return [
        WaterQualitySample(
            source=DataSource.TAIWAN_MOENV,
            station_id=sid,
            sample_datetime=dt,
            parameter=param,
            value=val,
            unit="mg/l" if param == "DO" else "",
            location=loc,
        )
        for sid, dt, param, val, loc in rows
    ]


def main() -> None:
    records = demo_records()

    # 1. To xarray.Dataset: dims (time, station_id), one var per parameter,
    #    lat/lon station coords. Ready for the Pangeo / NeuralHydrology world.
    ds = records_to_xarray(records)
    print("=== xarray.Dataset ===")
    print(ds)
    print("\nDO at TAMSUI on 2026-01-01:",
          ds["DO"].sel(time=datetime(2026, 1, 1), station_id="TAMSUI").item())

    # 2. To geopandas.GeoDataFrame: one row per record, Point geometry (EPSG:4326).
    gdf = records_to_geodataframe(records)
    print("\n=== geopandas.GeoDataFrame ===")
    print(gdf[["station_id", "parameter", "value", "geometry"]])

    # 3. In real use, collectors emit these objects directly:
    #
    #     from aquascope.collectors import TaiwanMOENVCollector
    #     ds = TaiwanMOENVCollector().collect(as_xarray=True)
    #     gdf = TaiwanMOENVCollector().collect(as_geodataframe=True)


if __name__ == "__main__":
    main()
