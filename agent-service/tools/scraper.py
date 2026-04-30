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
        Check MUIS halal certification via the official MUIS e-Service API.

        Flow:
        1. GET https://halal.muis.gov.sg/halal/establishments → get session cookie + CSRF token
        2. POST https://halal.muis.gov.sg/api/halal/establishments
              {"text": restaurant_name}
           with X-CSRF-TOKEN header + session cookie
        3. Parse response — check if restaurant name appears in results

        Returns:
            {
                "found": bool,
                "certified": bool,
                "certificate_number": str or None,
                "company_name": str or None,
                "address": str or None,
                "scheme": str or None,  (e.g. "Eating Establishment")
                "sub_scheme": str or None,  (e.g. "Restaurant" / "Food Court")
                "total_records": int,
                "all_matches": [{name, number, address, scheme}],
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
            "scheme": None,
            "sub_scheme": None,
            "total_records": 0,
            "all_matches": [],
            "search_url": "https://halal.muis.gov.sg/halal/establishments",
            "snippets": [],
        }

        muis_api = "https://halal.muis.gov.sg/api/halal/establishments"
        muis_page = "https://halal.muis.gov.sg/halal/establishments"

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                follow_redirects=True,
            ) as client:

                # Step 1: GET the directory page to obtain session cookie + CSRF token
                page_resp = await client.get(
                    muis_page,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Accept": "text/html,application/xhtml+xml",
                        "Accept-Language": "en-US,en;q=0.9",
                    }
                )

                if page_resp.status_code != 200:
                    print(f"  ☪️  MUIS page returned {page_resp.status_code}")
                    return result

                # Extract CSRF token from hidden input
                soup = BeautifulSoup(page_resp.text, "html.parser")
                csrf_input = soup.find("input", {"name": "__RequestVerificationToken"})
                if not csrf_input or not csrf_input.get("value"):
                    print(f"  ☪️  MUIS: could not extract CSRF token")
                    return result

                csrf_token = csrf_input["value"]

                # Step 2: POST to MUIS API with session cookies + CSRF token
                api_resp = await client.post(
                    muis_api,
                    json={"text": restaurant_name},
                    headers={
                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                        "Content-Type": "application/json",
                        "X-CSRF-TOKEN": csrf_token,
                        "X-Requested-With": "XMLHttpRequest",
                        "Accept": "application/json, text/plain, */*",
                        "Referer": muis_page,
                        "Origin": "https://halal.muis.gov.sg",
                    }
                )

                if api_resp.status_code != 200:
                    print(f"  ☪️  MUIS API returned {api_resp.status_code}")
                    return result

                data = api_resp.json()
                records = data.get("data", [])
                total = data.get("totalRecords", 0)
                result["total_records"] = total

                if not records:
                    print(f"  ☪️  MUIS: no results for '{restaurant_name}'")
                    return result

                # Step 3: Match results against restaurant name
                name_lower = restaurant_name.lower().strip()

                # Store all matches for the LLM to reason about
                result["all_matches"] = [
                    {
                        "name": r.get("name", ""),
                        "number": r.get("number", ""),
                        "address": r.get("address", ""),
                        "scheme": r.get("schemeText", ""),
                        "sub_scheme": r.get("subSchemeText", ""),
                    }
                    for r in records[:10]
                ]

                # Find best match — name must partially match
                best = None
                for r in records:
                    r_name = r.get("name", "").lower().strip()
                    # Check if either name contains the other
                    if (name_lower in r_name or r_name in name_lower or
                            any(word in r_name for word in name_lower.split() if len(word) > 3)):
                        best = r
                        break

                if best:
                    result["found"] = True
                    result["certified"] = True
                    result["certificate_number"] = best.get("number")
                    result["company_name"] = best.get("name")
                    result["address"] = best.get("address")
                    result["scheme"] = best.get("schemeText")
                    result["sub_scheme"] = best.get("subSchemeText")
                    result["snippets"].append(
                        f"✅ MUIS CERTIFIED: '{best['name']}' — Certificate: {best.get('number')} "
                        f"| {best.get('schemeText')} ({best.get('subSchemeText')}) "
                        f"| Address: {best.get('address')}"
                    )
                    print(f"  ☪️  MUIS ✅ CERTIFIED: '{restaurant_name}' → {best.get('number')} ({best.get('schemeText')})")
                else:
                    # No direct name match but show top results for LLM context
                    result["snippets"].append(
                        f"MUIS search for '{restaurant_name}' returned {total} results "
                        f"but no direct name match. Top result: {records[0].get('name')} "
                        f"at {records[0].get('address')}"
                    )
                    print(f"  ☪️  MUIS ❌ No match for '{restaurant_name}' ({total} results, top: {records[0].get('name')})")

        except Exception as e:
            print(f"  ⚠️  MUIS API error: {e}")
            result["snippets"].append(f"MUIS API error: {str(e)}")

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
