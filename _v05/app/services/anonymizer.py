"""Anonymisation et dé-anonymisation par rechercher/remplacer."""
from __future__ import annotations

import re


class Anonymizer:
    def __init__(self, mappings: dict[str, str]) -> None:
        """
        Args:
            mappings: {mot_réel: alias} — ex: {"Ministère des Armées": "CLIENT"}
        """
        self.mappings = mappings
        # Sort by length descending to avoid partial replacements
        self.sorted_keys = sorted(mappings.keys(), key=len, reverse=True)

    def anonymize(self, text: str) -> str:
        """Case-insensitive search/replace of real words with aliases."""
        for key in self.sorted_keys:
            pattern = re.compile(re.escape(key), re.IGNORECASE)
            text = pattern.sub(self.mappings[key], text)
        return text

    def deanonymize(self, text: str) -> str:
        """Reverse: replace aliases back with real words."""
        reverse = {v: k for k, v in self.mappings.items()}
        sorted_keys = sorted(reverse.keys(), key=len, reverse=True)
        for key in sorted_keys:
            text = text.replace(key, reverse[key])
        return text
