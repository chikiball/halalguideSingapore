"""
Halal Guide Singapore — LangChain Agent (Step 6)
Orchestrates the 3-phase pipeline:
  Phase 1: Discovery — find restaurants via search + geocode
  Phase 2: Research  — gather evidence, classify halal status
  Phase 3: Writing   — LLM-generated articles

Uses LangChain ChatOllama for LLM calls.
Uses a structured pipeline (not ReAct) for reliability with llama3.1:8b.
"""
import asyncio
import json
import os
import re
from typing import List, Dict, Any, Optional

import httpx

from tools.search import SearchTool
from tools.scraper import ScraperTool
from tools.geocoder import GeocoderTool
from tools.image_finder import ImageFinderTool
from tools.halal_classifier import HalalClassifier, HALAL_CATEGORIES


def _load_prompt(name: str) -> str:
    """Load a prompt template from the prompts/ directory."""
    path = os.path.join(os.path.dirname(__file__), "prompts", name)
    try:
        with open(path, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"  ⚠️ Prompt file not found: {path}")
        return ""


class HalalAgent:
    """
    AI Agent that uses Ollama + SearXNG to:
    1. Discover halal places near a coordinate
    2. Research each place (menu, cert, reviews)
    3. Write warm articles grounded in facts
    """

    def __init__(
        self,
        ollama_url: str,
        searxng_url: str,
        nominatim_url: str,
        model: str = "llama3.1:8b",
    ):
        self.ollama_url = ollama_url.rstrip("/")
        self.model = model

        # Initialize tools
        self.search = SearchTool(searxng_url)
        self.scraper = ScraperTool()
        self.geocoder = GeocoderTool(nominatim_url)
        self.image_finder = ImageFinderTool(searxng_url)
        self.classifier = HalalClassifier(ollama_url, model)

        # Load prompts
        self.prompt_discovery = _load_prompt("discovery.txt")
        self.prompt_research = _load_prompt("research.txt")
        self.prompt_article = _load_prompt("article.txt")

        # In-memory cache
        self._cache: Dict[str, Any] = {}
        # LLM call log (for debug panel)
        self._llm_calls: List[Dict] = []

        print(f"🤖 HalalAgent initialized | model={model}")

    # ─── LLM call helper ──────────────────────────────────────────

    async def _call_llm(self, system: str, user: str, json_mode: bool = False) -> str:
        """
        Call Ollama's chat API directly via httpx.

        Args:
            system: System prompt
            user: User message
            json_mode: If True, request JSON output format

        Returns:
            LLM response text
        """
        # Track call count for logging
        if not hasattr(self, '_llm_call_count'):
            self._llm_call_count = 0
        self._llm_call_count += 1
        call_id = self._llm_call_count

        # Log what we're sending to the LLM
        print(f"\n{'='*60}")
        print(f"  🧠 LLM CALL #{call_id} | model={self.model} | json_mode={json_mode}")
        print(f"{'='*60}")
        print(f"  📋 SYSTEM PROMPT ({len(system)} chars):")
        for line in system.split('\n')[:10]:
            print(f"    | {line}")
        if system.count('\n') > 10:
            print(f"    | ... ({system.count(chr(10)) - 10} more lines)")
        print(f"  📝 USER PROMPT ({len(user)} chars):")
        for line in user.split('\n')[:20]:
            print(f"    | {line}")
        if user.count('\n') > 20:
            print(f"    | ... ({user.count(chr(10)) - 20} more lines)")
        print(f"  ⏳ Calling Ollama...")

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {
                "temperature": 0.3,  # low temp for factual tasks
                "num_predict": 2048,
            },
        }

        if json_mode:
            payload["format"] = "json"

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=10.0)
            ) as client:
                resp = await client.post(
                    f"{self.ollama_url}/api/chat",
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                response_text = data.get("message", {}).get("content", "")

                # Log the response
                duration = data.get("total_duration", 0) / 1e9  # nanoseconds to seconds
                print(f"  ✅ LLM RESPONSE #{call_id} ({len(response_text)} chars, {duration:.1f}s):")
                for line in response_text.split('\n')[:15]:
                    print(f"    | {line}")
                if response_text.count('\n') > 15:
                    print(f"    | ... ({response_text.count(chr(10)) - 15} more lines)")
                print(f"{'='*60}\n")

                # Store for debug panel
                self._llm_calls.append({
                    "call_id": call_id,
                    "system_prompt": system[:500],
                    "user_prompt": user[:2000],
                    "response": response_text[:1500],
                    "duration_s": round(duration, 1),
                    "json_mode": json_mode,
                })
                # Keep only last 10 calls
                if len(self._llm_calls) > 10:
                    self._llm_calls = self._llm_calls[-10:]

                return response_text

        except Exception as e:
            print(f"  ⚠️ LLM CALL #{call_id} FAILED: {e}")
            return ""

    # ═══════════════════════════════════════════════════════════════
    # PHASE 1 — DISCOVERY
    # ═══════════════════════════════════════════════════════════════

    async def discover_places(self, lat: float, lng: float, radius: int, debug_emit=None) -> List[Dict]:
        """
        Phase 1: Search for restaurants, extract names, geocode them.
        debug_emit: optional async callback to emit debug events to SSE stream
        """
        async def _dbg(event_type, message, data=None):
            """Emit debug event if callback provided."""
            print(f"  [{event_type}] {message}")
            if debug_emit:
                evt = {"type": event_type, "message": message}
                if data:
                    evt["data"] = data
                await debug_emit(evt)

        cache_key = f"discover_{lat:.3f}_{lng:.3f}_{radius}"
        if cache_key in self._cache:
            await _dbg("cache", f"Cache hit: {cache_key}")
            return self._cache[cache_key]

        await _dbg("phase", f"🔍 Phase 1: Discovering near {lat:.4f}, {lng:.4f} (radius {radius}m)")

        # 1. Reverse geocode to get area name
        area_info = await self.geocoder.reverse_geocode(lat, lng)
        area_name = self.geocoder.get_area_name(area_info)
        await _dbg("geocode", f"📍 Area: {area_name}")

        # 2. Run SearXNG searches with area-aware extra queries
        extra_queries = [
            f"halal food {area_name} Singapore",
            f"Muslim restaurant {area_name} Singapore",
        ]
        search_results = await self.search.search_restaurants(
            lat, lng, radius, extra_queries=extra_queries
        )

        await _dbg("search", f"🔍 SearXNG returned {len(search_results)} unique results",
                    {"count": len(search_results),
                     "results": [{"title": r.get("title", "")[:80], "url": r.get("url", "")[:100], "snippet": r.get("snippet", "")[:120]} for r in search_results]})

        if not search_results:
            await _dbg("error", "❌ No search results found")
            return []

        # 2b. PRE-FILTER: keep only results relevant to the area
        # This reduces noise before sending to LLM (90 → ~20 results)
        area_keywords = self._get_area_keywords(area_name, area_info)
        filtered_results = []
        rejected_results = []

        for r in search_results:
            text = f"{r.get('title', '')} {r.get('snippet', '')}".lower()
            # Keep if: mentions area name, nearby areas, or looks like a restaurant listing
            is_relevant = (
                any(kw in text for kw in area_keywords)
                or any(kw in text for kw in ["restaurant", "cafe", "hawker", "food centre", "food court", "stall", "eating house"])
                or any(kw in text for kw in ["halal certified", "muis", "muslim owned", "no pork", "vegetarian", "vegan"])
            )
            # Reject if: clearly a blog/listicle/guide (not a specific restaurant)
            is_noise = any(kw in text for kw in ["best halal", "top 10", "top 20", "guide to", "list of", "where to eat"])

            if is_relevant and not is_noise:
                filtered_results.append(r)
            else:
                rejected_results.append(r)

        # If too aggressive, relax and include some rejected ones
        if len(filtered_results) < 5 and rejected_results:
            # Add back the rejected ones that at least mention food
            for r in rejected_results:
                text = f"{r.get('title', '')} {r.get('snippet', '')}".lower()
                if any(kw in text for kw in ["restaurant", "food", "halal", "cafe", "eat"]):
                    filtered_results.append(r)
                if len(filtered_results) >= 15:
                    break

        await _dbg("filter", f"📋 Pre-filter: {len(search_results)} → {len(filtered_results)} relevant results (rejected {len(rejected_results)} noise)",
                    {"kept": len(filtered_results), "rejected": len(rejected_results),
                     "area_keywords": area_keywords[:10],
                     "results": [{"title": r.get("title", "")[:80], "snippet": r.get("snippet", "")[:120], "url": r.get("url", "")[:100]} for r in filtered_results],
                     "rejected_sample": [r.get("title", "")[:60] for r in rejected_results[:5]]})

        # 3. Feed only filtered results to LLM (much smaller input)
        search_text = self._format_search_results(filtered_results[:30])

        extraction_prompt = f"""Extract all restaurant/food establishment names and their addresses from these search results.
Only include places that appear to be in or near {area_name}, Singapore.

Return ONLY a JSON array, no other text:
[
  {{"name": "Restaurant Name", "address": "Full address in Singapore", "type": "restaurant", "cuisine": "cuisine type if mentioned"}},
  ...
]

Search results:
{search_text}"""

        await _dbg("llm", "🧠 Sending search results to LLM for extraction...")

        llm_response = await self._call_llm(
            system=self.prompt_discovery,
            user=extraction_prompt,
            json_mode=True,
        )

        # 4. Parse LLM response
        extracted = self._parse_json_array(llm_response)
        if not extracted:
            await _dbg("llm", "⚠️ LLM extraction returned no results, falling back to regex")
            extracted = self._regex_extract_places(search_results)

        await _dbg("llm", f"🧠 LLM extracted {len(extracted)} places",
                    {"places": [{"name": e.get("name", "?"), "address": e.get("address", "")} for e in extracted[:15]]})

        for i, item in enumerate(extracted[:15]):
            print(f"    [{i+1}] {item.get('name', '?')} | {item.get('address', 'no address')}")

        # 5. Geocode each extracted place (multi-strategy)
        places = []
        for item in extracted[:25]:  # cap at 25 to limit geocoding time
            name = item.get("name", "").strip()
            address = item.get("address", "").strip()
            if not name:
                continue

            # Clean address for geocoding
            import re as _re
            clean_addr = address
            # Replace "Blk" / "Block" with number only (SG HDB notation)
            clean_addr = _re.sub(r"\b[Bb]l(?:oc)?k\.?\s*", "", clean_addr)
            # Remove unit numbers (#01-03, #B1-15/16)
            clean_addr = _re.sub(r"#[\w/]+-[\w/]+[,\s]*", "", clean_addr)
            # Remove "No." prefix
            clean_addr = _re.sub(r"\bNo\.?\s*", "", clean_addr)
            # Collapse multiple commas and whitespace
            clean_addr = _re.sub(r"\s*,\s*,", ",", clean_addr)
            clean_addr = _re.sub(r"\s{2,}", " ", clean_addr).strip(", ")

            # Extract postal code if present (Singapore: 6 digits)
            postal = ""
            postal_match = _re.search(r"\b(\d{6})\b", address)
            if postal_match:
                postal = postal_match.group(1)

            # Try multiple geocoding strategies (first success wins)
            geo = None
            strategies = [
                # Strategy 1: address only (without restaurant name)
                clean_addr if clean_addr else None,
                # Strategy 2: just postal code + Singapore
                f"Singapore {postal}" if postal else None,
                # Strategy 3: street name + Singapore
                _re.split(r",", clean_addr)[0] + ", Singapore" if clean_addr else None,
                # Strategy 4: restaurant name + area
                f"{name}, Singapore",
            ]

            for strategy in strategies:
                if not strategy:
                    continue
                geo = await self.geocoder.geocode(strategy)
                if geo:
                    await _dbg("geocode", f"📍 Geocoded: '{name}' → {geo['lat']:.4f}, {geo['lng']:.4f}",
                               {"strategy": strategy[:60], "lat": geo["lat"], "lng": geo["lng"]})
                    break

            if not geo:
                await _dbg("geocode", f"❌ Failed to geocode: '{name}'", {"address": address})
                continue

            place = {
                "name": name,
                "lat": geo["lat"],
                "lng": geo["lng"],
                "address": address or geo.get("display_name", ""),
                "type": item.get("type", "restaurant"),
                "cuisine": item.get("cuisine", ""),
                "halalStatus": "unverified",  # will be updated in Phase 2
                "source": "ai_agent",
            }
            places.append(place)

        await _dbg("geocode", f"📍 Geocoded {len(places)} of {len(extracted)} places",
                    {"geocoded": len(places), "total": len(extracted)})

        # 6. Filter by radius + deduplicate
        before_filter = len(places)
        places = self.geocoder.filter_by_radius(places, lat, lng, radius)
        places = self._deduplicate_places(places)

        await _dbg("filter", f"📍 Radius filter: {before_filter} → {len(places)} within {radius}m",
                    {"before": before_filter, "after": len(places), "radius": radius,
                     "places": [{"name": p["name"], "distance": p.get("distance", "?")} for p in places]})

        self._cache[cache_key] = places
        return places

    # ═══════════════════════════════════════════════════════════════
    # PHASE 2 — RESEARCH
    # ═══════════════════════════════════════════════════════════════

    async def research_place(self, place: Dict) -> Dict:
        """
        Phase 2: Deep research on a specific place.

        Flow:
        1. Run targeted SearXNG searches (general, halal, menu, reviews, etc.)
        2. Scrape top URLs for content
        3. Check MUIS halal directory
        4. Feed all evidence to LLM for classification
        5. Find images
        """
        name = place.get("name", "Unknown")
        cache_key = f"research_{name}_{place.get('lat', 0):.3f}"
        if cache_key in self._cache:
            print(f"  📦 Cache hit: {cache_key}")
            return self._cache[cache_key]

        print(f"🔬 Phase 2: Researching '{name}'")

        # 1. Targeted searches
        search_results = await self.search.search_place_details(name)

        # 2. Scrape top 5 most relevant URLs
        all_urls = []
        for category, results in search_results.items():
            for r in results[:2]:  # top 2 per category
                url = r.get("url", "")
                if url and url not in all_urls:
                    all_urls.append(url)

        scraped_pages = await self.scraper.scrape_multiple(all_urls[:8])

        # 3. Check MUIS
        muis_result = await self.scraper.scrape_muis(name)

        # 3b. Direct scrape halal directories (halaltag.com, etc.)
        halal_directory_urls = [
            f"https://www.halaltag.com/search?q={name.replace(' ', '+')}",
            f"https://www.halaltrip.com/search/?q={name.replace(' ', '+')}+Singapore",
        ]
        directory_pages = await self.scraper.scrape_multiple(halal_directory_urls, max_concurrent=3)

        # 4. Compile all evidence
        evidence = {
            "search_snippets": {},
            "scraped_content": [],
            "muis_check": muis_result,
            "images": [],
        }

        for category, results in search_results.items():
            evidence["search_snippets"][category] = [
                {"title": r["title"], "snippet": r["snippet"]}
                for r in results[:3]
            ]

        for page in scraped_pages:
            if isinstance(page, dict) and page.get("success"):
                evidence["scraped_content"].append({
                    "url": page["url"],
                    "title": page["title"],
                    "text": page["text"][:1500],  # truncate for LLM
                    "halal_related": any(
                        kw in page["text"].lower()
                        for kw in ["halal", "muis", "muslim", "pork", "lard", "vegan", "vegetarian"]
                    ),
                })
                # Collect images
                if page.get("og_image"):
                    evidence["images"].append({
                        "url": page["og_image"],
                        "caption": page["title"],
                        "source": page["url"],
                    })

        # Add halal directory scrape results to evidence
        for page in directory_pages:
            if isinstance(page, dict) and page.get("success"):
                evidence["scraped_content"].append({
                    "url": page["url"],
                    "title": page["title"],
                    "text": page["text"][:1500],
                    "halal_related": True,  # these are halal directories
                    "source_type": "halal_directory",
                })
                print(f"  📗 Halal directory: {page['url'][:60]} ({len(page['text'])} chars)")

        # 5. LLM classification
        evidence_text = self._format_evidence(name, place, evidence)

        classification_prompt = f"""Based on the following evidence about "{name}", classify its halal status and extract key facts.

{evidence_text}

Return ONLY a JSON object:
{{
  "status": "halal_certified|muslim_owned|no_pork_no_lard|halal_friendly|vegetarian|vegan|unverified",
  "confidence": "high|medium|low",
  "reasoning": "Step by step explanation citing evidence",
  "certificate": "MUIS cert number or null",
  "cuisine": "cuisine type",
  "price_range": "budget/moderate/premium with S$ if found",
  "popular_dishes": ["dish1", "dish2"],
  "hours": "operating hours if found",
  "phone": "phone number if found",
  "website": "website URL if found",
  "address": "full address if found"
}}"""

        llm_response = await self._call_llm(
            system=self.prompt_research,
            user=classification_prompt,
            json_mode=True,
        )

        classification = self._parse_json_object(llm_response)
        if not classification:
            classification = {"status": "unverified", "confidence": "low", "reasoning": "LLM parsing failed"}

        # Add category metadata
        status = classification.get("status", "unverified")
        if status in HALAL_CATEGORIES:
            cat = HALAL_CATEGORIES[status]
            classification["label"] = cat["label"]
            classification["icon"] = cat["icon"]
            classification["badge_color"] = cat["badge_color"]
        else:
            classification["status"] = "unverified"
            classification["label"] = "Unverified"
            classification["icon"] = "⚪"
            classification["badge_color"] = "gray"

        research = {
            "classification": classification,
            "evidence": evidence,
            "images": evidence["images"][:5],
            "llm_calls": list(self._llm_calls),  # include LLM calls for debug
        }

        # Clear calls for next restaurant
        self._llm_calls = []

        print(f"✅ Phase 2 complete: '{name}' → {classification.get('label')} ({classification.get('confidence')})")

        self._cache[cache_key] = research
        return research

    # ═══════════════════════════════════════════════════════════════
    # PHASE 3 — ARTICLE WRITING
    # ═══════════════════════════════════════════════════════════════

    async def write_article(self, place: Dict, research: Dict) -> Dict:
        """
        Phase 3: Write a warm article about the restaurant.

        The LLM writes based on the research evidence only — no hallucination.
        """
        name = place.get("name", "Unknown")
        cache_key = f"article_{name}_{place.get('lat', 0):.3f}"
        if cache_key in self._cache:
            print(f"  📦 Cache hit: {cache_key}")
            return self._cache[cache_key]

        print(f"✍️ Phase 3: Writing article for '{name}'")

        classification = research.get("classification", {})

        # Build a facts summary for the LLM
        facts = f"""Restaurant: {name}
Location: {place.get('address', 'Singapore')}
Halal Status: {classification.get('label', 'Unverified')} ({classification.get('confidence', 'low')} confidence)
Reasoning: {classification.get('reasoning', 'N/A')}
Cuisine: {classification.get('cuisine', place.get('cuisine', 'Not specified'))}
Price Range: {classification.get('price_range', 'Not specified')}
Popular Dishes: {', '.join(classification.get('popular_dishes', [])) or 'Not specified'}
Hours: {classification.get('hours', 'Not specified')}
Phone: {classification.get('phone', 'Not specified')}
Website: {classification.get('website', 'Not specified')}
Certificate: {classification.get('certificate', 'None found')}"""

        article_prompt = f"""Write an article about this restaurant based ONLY on the facts below.
Do NOT invent any details not listed in the facts.

{facts}

Return ONLY a JSON object:
{{
  "title": "Short catchy title",
  "article": "The full article (150-250 words) with **bold** for emphasis",
  "tags": ["tag1", "tag2", "tag3"]
}}"""

        llm_response = await self._call_llm(
            system=self.prompt_article,
            user=article_prompt,
            json_mode=True,
        )

        article = self._parse_json_object(llm_response)
        if not article:
            # Fallback: generate a basic article without LLM
            article = {
                "title": name,
                "article": f"**{name}** is a {classification.get('label', '').lower()} establishment in Singapore. "
                           f"Serving {classification.get('cuisine', 'various')} cuisine. "
                           f"Visit to experience their offerings!",
                "tags": [classification.get("status", "unverified")],
            }

        # Attach images from research
        article["images"] = research.get("images", [])

        # Attach classification for the frontend badge
        article["classification"] = classification

        print(f"✅ Phase 3 complete: article for '{name}' ({len(article.get('article', ''))} chars)")

        self._cache[cache_key] = article
        return article

    # ─── Helper methods ───────────────────────────────────────────

    def _get_area_keywords(self, area_name: str, area_info: Optional[Dict]) -> List[str]:
        """Generate area-specific keywords for pre-filtering search results."""
        keywords = []

        # Primary area name (lowercase)
        if area_name and area_name != "Singapore":
            keywords.append(area_name.lower())
            # Also add parts of the name (e.g., "Bishan East" → "bishan")
            for part in area_name.lower().split():
                if len(part) > 3 and part not in ["east", "west", "north", "south", "central"]:
                    keywords.append(part)

        # Add neighbourhood, suburb, road from reverse geocode
        if area_info:
            for key in ["neighbourhood", "suburb", "road", "city"]:
                val = area_info.get(key, "").lower().strip()
                if val and val != "singapore" and len(val) > 2:
                    keywords.append(val)
                    # Add parts for compound names
                    for part in val.split():
                        if len(part) > 3:
                            keywords.append(part)

        # Add postcode if available
        if area_info and area_info.get("postcode"):
            keywords.append(area_info["postcode"])

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                unique.append(kw)

        return unique

    def _format_search_results(self, results: List[Dict]) -> str:
        """Format search results into text for the LLM."""
        lines = []
        for i, r in enumerate(results[:30], 1):
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            url = r.get("url", "")
            lines.append(f"{i}. [{title}]({url})\n   {snippet}")
        return "\n\n".join(lines)

    def _format_evidence(self, name: str, place: Dict, evidence: Dict) -> str:
        """Format all gathered evidence into text for the LLM."""
        parts = [f"=== Evidence for: {name} ===\n"]

        # MUIS check
        muis = evidence.get("muis_check", {})
        if muis.get("certified"):
            parts.append(f"MUIS CHECK: ✅ FOUND in MUIS certified list")
            if muis.get("certificate_number"):
                parts.append(f"Certificate: {muis['certificate_number']}")
        else:
            parts.append(f"MUIS CHECK: ❌ Not found in MUIS directory")

        for snippet in muis.get("snippets", []):
            parts.append(f"  Note: {snippet}")

        # Search snippets
        for category, snippets in evidence.get("search_snippets", {}).items():
            if snippets:
                parts.append(f"\n--- Search: {category} ---")
                for s in snippets:
                    parts.append(f"• {s['title']}: {s['snippet']}")

        # Scraped page content
        for page in evidence.get("scraped_content", [])[:5]:
            if page.get("halal_related"):
                parts.append(f"\n--- Scraped: {page['title']} ({page['url'][:60]}...) ---")
                parts.append(page["text"][:800])

        return "\n".join(parts)

    def _parse_json_array(self, text: str) -> List[Dict]:
        """Try to parse a JSON array from LLM response."""
        text = text.strip()
        # Try direct parse
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        # Try extracting JSON from markdown code block
        match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding array in the text
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return []

    def _parse_json_object(self, text: str) -> Optional[Dict]:
        """Try to parse a JSON object from LLM response."""
        text = text.strip()
        try:
            result = json.loads(text)
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return None

    def _regex_extract_places(self, search_results: List[Dict]) -> List[Dict]:
        """Fallback: extract restaurant names from search results using regex."""
        places = []
        seen_names = set()
        for r in search_results:
            title = r.get("title", "")
            snippet = r.get("snippet", "")
            # Try to extract a clean restaurant name from the title
            # Remove common suffixes like "- Review", "| Menu", etc.
            name = re.split(r"\s*[-|–—·•]\s*", title)[0].strip()
            if name and len(name) > 2 and name.lower() not in seen_names:
                seen_names.add(name.lower())
                places.append({
                    "name": name,
                    "address": "",
                    "type": "restaurant",
                    "cuisine": "",
                })
        return places[:20]

    def _deduplicate_places(self, places: List[Dict]) -> List[Dict]:
        """Remove duplicate places by name similarity + proximity."""
        unique = []
        seen = set()
        for p in places:
            key = re.sub(r"[^a-z0-9]", "", p["name"].lower())
            if key not in seen:
                seen.add(key)
                unique.append(p)
        return unique
