# =============================================================================
# VerdaMap — Sentinel Hub Service
# =============================================================================
# Handles all communication with the Sentinel Hub Processing API.
#
# Flow for each analysis:
#   1. Get an OAuth2 access token from Sentinel Hub
#   2. Call the Statistics API to get NDVI numbers for the polygon
#   3. Call the Process API to get a rendered NDVI color image (PNG)
#   4. Return everything to the route handler
# =============================================================================

import httpx
import base64
import math
import numpy as np
from datetime import datetime, timezone
from typing import Optional
from app.config import get_settings

settings = get_settings()

# =============================================================================
# EVALSCRIPT
# This JavaScript snippet runs inside Sentinel Hub's servers.
# It receives the raw satellite bands and returns what we want.
#
# We request two outputs:
#   - "ndvi"  : raw float32 NDVI values (for statistics)
#   - "visual": colored PNG (for the map overlay)
# =============================================================================
NDVI_EVALSCRIPT = """
//VERSION=3
function setup() {
  return {
    input: [{
      bands: ["B04", "B08", "SCL"],
      units: ["REFLECTANCE", "REFLECTANCE", "DN"]
    }],
    output: [
      { id: "ndvi",     bands: 1, sampleType: "FLOAT32" },
      { id: "visual",   bands: 4, sampleType: "UINT8"   },
      { id: "dataMask", bands: 1, sampleType: "UINT8"   }
    ]
  };
}

// Map an NDVI value to an RGBA color
function ndviToColor(ndvi) {
  if (ndvi < 0.0)  return [26,  35, 126, 255];  // deep blue   — water
  if (ndvi < 0.1)  return [212,163,115, 255];    // tan         — bare soil
  if (ndvi < 0.3)  return [255,209,102, 255];    // yellow      — sparse
  if (ndvi < 0.6)  return [144,190,109, 255];    // light green — moderate
  return                  [27,  67,  50, 255];   // dark green  — healthy
}

function evaluatePixel(sample) {
  // SCL = Scene Classification Layer — used to mask clouds
  // SCL values 3 (cloud shadow), 8 (cloud medium), 9 (cloud high), 10 (thin cirrus)
  const isCloud = [3, 8, 9, 10].includes(sample.SCL);

  // dataMask: 1 = valid pixel, 0 = masked (cloud/no-data)
  const mask = isCloud ? 0 : 1;

  if (isCloud) {
    return {
      ndvi:     [NaN],
      visual:   [255, 255, 255, 0],
      dataMask: [0]
    };
  }

  const ndvi = (sample.B08 - sample.B04) / (sample.B08 + sample.B04 + 1e-10);
  const color = ndviToColor(ndvi);

  return {
    ndvi:     [ndvi],
    visual:   color,
    dataMask: [1]
  };
}
"""


class SentinelHubError(Exception):
    """Raised when Sentinel Hub returns an error."""
    pass


