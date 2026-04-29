"""
SearXNG web search tool — Step 3
Queries self-hosted SearXNG for web results and images.

SearXNG JSON API:
  GET /search?q=...&format=json&categories=general
  GET /search?q=...&format=json&categories=images
"""
import asyncio
import httpx
from typing import List, Dict, Optional


class SearchTool:
    """Searches the web via a self-hosted SearXNG instance."""

    def __init__(self, searxng_url: str):
        self.base_url = searxng_url.rstrip("/")
        self.timeout = httpx.Timeout(15.0, connect=5.0)
        self.headers = {"Accept": "application/json"}
        print(f"  🔍 SearchTool ready | {searxng_url}")

    async def search(
        self,
        query: str,
        categories: str = "general",
        num_results: int = 10,
        language: str = "en",
    ) -> List[Dict]:
        """
        Perform a web search via SearXNG.

        Args:
            query: Search query string
            categories: SearXNG category (general, images, news, map)
            num_results: Max results to return
            language: Search language

        Returns:
            List of {title, url, snippet, engine, score}
        """
        params = {
            "q": query,
            "format": "json",
            "categories": categories,
            "language": language,
            "pageno": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.base_url}/search",
                    params=params,
                    headers=self.headers,
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("results", [])[:num_results]:
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content", ""),
                    "engine": item.get("engine", ""),
                    "score": item.get("score", 0),
                })

            return results

        except httpx.HTTPStatusError as e:
            print(f"  ⚠️ SearXNG HTTP error: {e.response.status_code}")
            return []
        except httpx.RequestError as e:
            print(f"  ⚠️ SearXNG connection error: {e}")
            return []
        except Exception as e:
            print(f"  ⚠️ SearXNG unexpected error: {e}")
            return []

    async def search_images(
        self,
        query: str,
        num_results: int = 5,
    ) -> List[Dict]:
        """
        Search for images via SearXNG.

        Returns:
            List of {url, thumbnail, title, source, source_url}
        """
        params = {
            "q": query,
            "format": "json",
            "categories": "images",
            "pageno": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    f"{self.base_url}/search",
                    params=params,
                    headers=self.headers,
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("results", [])[:num_results]:
                img_url = item.get("img_src", "") or item.get("url", "")
                if not img_url:
                    continue

                results.append({
                    "url": img_url,
                    "thumbnail": item.get("thumbnail_src", img_url),
                    "title": item.get("title", ""),
                    "source": item.get("engine", ""),
                    "source_url": item.get("url", ""),
                })

            return results

        except Exception as e:
            print(f"  ⚠️ SearXNG image search error: {e}")
            return []

    async def search_restaurants(
        self,
        lat: float,
        lng: float,
        radius_m: int = 1500,
        extra_queries: Optional[List[str]] = None,
    ) -> List[Dict]:
        """
        Search for halal/Muslim-friendly restaurants near a coordinate.
        Runs multiple search queries in parallel for broader coverage.

        Args:
            lat, lng: Center coordinates
            radius_m: Search radius in meters
            extra_queries: Additional custom queries to run

        Returns:
            Combined, deduplicated list of search results
        """
        # Convert radius to a human-readable area description
        # Use reverse geocode or just "near lat,lng"
        radius_km = radius_m / 1000.0
        coord_str = f"{lat:.4f},{lng:.4f}"

        # Core queries — cover all Muslim-friendly food categories:
        # 1. Halal certified (MUIS)
        # 2. Halal (general)
        # 3. Muslim owned
        # 4. No pork no lard
        # 5. Vegetarian / vegan (safe for Muslim consumption)
        # 6. Cuisine-based (Malay, Indonesian, Middle Eastern, Indian, Turkish)
        queries = [
            f"halal certified restaurant near {coord_str} Singapore",
            f"MUIS halal food near {coord_str} Singapore",
            f"halal restaurant near {coord_str} Singapore",
            f"Muslim owned restaurant near {coord_str} Singapore",
            f"Muslim friendly food near {coord_str} Singapore",
            f"no pork no lard restaurant near {coord_str} Singapore",
            f"vegetarian vegan restaurant near {coord_str} Singapore",
            f"Malay Indonesian food near {coord_str} Singapore",
            f"Middle Eastern Arab Turkish food near {coord_str} Singapore",
            f"Indian Pakistani restaurant near {coord_str} Singapore",
        ]

        if extra_queries:
            queries.extend(extra_queries)

        # Run all searches in parallel
        tasks = [self.search(q, num_results=10) for q in queries]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Flatten + deduplicate by URL
        seen_urls = set()
        combined = []
        for result_set in all_results:
            if isinstance(result_set, Exception):
                print(f"  ⚠️ Search query failed: {result_set}")
                continue
            for item in result_set:
                url = item.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    combined.append(item)

        print(f"  🔍 Restaurant search: {len(queries)} queries → {len(combined)} unique results")
        return combined

    async def search_place_details(
        self,
        name: str,
        queries_extra: Optional[List[str]] = None,
    ) -> Dict[str, List[Dict]]:
        """
        Search for detailed info about a specific restaurant.
        Runs targeted searches for menu, halal cert, reviews.

        Returns:
            {
                "general": [...results...],
                "halal": [...results...],
                "menu": [...results...],
                "reviews": [...results...],
            }
        """
        search_map = {
            "general": f"{name} Singapore restaurant",
            "halal": f"{name} Singapore halal certificate MUIS certified",
            "pork_lard": f"{name} Singapore no pork no lard",
            "muslim_owned": f"{name} Singapore Muslim owned",
            "menu": f"{name} Singapore menu prices food",
            "reviews": f"{name} Singapore review rating",
            "vegan": f"{name} Singapore vegetarian vegan plant-based",
            # Halal-specific directories and databases
            "halaltag": f"site:halaltag.com {name} Singapore",
            "halaltrip": f"site:halaltrip.com {name} Singapore",
            "sethlah": f"site:sethlah.com {name}",
            "muis_dir": f"site:muis.gov.sg {name} halal",
        }

        if queries_extra:
            for i, q in enumerate(queries_extra):
                search_map[f"extra_{i}"] = q

        # Run all in parallel
        tasks = {
            key: self.search(query, num_results=5)
            for key, query in search_map.items()
        }

        results = {}
        gathered = await asyncio.gather(
            *[self.search(q, num_results=5) for q in search_map.values()],
            return_exceptions=True,
        )

        for key, result in zip(search_map.keys(), gathered):
            if isinstance(result, Exception):
                print(f"  ⚠️ Detail search '{key}' failed: {result}")
                results[key] = []
            else:
                results[key] = result

        total = sum(len(v) for v in results.values())
        print(f"  🔍 Place detail search for '{name}': {total} results across {len(results)} categories")
        return results
