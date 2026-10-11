"""Rule-based hallucination guards (traditional code, not LLM).

These run AFTER the LLM steps and are deterministic, so they can't be
talked out of their job:
  1. citation check  - every source_id must exist; requirements without a
                       valid citation are demoted to "assumption"
  2. quote check     - extracted quotes must really appear in the input
  3. watch-list      - well-known "hallucination magnets" (biometric, GPS,
                       SSO, 99.9%...) that appear in output but not in input
  4. number check    - numbers in a requirement that the customer never said
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from .schemas import Extraction, Requirement, RequirementsDraft

# Terms LLMs love to add to requirement specs. Each entry: canonical -> variants.
WATCHLIST: dict[str, list[str]] = {
    "biometric": ["biometric", "fingerprint", "face id", "facial recognition", "face recognition"],
    "GPS/geolocation": ["gps", "geolocation", "geo-fenc", "geofenc", "location tracking", "location-based"],
    "SSO/OAuth": ["sso", "single sign-on", "oauth", "saml", "ldap", "active directory"],
    "2FA/MFA": ["2fa", "mfa", "two-factor", "multi-factor", "otp"],
    "email/SMS notifications": ["email notification", "sms", "push notification"],
    "specific file formats": ["pdf", "csv", "excel", "xlsx"],
    "blockchain": ["blockchain"],
    "AI/ML": ["machine learning", "artificial intelligence", " ai ", "ai-powered"],
    "encryption standards": ["aes-256", "aes 256", "tls 1.", "encryption at rest"],
    "compliance regimes": ["gdpr", "hipaa", "soc 2", "pci"],
    "uptime/SLA": ["uptime", "99.9", "sla"],
    "cloud vendors": ["aws", "azure", "google cloud", "gcp"],
    "QR/NFC/RFID": ["qr code", "nfc", "rfid"],
    "payroll integration": ["payroll"],
}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def valid_ids(ids: list[str], known: set[str]) -> list[str]:
    out = []
    for i in ids:
        i = i.strip().upper().strip("[]")
        if i in known and i not in out:
            out.append(i)
    return out


def quote_in_source(quote: str, source: str) -> bool:
    q, s = _norm(quote), _norm(source)
    if not q:
        return False
    if q in s:
        return True
    # tolerate small edits (punctuation, plural) - best matching window
    m = SequenceMatcher(None, s, q).find_longest_match(0, len(s), 0, len(q))
    return m.size / max(len(q), 1) >= 0.8


def watchlist_hits(text: str, source_text: str) -> list[str]:
    t, src = f" {_norm(text)} ", f" {_norm(source_text)} "
    hits = []
    for name, variants in WATCHLIST.items():
        if any(v in t for v in variants) and not any(v in src for v in variants):
            hits.append(name)
    return hits


def foreign_numbers(text: str, source_text: str) -> list[str]:
    cleaned = re.sub(r"\b(?:FR|NFR|US|S)-?\d+\b", "", text)
    nums = set(re.findall(r"\d+(?:\.\d+)?", cleaned))
    src_nums = set(re.findall(r"\d+(?:\.\d+)?", source_text))
    return sorted(nums - src_nums)


def check_extraction(ex: Extraction, sentences: list[dict]) -> tuple[Extraction, list[str]]:
    """Drop invalid IDs; flag quotes that aren't in the cited sentence."""
    known = {s["id"] for s in sentences}
    by_id = {s["id"]: s["text"] for s in sentences}
    notes: list[str] = []
    for a in ex.actors:
        a.source_ids = valid_ids(a.source_ids, known)
    kept = []
    for n in ex.needs:
        n.source_ids = valid_ids(n.source_ids, known)
        cited = " ".join(by_id[i] for i in n.source_ids)
        if not n.source_ids:
            notes.append(f"Dropped extracted need without a valid citation: '{n.need}'")
            continue
        if n.quote and not quote_in_source(n.quote, cited):
            # quote not found in cited sentence - try whole text before giving up
            full = " ".join(by_id.values())
            if not quote_in_source(n.quote, full):
                notes.append(f"Quote not found in input, dropped: '{n.quote}'")
                continue
        kept.append(n)
    ex.needs = kept
    for v in ex.vague_terms:
        v.source_ids = valid_ids(v.source_ids, known)
    return ex, notes


def _check_req(r: Requirement, known: set[str], by_id: dict, full_text: str) -> None:
    r.source_ids = valid_ids(r.source_ids, known)
    if not r.source_ids and r.origin != "assumption":
        r.origin = "assumption"
        r.validation_notes.append("No valid source citation - demoted to assumption.")
    cited = " ".join(by_id[i] for i in r.source_ids) or full_text
    for hit in watchlist_hits(r.text, full_text):
        r.validation_notes.append(f"Introduces '{hit}', which the customer never mentioned.")
    for num in foreign_numbers(r.text, full_text):
        r.validation_notes.append(f"Contains the value '{num}', which is not in the input.")


def check_draft(draft: RequirementsDraft, sentences: list[dict]) -> RequirementsDraft:
    known = {s["id"] for s in sentences}
    by_id = {s["id"]: s["text"] for s in sentences}
    full = " ".join(by_id.values())
    for r in draft.functional_requirements + draft.non_functional_requirements:
        _check_req(r, known, by_id, full)
    for a in draft.actors:
        a.source_ids = valid_ids(a.source_ids, known)
    return draft


def text_hallucination_scan(texts: list[str], source_text: str) -> list[dict]:
    """Used by the evaluator and the UI summary."""
    out = []
    for t in texts:
        hits = watchlist_hits(t, source_text)
        if hits:
            out.append({"text": t, "terms": hits})
    return out
