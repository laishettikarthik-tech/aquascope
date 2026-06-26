"""
Abstract base class for all data collectors.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from aquascope.utils.http_client import CachedHTTPClient

logger = logging.getLogger(__name__)


class BaseCollector(ABC):
    """
    Every collector must implement ``fetch_raw`` and ``normalise``.

    The public entry-point is ``collect()`` which chains those two steps.
    """

    name: str = "base"

    def __init__(self, client: CachedHTTPClient | None = None):
        self.client = client or CachedHTTPClient()

    @abstractmethod
    def fetch_raw(self, **kwargs) -> Any:
        """Fetch raw data from the upstream API."""

    @abstractmethod
    def normalise(self, raw: Any) -> Sequence[BaseModel]:
        """Convert raw API response into unified Pydantic records."""

    def collect(
        self,
        *,
        as_xarray: bool = False,
        as_geodataframe: bool = False,
        **kwargs,
    ) -> Any:
        """Fetch + normalise in one call.

        By default returns the list of unified Pydantic records. Set
        ``as_xarray=True`` to get an ``xarray.Dataset`` (time-series) or
        ``as_geodataframe=True`` to get a ``geopandas.GeoDataFrame`` (point
        geometry) instead — both require the ``interop`` extra. The two flags
        are mutually exclusive.
        """
        if as_xarray and as_geodataframe:
            raise ValueError("as_xarray and as_geodataframe are mutually exclusive.")
        logger.info("[%s] Starting collection …", self.name)
        raw = self.fetch_raw(**kwargs)
        records = self.normalise(raw)
        logger.info("[%s] Collected %d records.", self.name, len(records))
        if as_xarray:
            from aquascope.io.interop import records_to_xarray

            return records_to_xarray(records)
        if as_geodataframe:
            from aquascope.io.interop import records_to_geodataframe

            return records_to_geodataframe(records)
        return records
