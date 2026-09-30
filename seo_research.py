"""Optional SEO research primitives inspired by OpenSEO patterns.

This module is provider-neutral: it performs local analysis without inventing
search-volume or ranking data. Live keyword/SERP/backlink providers can be
added behind the same interface later.
"""
from __future__ import annotations
import re
from collections import Counter
from typing import Any, Dict, List


_STOP = {
    "the","a","an","and","or","for","to","of","in","on","with","by","from",
    "is","are","was","were","this","that","your","our","best","new"
}


def extract_terms(text: str) -> List[str]:
    words = re.findall(r"[a-z0-9][a-z0-9-]{2,}", (text or "").lower())
    return [w for w in words if w not in _STOP]


def cluster_keywords(keywords: List[str]) -> List[Dict[str, Any]]:
    groups: Dict[str, List[str]] = {}
    for raw in keywords or []:
        phrase = " ".join(extract_terms(raw))
        if not phrase:
            continue
        root = extract_terms(phrase)[0]
        groups.setdefault(root, []).append(raw.strip())
    return [
        {"topic": topic, "keywords": sorted(set(values)), "count": len(set(values))}
        for topic, values in sorted(groups.items(), key=lambda item: (-len(set(item[1])), item[0]))
    ]


def audit_product_page(title: str, description: str, url_slug: str = "", meta_description: str = "") -> Dict[str, Any]:
    issues: List[Dict[str, str]] = []
    title = (title or "").strip()
    description = (description or "").strip()
    meta_description = (meta_description or "").strip()
    slug = (url_slug or "").strip()

    if not title:
        issues.append({"severity": "high", "issue": "Missing product title"})
    elif len(title) > 60:
        issues.append({"severity": "medium", "issue": "Title exceeds ~60 characters"})

    if not description:
        issues.append({"severity": "high", "issue": "Missing product description"})
    elif len(description) < 120:
        issues.append({"severity": "medium", "issue": "Description is short for useful search context"})

    if not meta_description:
        issues.append({"severity": "medium", "issue": "Missing meta description"})
    elif len(meta_description) > 160:
        issues.append({"severity": "medium", "issue": "Meta description exceeds ~160 characters"})

    if not slug:
        issues.append({"severity": "medium", "issue": "Missing URL slug"})
    elif not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug):
        issues.append({"severity": "low", "issue": "URL slug contains non-SEO-friendly characters"})

    return {
        "status": "needs_attention" if issues else "pass",
        "issue_count": len(issues),
        "issues": issues,
        "checks": {
            "title_length": len(title),
            "description_length": len(description),
            "meta_description_length": len(meta_description),
            "slug": slug,
        },
    }


def build_research_report(title: str, description: str, keywords: List[str] | None = None) -> Dict[str, Any]:
    seed_terms = list(keywords or [])
    if not seed_terms:
        seed_terms = extract_terms(f"{title} {description}")
    return {
        "title": title,
        "keyword_clusters": cluster_keywords(seed_terms),
        "page_audit": audit_product_page(title, description),
        "data_sources": ["local_content_analysis"],
        "live_data_required": True,
        "note": "No search volume, rankings, backlink counts, or competitor claims are fabricated.",
    }
