"""Nominatim geocoding tool — Step 5."""
import httpx
import math
from typing import Dict, Optional


class GeocoderTool:
    def __init__(self, nominatim_url: str):
        self.base_url = nominatim_url.rstrip("/")
        print(f"  📍 GeocoderTool ready | {nominatim_url}")

    async def geocode(self, address: str, country: str = "sg") -> Optional[Dict]:
        """Convert address string to {lat, lng, display_name}."""
        # TODO: Implement in Step 5
        return None

    @staticmethod
    def distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Haversine distance in meters."""
        R = 6371e3
        d_lat = math.radians(lat2 - lat1)
        d_lng = math.radians(lng2 - lng1)
        a = math.sin(d_lat / 2) ** 2 + \
            math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * \
            math.sin(d_lng / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