class SentinelHubService:
    """
    Async client for the Sentinel Hub API.
    Uses httpx.AsyncClient for non-blocking HTTP requests.
    """

    def __init__(self):
        self._token: Optional[str] = None
        self._token_expires_at: float = 0.0

    # ── Authentication ────────────────────────────────────────────────────────

    async def _get_token(self) -> str:
        """
        Returns a valid OAuth2 access token, refreshing it if expired.
        Sentinel Hub tokens last 10 minutes — we refresh 60s early.
        """
        now = datetime.now(timezone.utc).timestamp()
        if self._token and now < self._token_expires_at - 60:
            return self._token

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                settings.sentinelhub_token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": settings.sentinelhub_client_id,
                    "client_secret": settings.sentinelhub_client_secret,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        if response.status_code != 200:
            raise SentinelHubError(
                f"Failed to authenticate with Sentinel Hub: {response.text}"
            )

        data = response.json()
        self._token = data["access_token"]
        self._token_expires_at = now + data.get("expires_in", 600)
        return self._token

    def _auth_headers(self, token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    # ── Geometry helpers ──────────────────────────────────────────────────────

    @staticmethod
    def polygon_to_bbox(polygon: list[list[float]]) -> list[float]:
        """
        Compute [west, south, east, north] bounding box from polygon coordinates.
        polygon is a list of [lon, lat] pairs.
        """
        lons = [p[0] for p in polygon]
        lats = [p[1] for p in polygon]
        return [min(lons), min(lats), max(lons), max(lats)]

    @staticmethod
    def bbox_area_km2(bbox: list[float]) -> float:
        """
        Approximate area of a bounding box in km².
        Uses the haversine formula for accuracy near the equator.
        """
        west, south, east, north = bbox
        R = 6371.0
        lat_mid = math.radians((south + north) / 2)
        width_km = R * math.radians(east - west) * math.cos(lat_mid)
        height_km = R * math.radians(north - south)
        return abs(width_km * height_km)

    @staticmethod
    def polygon_area_km2(polygon: list[list[float]]) -> float:
        """
        Compute polygon area in km² using the Shoelace formula.
        More accurate than bbox area for irregular shapes.
        """
        R = 6371.0
        to_rad = math.radians
        area = 0.0
        n = len(polygon)
        for i in range(n - 1):
            lon1, lat1 = polygon[i]
            lon2, lat2 = polygon[i + 1]
            area += to_rad(lon2 - lon1) * (
                2 + math.sin(to_rad(lat1)) + math.sin(to_rad(lat2))
            )
        return abs((area * R * R) / 2)

    # ── Statistics API ────────────────────────────────────────────────────────

    async def get_ndvi_statistics(
        self,
        polygon: list[list[float]],
        date_from: str,
        date_to: str,
    ) -> dict:
        """
        Call the Sentinel Hub Statistical API to get NDVI numbers.
        """
        token = await self._get_token()

        geometry = {
            "type": "Polygon",
            "coordinates": [polygon],
        }

        payload = {
            "input": {
                "bounds": {
                    "geometry": geometry,
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
                },
                "data": [
                    {
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {
                                "from": f"{date_from}T00:00:00Z",
                                "to": f"{date_to}T23:59:59Z",
                            },
                            "maxCloudCoverage": 80,
                            "mosaickingOrder": "leastCC",
                        },
                    }
                ],
            },
            "aggregation": {
                "timeRange": {
                    "from": f"{date_from}T00:00:00Z",
                    "to": f"{date_to}T23:59:59Z",
                },
                "aggregationInterval": {"of": "P1D"},
                "evalscript": NDVI_EVALSCRIPT,
                "resx": 10,
                "resy": 10,
            },
            "calculations": {
                "ndvi": {
                    "histograms": {
                        "default": {
                            "nBins": 20,
                            "lowEdge": -1.0,
                            "highEdge": 1.0,
                        }
                    },
                    "statistics": {
                        "default": {}
                    },
                }
            },
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                settings.sentinelhub_statistics_url,
                json=payload,
                headers={**self._auth_headers(token), "Content-Type": "application/json"},
            )

        if response.status_code != 200:
            raise SentinelHubError(
                f"Statistics API error {response.status_code}: {response.text}"
            )

        raw = response.json()
        # Log the structure so we can see exactly what came back
        import json
        print("=== STATISTICS API RESPONSE ===")
        print(json.dumps(raw, indent=2)[:3000])  # first 3000 chars
        print("================================")

        return self._parse_statistics(raw)

    def _parse_statistics(self, data: dict) -> dict:
        """
        Extract the useful numbers from the Statistics API response.
        Picks the interval with the least cloud cover.
        """
        intervals = data.get("data", [])
        if not intervals:
            raise SentinelHubError(
                "No satellite imagery found for the selected area and date range. "
                "Try a wider date range or a different area."
            )

        # Find the first interval that has any output data at all
        valid = []
        for iv in intervals:
            outputs = iv.get("outputs", {})
            if outputs:
                valid.append(iv)

        if not valid:
            raise SentinelHubError(
                "No clear imagery found. The area may be fully cloud-covered. "
                "Try a wider date range."
            )

        # Pick the best interval — least no-data fraction
        def no_data_fraction(iv):
            try:
                # Walk whatever output/band structure exists
                outputs = iv.get("outputs", {})
                for out_name, out_val in outputs.items():
                    bands = out_val.get("bands", {})
                    for band_name, band_val in bands.items():
                        stats = band_val.get("stats", {})
                        total = stats.get("sampleCount", 1)
                        no_data = stats.get("noDataCount", 0)
                        return no_data / max(total, 1)
            except Exception:
                pass
            return 1.0

        best = min(valid, key=no_data_fraction)

        # Extract stats and histogram from whatever band is present
        outputs = best.get("outputs", {})

        # Try to find the ndvi output first, fall back to first available
        ndvi_output = outputs.get("ndvi") or next(iter(outputs.values()), {})
        bands = ndvi_output.get("bands", {})
        band_data = bands.get("B0") or next(iter(bands.values()), {})

        stats = band_data.get("stats", {})
        # histograms key may be at band level or output level
        histograms = band_data.get("histograms", {})
        histogram = histograms.get("default", {})

        ndvi_mean = stats.get("mean", 0.0)
        ndvi_min  = stats.get("min", -1.0)
        ndvi_max  = stats.get("max", 1.0)
        ndvi_std  = stats.get("stDev", 0.0)

        total   = stats.get("sampleCount", 1)
        no_data = stats.get("noDataCount", 0)
        cloud_cover = round((no_data / max(total, 1)) * 100, 1)

        date_acquired = best["interval"]["from"][:10]
        health_pct = self._histogram_to_health(histogram)

        def safe_float(val, default=0.0):
            """Replace NaN/Infinity with a safe default."""
            import math
            try:
                f = float(val)
                if math.isnan(f) or math.isinf(f):
                    return default
                return f
            except (TypeError, ValueError):
                return default

        return {
            "ndvi_mean":        round(safe_float(ndvi_mean, 0.0), 4),
            "ndvi_min":         round(safe_float(ndvi_min, -1.0), 4),
            "ndvi_max":         round(safe_float(ndvi_max,  1.0), 4),
            "ndvi_std":         round(safe_float(ndvi_std,  0.0), 4),
            "cloud_cover":      cloud_cover,
            "date_acquired":    date_acquired,
            "health_percentage": health_pct,
        }

    @staticmethod
    def _histogram_to_health(histogram: dict) -> dict:
        """
        Convert the NDVI histogram bins into health category percentages.

        NDVI ranges:
          < 0.0  → no_vegetation
          0.0–0.1 → sparse
          0.1–0.3 → stressed
          0.3–0.6 → moderate
          >= 0.6  → healthy
        """
        bins = histogram.get("bins", [])
        if not bins:
            return {"healthy": 0, "moderate": 0, "stressed": 0, "sparse": 0, "no_vegetation": 100}

        total_count = sum(b.get("count", 0) for b in bins)
        if total_count == 0:
            return {"healthy": 0, "moderate": 0, "stressed": 0, "sparse": 0, "no_vegetation": 100}

        counts = {"healthy": 0, "moderate": 0, "stressed": 0, "sparse": 0, "no_vegetation": 0}

        low_edge = histogram.get("lowEdge", -1.0)
        high_edge = histogram.get("highEdge", 1.0)
        n_bins = len(bins)
        bin_width = (high_edge - low_edge) / n_bins

        for i, b in enumerate(bins):
            bin_center = low_edge + (i + 0.5) * bin_width
            count = b.get("count", 0)
            if bin_center < 0.0:
                counts["no_vegetation"] += count
            elif bin_center < 0.1:
                counts["sparse"] += count
            elif bin_center < 0.3:
                counts["stressed"] += count
            elif bin_center < 0.6:
                counts["moderate"] += count
            else:
                counts["healthy"] += count

        return {k: round((v / total_count) * 100, 1) for k, v in counts.items()}

    # ── Process API (rendered image) ──────────────────────────────────────────

    async def get_ndvi_image(
        self,
        polygon: list[list[float]],
        bbox: list[float],
        date_acquired: str,
    ) -> bytes:
        """
        Call the Sentinel Hub Process API to get a rendered NDVI PNG image.
        Returns raw PNG bytes.
        """
        token = await self._get_token()

        west, south, east, north = bbox

        # Calculate output image dimensions (max 512px on longest side)
        lon_span = east - west
        lat_span = north - south
        aspect = lon_span / max(lat_span, 1e-6)
        if aspect >= 1:
            width, height = 512, max(1, int(512 / aspect))
        else:
            width, height = max(1, int(512 * aspect)), 512

        payload = {
            "input": {
                "bounds": {
                    "bbox": [west, south, east, north],
                    "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"},
                },
                "data": [
                    {
                        "type": "sentinel-2-l2a",
                        "dataFilter": {
                            "timeRange": {
                                "from": f"{date_acquired}T00:00:00Z",
                                "to": f"{date_acquired}T23:59:59Z",
                            },
                        },
                    }
                ],
            },
            "output": {
                "width": width,
                "height": height,
                "responses": [
                    {
                        "identifier": "visual",
                        "format": {"type": "image/png"},
                    }
                ],
            },
            "evalscript": NDVI_EVALSCRIPT,
        }

        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                settings.sentinelhub_process_url,
                json=payload,
                headers={**self._auth_headers(token), "Content-Type": "application/json"},
            )

        if response.status_code != 200:
            raise SentinelHubError(
                f"Process API error {response.status_code}: {response.text}"
            )

        return response.content  # raw PNG bytes

    # ── Health status label ───────────────────────────────────────────────────

    @staticmethod
    def get_health_status(ndvi_mean: float) -> str:
        if ndvi_mean >= 0.6:
            return "Healthy"
        if ndvi_mean >= 0.3:
            return "Moderate"
        if ndvi_mean >= 0.1:
            return "Stressed"
        if ndvi_mean >= 0.0:
            return "Sparse"
        return "No Vegetation"


# Singleton instance — reused across requests (keeps the token cached)
sentinel_service = SentinelHubService()
