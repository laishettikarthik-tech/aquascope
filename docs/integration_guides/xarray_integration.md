# xarray and GeoPandas Integration Guide

Export AquaScope records to [xarray](https://docs.xarray.dev/) Datasets and
[GeoPandas](https://geopandas.org/) GeoDataFrames so they compose with the wider
scientific-Python ecosystem (the Pangeo stack, NeuralHydrology, GIS).

## Prerequisites

```bash
pip install "aquascope[interop]"   # installs xarray, geopandas, shapely
```

## Quick export to xarray

`records_to_xarray()` builds a Dataset with dimensions `(time, station_id)`, one
data variable per parameter, `lat`/`lon` station coordinates, and a `units`
attribute on each variable:

```python
from aquascope.collectors import TaiwanMOENVCollector
from aquascope.io.interop import records_to_xarray

records = TaiwanMOENVCollector(api_key="YOUR_KEY").collect()
ds = records_to_xarray(records)
print(ds)
# Dimensions:  (time, station_id); data variables: DO, pH, ...; coords lat/lon
```

Or get the Dataset straight from the collector:

```python
ds = TaiwanMOENVCollector(api_key="YOUR_KEY").collect(as_xarray=True)
```

`WaterQualitySample` records yield one variable per parameter; `WaterLevelReading`
records yield a single `water_level` variable. Stations without a known location
get `NaN` coordinates rather than being dropped.

## Quick export to GeoPandas

```python
from aquascope.io.interop import records_to_geodataframe

gdf = records_to_geodataframe(records)        # Point geometry, EPSG:4326
gdf.to_file("stations.gpkg")                  # straight into any GIS workflow

# or directly:
gdf = TaiwanMOENVCollector().collect(as_geodataframe=True)
```

Records without a location keep a null geometry (the count is logged), so nothing
is silently lost.

## Adding CF metadata

```python
ds.attrs["title"] = "AquaScope Taiwan River Water Quality"
ds.attrs["Conventions"] = "CF-1.8"
ds["DO"].attrs["standard_name"] = "mass_concentration_of_oxygen_in_sea_water"
```

## Saving to NetCDF / Zarr

```python
ds.to_netcdf("taiwan_wq.nc", engine="netcdf4")
ds.to_zarr("taiwan_wq.zarr")                  # cloud-native, Dask-friendly
```

## Time-series resampling

```python
monthly = ds.resample(time="ME").mean()       # the time dim is named "time"
monthly["DO"].plot(col="station_id", col_wrap=4)
```

## Merging multiple sources

```python
from aquascope.collectors import USGSCollector

ds_tw = TaiwanMOENVCollector().collect(as_xarray=True)
ds_us = USGSCollector().collect(as_xarray=True)

combined = xr.concat(
    [ds_tw.expand_dims("source"), ds_us.expand_dims("source")],
    dim="source",
)
combined["source"] = ["taiwan_moenv", "usgs"]
```

## Tips

- Use `engine="h5netcdf"` for HDF5-backed files with large datasets.
- Open with `chunks={"time": 100}` to enable Dask-backed lazy loading.
- A runnable end-to-end demo lives in `examples/11_interop_xarray.py`.
