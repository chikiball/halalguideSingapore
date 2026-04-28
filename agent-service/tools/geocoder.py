"""
Nominatim geocoding tool — Step 5
Converts addresses to coordinates and vice versa.
Uses OpenStreetMap's free Nominatim API (no API key needed).

API docs: https://nominatim.org/release-docs/latest/api/Search/

Usage policy: max 1 req/sec, include User-Agent.
We add a small delay between batch requests to be polite.
"""
import asyncio
import math
import httpx
from typing import Dict, List, Optional, Tuple


class GeocoderTool:
    """Geocodes addresses to coordinates using Nominatim (free, OSM-based)."""

    def __init__(self, nominatim_url: str):
        self.base_url = nominatim_url.rstrip("/")
        self.timeout = httpx.Timeout(10.0, connect=5.0)
        self.headers = {
            "User-Agent": "HalalGuideSG/1.0 (halal food guide; https://halal.nandharu.uk)",
            "Accept": "application/json",
        }
        # Rate limit: Nominatim allows max 1 req/sec
        self._last_request_time = 0.0
        self._min_interval = 1.1  # seconds between requests
        print(f"  📍 GeocoderTool ready | {nominatim_url}")

    async def _rate_limit(self):
        """Enforce Nominatim's 1 req/sec policy."""
        import time
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.time()

    async def geocode(self, address: str, country: str = "sg") -> Optional[Dict]:
        """
        Convert an address string to coordinates.

        Args:
            address: Address or place name to geocode
            country: ISO country code to bias results (default: Singapore)

        Returns:
            {lat, lng, display_name, type, importance} or None if not found
        """
        await self._rate_limit()

        params = {
            "q": address,
            "format": "json",
            "countrycodes": country,
            "limit": 1,
            "addressdetails": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.base_url}/search",
                    params=params,
                    headers=self.headers,
                )
                resp.raise_for_status()
                results = resp.json()

            if not results:
                return None

            r = results[0]
            result = {
                "lat": float(r["lat"]),
                "lng": float(r["lon"]),
                "display_name": r.get("display_name", ""),
                "type": r.get("type", ""),
                "importance": r.get("importance", 0),
                "address": r.get("address", {}),
            }

            print(f"  📍 Geocoded: '{address}' → {result['lat']:.4f}, {result['lng']:.4f}")
            return result

        except Exception as e:
            print(f"  ⚠️ Geocode failed for '{address}': {e}")
            return None

    async def reverse_geocode(self, lat: float, lng: float) -> Optional[Dict]:
        """
        Convert coordinates to a human-readable address/neighborhood.
        Useful for making search queries more specific.

        Args:
            lat, lng: Coordinates

        Returns:
            {display_name, neighbourhood, suburb, city, road} or None
        """
        await self._rate_limit()

        params = {
            "lat": lat,
            "lon": lng,
            "format": "json",
            "zoom": 16,  # neighbourhood level
            "addressdetails": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.base_url}/reverse",
                    params=params,
                    headers=self.headers,
                )
                resp.raise_for_status()
                data = resp.json()

            addr = data.get("address", {})
            result = {
                "display_name": data.get("display_name", ""),
                "neighbourhood": addr.get("neighbourhood", ""),
                "suburb": addr.get("suburb", ""),
                "city": addr.get("city", addr.get("town", "")),
                "road": addr.get("road", ""),
                "postcode": addr.get("postcode", ""),
            }

            area = result["neighbourhood"] or result["suburb"] or result["road"]
            print(f"  📍 Reverse geocoded: {lat:.4f}, {lng:.4f} → {area}")
            return result

        except Exception as e:
            print(f"  ⚠️ Reverse geocode failed: {e}")
            return None

    async def geocode_batch(self, addresses: List[str], country: str = "sg") -> List[Optional[Dict]]:
        """
        Geocode multiple addresses sequentially (respecting rate limit).

        Args:
            addresses: List of address strings
            country: ISO country code

        Returns:
            List of geocode results (None for failed ones)
        """
        results = []
        for addr in addresses:
            result = await self.geocode(addr, country)
            results.append(result)
        print(f"  📍 Batch geocoded: {len(addresses)} addresses → {sum(1 for r in results if r)} found")
        return results

    def filter_by_radius(
        self,
        places: List[Dict],
        center_lat: float,
        center_lng: float,
        radius_m: int,
    ) -> List[Dict]:
        """
        Filter a list of places to only those within radius of center point.
        Each place must have 'lat' and 'lng' keys.

        Returns:
            Filtered list with 'distance' field added to each place.
        """
        filtered = []
        for place in places:
            lat = place.get("lat")
            lng = place.get("lng")
            if lat is None or lng is None:
                continue
            dist = self.distance(center_lat, center_lng, lat, lng)
            if dist <= radius_m:
                place["distance"] = round(dist)
                filtered.append(place)

        filtered.sort(key=lambda p: p["distance"])
        print(f"  📍 Radius filter: {len(places)} → {len(filtered)} within {radius_m}m")
        return filtered

    def get_area_name(self, reverse_result: Optional[Dict]) -> str:
        """
        Extract a human-readable area name from reverse geocode result.
        Used to enhance search queries with local area names.

        Returns:
            Area name string like "Kampong Glam" or "Bugis"
        """
        if not reverse_result:
            return "Singapore"

        # Priority: neighbourhood > suburb > road > city
        for key in ["neighbourhood", "suburb", "road", "city"]:
            value = reverse_result.get(key, "")
            if value:
                return value

        return "Singapore"

    @staticmethod
    def distance(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
        """Haversine distance in meters between two points."""
        R = 6371e3
        d_lat = math.radians(lat2 - lat1)
        d_lng = math.radians(lng2 - lng1)
        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(d_lng / 2) ** 2
        )
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
