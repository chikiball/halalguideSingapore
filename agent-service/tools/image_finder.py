"""Image finder tool — Step 9."""
from typing import List, Dict


class ImageFinderTool:
    def __init__(self, searxng_url: str):
        self.searxng_url = searxng_url
        print("  🖼️  ImageFinderTool ready")

    async def find_images(self, name: str, cuisine: str = "") -> List[Dict]:
        """Find images for a restaurant. Returns list of {url, caption, source}."""
        # TODO: Implement in Step 9
        return []
