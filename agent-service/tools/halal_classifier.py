"""Halal classifier — Step 7."""
from typing import Dict

# All classification categories
HALAL_CATEGORIES = {
    "halal_certified": {
        "label": "Halal Certified",
        "icon": "☪️",
        "badge_color": "green",
        "description": "MUIS halal certified",
    },
    "muslim_owned": {
        "label": "Muslim Owned",
        "icon": "🟢",
        "badge_color": "green",
        "description": "Muslim-owned, serves halal food",
    },
    "no_pork_no_lard": {
        "label": "No Pork No Lard",
        "icon": "🚫🐷",
        "badge_color": "blue",
        "description": "No pork and no lard, not halal certified",
    },
    "halal_friendly": {
        "label": "Halal Friendly",
        "icon": "🔵",
        "badge_color": "blue",
        "description": "Offers halal options",
    },
    "vegetarian": {
        "label": "Vegetarian",
        "icon": "🌿",
        "badge_color": "teal",
        "description": "Fully vegetarian, safe for Muslims",
    },
    "vegan": {
        "label": "Vegan",
        "icon": "🌱",
        "badge_color": "teal",
        "description": "Fully vegan, safe for Muslims",
    },
    "unverified": {
        "label": "Unverified",
        "icon": "⚪",
        "badge_color": "gray",
        "description": "Not enough evidence",
    },
}


class HalalClassifier:
    def __init__(self, base_url: str, model: str):
        self.base_url = base_url
        self.model = model
        self.categories = HALAL_CATEGORIES
        print(f"  ☪️  HalalClassifier ready | model={model}")

    async def classify(self, place: Dict, evidence: Dict) -> Dict:
        """
        Classify halal status based on evidence.
        Returns:
        {
            status: one of HALAL_CATEGORIES keys,
            label: human-readable label,
            icon: emoji icon,
            confidence: "high" | "medium" | "low",
            reasoning: str,
            certificate: str or None (MUIS cert number),
        }
        """
        # TODO: Implement in Step 7
        return {
            "status": "unverified",
            "label": "Unverified",
            "icon": "⚪",
            "confidence": "low",
            "reasoning": "",
            "certificate": None,
        }
