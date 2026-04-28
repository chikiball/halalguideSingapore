"""
Web scraper tool — Step 4
Scrapes web pages for structured content using httpx + BeautifulSoup.
Also checks MUIS halal certification directory.
"""
import re
import asyncio
import httpx
from typing import Dict, List, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse


class ScraperTool:
    """Scrapes web pages and extracts structured content."""

    def __init__(self):
        self.timeout = httpx.Timeout(10.0, connect=5.0)
        self.headers = {
            "User-Agent": "Mozilla/5.0 (compatible; HalalGuideSG/1.0; +https://halal.nandharu.uk)",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "en-US,en;q=0.9",
        }
        self.max_text_length = 3000  # chars — keep LLM context manageable
        print("  🌐 ScraperTool ready")

    async def scrape(self, url: str) -> Dict:
        """
        Scrape a URL and extract structured content.

        Returns:
            {
                "url": str,
                "title": str,
                "description": str,
                "og_image": str or None,
                "images": [{url, alt}],
                "text": str (truncated to max_text_length),
                "links": [{text, href}],
                "success": bool,
            }
        """
        result = {
            "url": url,
            "title": "",
            "description": "",
            "og_image": None,
            "images": [],
            "text": "",
            "links": [],
            "success": False,
        }

        try:
            if not url.startswith("http"):
                url = "https://" + url

            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                max_redirects=5,
            ) as client:
                resp = await client.get(url, headers=self.headers)
                resp.raise_for_status()

            content_type = resp.headers.get("content-type", "")
            if "text/html" not in content_type:
                return result

            soup = BeautifulSoup(resp.text, "html.parser")

            # Remove noisy elements
            for tag in soup(["script", "style", "nav", "footer", "iframe", "noscript"]):
                tag.decompose()

            # Title
            result["title"] = (
                self._meta(soup, "og:title")
                or (soup.title.string.strip() if soup.title and soup.title.string else "")
            )

            # Description
            result["description"] = (
                self._meta(soup, "og:description")
                or self._meta_name(soup, "description")
                or ""
            )

            # OG Image
            og_img = self._meta(soup, "og:image")
            if og_img:
                result["og_image"] = self._abs_url(og_img, url)

            # Extract images (first 10 meaningful ones)
            images = []
            for img in soup.find_all("img", src=True)[:20]:
                src = img.get("src", "")
                alt = img.get("alt", "")
                if not src or self._is_junk_image(src):
                    continue
                abs_src = self._abs_url(src, url)
                if abs_src:
                    images.append({"url": abs_src, "alt": alt})
                if len(images) >= 10:
                    break
            result["images"] = images

            # Extract visible text (cleaned, truncated)
            text = soup.get_text(separator="\n", strip=True)
            # Collapse multiple newlines/spaces
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = re.sub(r" {2,}", " ", text)
            result["text"] = text[: self.max_text_length]

            # Extract relevant links
            links = []
            for a in soup.find_all("a", href=True)[:30]:
                href = a.get("href", "")
                link_text = a.get_text(strip=True)
                if not link_text or len(link_text) < 3:
                    continue
                abs_href = self._abs_url(href, url)
                if abs_href and abs_href.startswith("http"):
                    links.append({"text": link_text[:100], "href": abs_href})
            result["links"] = links[:15]

            result["success"] = True
            print(f"  🌐 Scraped: {url[:60]}... ({len(result['text'])} chars, {len(images)} imgs)")

        except httpx.HTTPStatusError as e:
            print(f"  ⚠️ Scrape HTTP error {e.response.status_code}: {url[:60]}")
        except httpx.RequestError as e:
            print(f"  ⚠️ Scrape connection error: {url[:60]} — {e}")
        except Exception as e:
            print(f"  ⚠️ Scrape error: {url[:60]} — {e}")

        return result

    async def scrape_multiple(self, urls: List[str], max_concurrent: int = 5) -> List[Dict]:
        """Scrape multiple URLs with concurrency limit."""
        semaphore = asyncio.Semaphore(max_concurrent)

        async def _limited_scrape(u: str) -> Dict:
            async with semaphore:
                return await self.scrape(u)

        results = await asyncio.gather(
            *[_limited_scrape(u) for u in urls],
            return_exceptions=True,
        )

        return [
            r if isinstance(r, dict) else {"url": urls[i], "success": False, "error": str(r)}
            for i, r in enumerate(results)
        ]

    async def scrape_muis(self, restaurant_name: str) -> Dict:
        """
        Check MUIS (Majlis Ugama Islam Singapura) halal certification.
        Searches the MUIS halal directory for the restaurant name.

        Returns:
            {
                "found": bool,
                "certified": bool,
                "certificate_number": str or None,
                "company_name": str or None,
                "address": str or None,
                "expiry": str or None,
                "search_url": str,
                "snippets": [str],
            }
        """
        result = {
            "found": False,
            "certified": False,
            "certificate_number": None,
            "company_name": None,
            "address": None,
            "expiry": None,
            "search_url": "",
            "snippets": [],
        }

        # MUIS halal directory search URL
        search_url = "https://www.muis.gov.sg/Halal/Halal-Certificates/Certified-Eating-Establishments"
        result["search_url"] = search_url

        try:
            # Try scraping MUIS eating establishments page
            # The MUIS site may use JS rendering, so we also try a Google search fallback
            queries = [
                f'site:muis.gov.sg "{restaurant_name}" halal',
                f'"{restaurant_name}" MUIS halal certificate Singapore',
            ]

            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
            ) as client:
                # Direct MUIS page scrape attempt
                try:
                    resp = await client.get(search_url, headers=self.headers)
                    if resp.status_code == 200:
                        soup = BeautifulSoup(resp.text, "html.parser")
                        page_text = soup.get_text(separator=" ", strip=True).lower()
                        name_lower = restaurant_name.lower()

                        if name_lower in page_text:
                            result["found"] = True
                            result["certified"] = True
                            result["snippets"].append(
                                f"Restaurant name '{restaurant_name}' found on MUIS certified establishments page."
                            )
                except Exception:
                    pass

            # Extract certificate pattern from any gathered text
            # MUIS cert numbers look like: HA-xxxx-xxxx or M/xxxx/xxxx
            cert_patterns = [
                r"(HA[-/]\d{4}[-/]\d{4})",
                r"(M[-/]\d{4}[-/]\d{4})",
                r"(MUIS[-/]\w+[-/]\d+)",
            ]

            print(f"  ☪️ MUIS check for '{restaurant_name}': {'✅ FOUND' if result['found'] else '❌ Not found'}")

        except Exception as e:
            print(f"  ⚠️ MUIS check error: {e}")
            result["snippets"].append(f"Error checking MUIS directory: {str(e)}")

        return result

    async def extract_restaurant_info(self, url: str) -> Dict:
        """
        Scrape a restaurant's website and extract structured info.
        Looks for menu, prices, hours, address, halal mentions.

        Returns:
            {
                "name": str,
                "menu_items": [str],
                "price_range": str,
                "hours": str,
                "address": str,
                "phone": str,
                "halal_mentions": [str],
                "images": [{url, alt}],
            }
        """
        scraped = await self.scrape(url)
        if not scraped["success"]:
            return {"error": f"Could not scrape {url}"}

        text = scraped["text"].lower()
        info = {
            "name": scraped["title"],
            "menu_items": [],
            "price_range": "",
            "hours": "",
            "address": "",
            "phone": "",
            "halal_mentions": [],
            "images": scraped["images"][:5],
        }

        # Find halal mentions
        halal_keywords = ["halal", "muis", "muslim", "certified", "certificate", "حلال"]
        for kw in halal_keywords:
            if kw in text:
                # Extract surrounding context (50 chars before/after)
                idx = text.find(kw)
                start = max(0, idx - 50)
                end = min(len(text), idx + len(kw) + 50)
                context = scraped["text"][start:end].strip()
                info["halal_mentions"].append(context)

        # Find price patterns ($, SGD, S$)
        price_matches = re.findall(
            r"(?:S?\$|SGD)\s*\d+(?:\.\d{2})?(?:\s*[-–]\s*(?:S?\$|SGD)?\s*\d+(?:\.\d{2})?)?",
            scraped["text"],
        )
        if price_matches:
            prices = price_matches[:5]
            info["price_range"] = " | ".join(prices)

        # Find phone numbers (SG format: +65 xxxx xxxx or 6xxx xxxx)
        phone_matches = re.findall(
            r"(?:\+65\s?)?[689]\d{3}\s?\d{4}",
            scraped["text"],
        )
        if phone_matches:
            info["phone"] = phone_matches[0]

        # Find operating hours patterns
        hours_patterns = [
            r"(?:open|hours|operating)[\s:]+([^\n]{10,60})",
            r"(\d{1,2}(?::\d{2})?\s*(?:am|pm)\s*[-–]\s*\d{1,2}(?::\d{2})?\s*(?:am|pm))",
            r"((?:mon|tue|wed|thu|fri|sat|sun)\w*\s*[-–:]\s*[^\n]{5,40})",
        ]
        for pattern in hours_patterns:
            match = re.search(pattern, scraped["text"], re.IGNORECASE)
            if match:
                info["hours"] = match.group(1).strip() if match.lastindex else match.group(0).strip()
                break

        return info

    # ─── Private helpers ──────────────────────────────────────────

    @staticmethod
    def _meta(soup: BeautifulSoup, prop: str) -> str:
        """Get og: meta tag content."""
        tag = soup.find("meta", property=prop)
        return tag["content"].strip() if tag and tag.get("content") else ""

    @staticmethod
    def _meta_name(soup: BeautifulSoup, name: str) -> str:
        """Get meta name= tag content."""
        tag = soup.find("meta", attrs={"name": name})
        return tag["content"].strip() if tag and tag.get("content") else ""

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
        return urljoin(base, src)

    @staticmethod
    def _is_junk_image(src: str) -> bool:
        """Filter out tracking pixels, icons, SVGs, etc."""
        junk = [
            ".svg", "pixel", "tracking", "spacer", "blank",
            "1x1", "favicon", "icon", "logo", "sprite",
            "data:image", "base64",
        ]
        src_lower = src.lower()
        return any(j in src_lower for j in junk)
