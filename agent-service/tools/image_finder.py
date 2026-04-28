"""
Image finder tool — Step 9
Finds restaurant images from multiple sources:
  1. SearXNG image search
  2. Website og:image / hero images (via ScraperTool)
  3. Cuisine-based fallback images

Priority order: website photos > search images > fallback
"""
import asyncio
import re
import httpx
from typing import List, Dict, Optional
from urllib.parse import urlparse


# Cuisine-based fallback images (Unsplash, free to use)
CUISINE_FALLBACKS = {
    "malay":          "https://images.unsplash.com/photo-1562279972-096e1e2e3afc?w=600&q=80",
    "indonesian":     "https://images.unsplash.com/photo-1585032226651-759b368d7246?w=600&q=80",
    "indian":         "https://images.unsplash.com/photo-1565557623262-b51c2513a641?w=600&q=80",
    "middle eastern": "https://images.unsplash.com/photo-1541518763669-27fef04b14ea?w=600&q=80",
    "arab":           "https://images.unsplash.com/photo-1541518763669-27fef04b14ea?w=600&q=80",
    "turkish":        "https://images.unsplash.com/photo-1599487488170-d11ec9c172f0?w=600&q=80",
    "japanese":       "https://images.unsplash.com/photo-1553621042-f6e147245754?w=600&q=80",
    "burger":         "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?w=600&q=80",
    "kebab":          "https://images.unsplash.com/photo-1529006557810-274b9b2fc783?w=600&q=80",
    "seafood":        "https://images.unsplash.com/photo-1615141982883-c7ad0e69fd62?w=600&q=80",
    "chinese":        "https://images.unsplash.com/photo-1552566626-52f8b828add9?w=600&q=80",
    "pakistani":      "https://images.unsplash.com/photo-1565557623262-b51c2513a641?w=600&q=80",
    "vegetarian":     "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=600&q=80",
    "vegan":          "https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=600&q=80",
    "cafe":           "https://images.unsplash.com/photo-1554118811-1e0d58224f24?w=600&q=80",
    "default":        "https://images.unsplash.com/photo-1517248135467-4c7edcad34c4?w=600&q=80",
}

# Image URL patterns to skip (ads, tracking, tiny images)
SKIP_PATTERNS = [
    r"logo", r"icon", r"favicon", r"sprite", r"avatar",
    r"pixel", r"tracking", r"spacer", r"blank", r"badge",
    r"banner.*ad", r"advertisement", r"1x1", r"\.gif$",
    r"\.svg$", r"data:image", r"base64", r"facebook\.com",
    r"twitter\.com", r"googleapis\.com/maps",
]
_skip_re = re.compile("|".join(SKIP_PATTERNS), re.IGNORECASE)


