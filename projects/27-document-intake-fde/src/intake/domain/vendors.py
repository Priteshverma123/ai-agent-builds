"""Vendor master resolution: map whatever name is printed on a document to one vendor_id."""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from .models import Vendor

LEGAL_SUFFIXES = re.compile(r"\b(inc|incorporated|co|company|corp|corporation|llc|ltd|gmbh)\b")


def normalize_name(name: str) -> str:
    name = re.sub(r"[^a-z0-9 ]", " ", name.lower())
    return " ".join(LEGAL_SUFFIXES.sub(" ", name).split())


class VendorMaster:
    def __init__(self, vendors: list[Vendor], fuzzy_threshold: float = 0.88) -> None:
        self.vendors = {v.vendor_id: v for v in vendors}
        self._threshold = fuzzy_threshold
        self._by_name = {normalize_name(n): v for v in vendors for n in [v.name, *v.aliases]}
        self._by_tax = {v.tax_id: v for v in vendors if v.tax_id}

    def resolve(self, name: str, tax_id: str | None = None) -> tuple[Vendor | None, str]:
        """Return (vendor, how) where how is 'tax id', 'name', 'fuzzy 0.93' or 'no match'."""
        if tax_id and tax_id in self._by_tax:
            return self._by_tax[tax_id], "tax id"
        key = normalize_name(name)
        if key in self._by_name:
            return self._by_name[key], "name"
        best, score = None, 0.0
        for known, vendor in self._by_name.items():
            ratio = SequenceMatcher(None, key, known).ratio()
            if ratio > score:
                best, score = vendor, ratio
        if best and score >= self._threshold:
            return best, f"fuzzy {score:.2f}"
        return None, "no match"

    def get(self, vendor_id: str) -> Vendor | None:
        return self.vendors.get(vendor_id)
