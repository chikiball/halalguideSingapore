"""Halal classifier — Step 7."""
from typing import Dict


class HalalClassifier:
    def __init__(self, ollama_url: str, model: str):
        self.ollama_url = ollama_url
        self.model = model
        print(f"  ☪️  HalalClassifier ready | model={model}")

    async def classify(self, place: Dict, evidence: Dict) -> Dict:
        """
        Classify halal status based on evidence.
        Returns {status, confidence, reasoning, certificate}.
        """
        # TODO: Implement in Step 7
        return {"status": "unverified", "confidence": 0.0, "reasoning": "", "certificate": None}