class ImageFinderTool:
    """Finds images for restaurants via SearXNG image search + website scraping."""

    def __init__(self, searxng_url: str):
        self.searxng_url = searxng_url.rstrip("/")
        self.timeout = httpx.Timeout(10.0, connect=5.0)
        self.headers = {"Accept": "application/json"}
        print("  🖼️  ImageFinderTool ready")

    async def find_images(
        self,
        name: str,
        cuisine: str = "",
        website_url: str = "",
        max_images: int = 5,
    ) -> List[Dict]:
        """
        Find images for a restaurant from multiple sources.

        Args:
            name: Restaurant name
            cuisine: Cuisine type (for fallback images)
            website_url: Restaurant website (if known, for og:image)
            max_images: Maximum images to return

        Returns:
            List of {url, caption, source, thumbnail}
        """
        all_images = []
        seen_urls = set()

        # 1. Try restaurant website first (highest quality)
        if website_url:
            web_images = await self._extract_website_images(website_url, name)
            for img in web_images:
                if img["url"] not in seen_urls:
                    seen_urls.add(img["url"])
                    all_images.append(img)

        # 2. SearXNG image search
        search_images = await self._search_images(name)
        for img in search_images:
            if img["url"] not in seen_urls:
                seen_urls.add(img["url"])
                all_images.append(img)

        # 3. Validate images (check they actually load)
        valid_images = await self._validate_images(all_images[:max_images + 3])

        # 4. If still not enough, add cuisine fallback
        if len(valid_images) < 1:
            fallback = self._get_cuisine_fallback(cuisine)
            valid_images.append(fallback)

        result = valid_images[:max_images]
        print(f"  🖼️ Found {len(result)} images for '{name}'")
        return result

    async def _search_images(self, name: str) -> List[Dict]:
        """Search for images via SearXNG."""
        queries = [
            f"{name} Singapore restaurant food",
            f"{name} Singapore halal",
        ]

        all_images = []
        for query in queries:
            try:
                params = {
                    "q": query,
                    "format": "json",
                    "categories": "images",
                    "pageno": 1,
                }
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(
                        f"{self.searxng_url}/search",
                        params=params,
                        headers=self.headers,
                    )
                    resp.raise_for_status()
                    data = resp.json()

                for item in data.get("results", [])[:5]:
                    img_url = item.get("img_src", "") or item.get("url", "")
                    if not img_url or _skip_re.search(img_url):
                        continue

                    all_images.append({
                        "url": img_url,
                        "thumbnail": item.get("thumbnail_src", img_url),
                        "caption": item.get("title", name),
                        "source": "search",
                    })

            except Exception as e:
                print(f"  ⚠️ Image search failed for '{query}': {e}")

        return all_images

    async def _extract_website_images(self, url: str, name: str) -> List[Dict]:
        """Extract images from a restaurant's website."""
        images = []

        try:
            if not url.startswith("http"):
                url = "https://" + url

            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; HalalGuideSG/1.0)",
                    "Accept": "text/html",
                })
                resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type:
                return images

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")

            # og:image (highest priority — curated by the website)
            og_img = soup.find("meta", property="og:image")
            if og_img and og_img.get("content"):
                img_url = self._abs_url(og_img["content"], url)
                if img_url and not _skip_re.search(img_url):
                    images.append({
                        "url": img_url,
                        "thumbnail": img_url,
                        "caption": name,
                        "source": "website",
                    })

            # Hero / main images
            selectors = [
                'img[class*="hero"]', 'img[class*="banner"]',
                'img[class*="header"]', 'img[class*="main"]',
                'img[class*="featured"]', '.hero img',
                '.banner img', 'header img', 'main img',
            ]
            for sel in selectors:
                for img in soup.select(sel)[:2]:
                    src = img.get("src") or img.get("data-src") or img.get("data-lazy")
                    if not src or _skip_re.search(src):
                        continue
                    abs_src = self._abs_url(src, url)
                    if abs_src:
                        images.append({
                            "url": abs_src,
                            "thumbnail": abs_src,
                            "caption": img.get("alt", name),
                            "source": "website",
                        })

            # Large content images (width > 200 or no explicit small size)
            for img in soup.find_all("img", src=True)[:15]:
                src = img.get("src", "")
                width = img.get("width", "")
                if _skip_re.search(src):
                    continue
                # Skip tiny images
                try:
                    if width and int(width) < 150:
                        continue
                except (ValueError, TypeError):
                    pass
                abs_src = self._abs_url(src, url)
                if abs_src and abs_src not in [i["url"] for i in images]:
                    images.append({
                        "url": abs_src,
                        "thumbnail": abs_src,
                        "caption": img.get("alt", name),
                        "source": "website",
                    })
                if len(images) >= 5:
                    break

        except Exception as e:
            print(f"  ⚠️ Website image extraction failed for {url[:50]}: {e}")

        return images

    async def _validate_images(self, images: List[Dict]) -> List[Dict]:
        """Check that image URLs actually resolve (HEAD request)."""
        valid = []

        async def _check(img: Dict) -> Optional[Dict]:
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                    resp = await client.head(
                        img["url"],
                        follow_redirects=True,
                        headers={"User-Agent": "HalalGuideSG/1.0"},
                    )
                    if resp.status_code == 200:
                        content_type = resp.headers.get("content-type", "")
                        if "image" in content_type:
                            return img
            except Exception:
                pass
            return None

        results = await asyncio.gather(
            *[_check(img) for img in images],
            return_exceptions=True,
        )

        for r in results:
            if isinstance(r, dict):
                valid.append(r)

        return valid

    def _get_cuisine_fallback(self, cuisine: str) -> Dict:
        """Get a cuisine-appropriate fallback image from Unsplash."""
        if cuisine:
            cuisine_lower = cuisine.lower()
            for key, url in CUISINE_FALLBACKS.items():
                if key in cuisine_lower:
                    return {
                        "url": url,
                        "thumbnail": url,
                        "caption": f"{key.title()} cuisine",
                        "source": "fallback",
                    }

        return {
            "url": CUISINE_FALLBACKS["default"],
            "thumbnail": CUISINE_FALLBACKS["default"],
            "caption": "Restaurant",
            "source": "fallback",
        }

    @staticmethod
    def _abs_url(src: str, base: str) -> Optional[str]:
        """Convert relative URL to absolute."""
        if not src:
            return None
        if src.startswith("data:"):
            return None
        if src.startswith("//"):
            return "https:" + src
        if src.startswith("/"):
            parsed = urlparse(base)
            return f"{parsed.scheme}://{parsed.netloc}{src}"
        if src.startswith("http"):
            return src
        from urllib.parse import urljoin
        return urljoin(base, src)
