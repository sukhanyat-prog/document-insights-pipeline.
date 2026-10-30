"""Fictional sample data for the demo. Every company, document and number here is invented."""

from __future__ import annotations

import random

YEARS = (2026, 2025)

SOURCES = [
    "Northwind Research",
    "Contoso Insights",
    "Fabrikam Analytics",
    "Tailspin Advisory",
    "Litware Group",
    "Adventure Works Review",
]

# canonical theme -> the different phrases the "model" might use for it in different documents
THEMES: dict[str, list[str]] = {
    "Demand and Market Share": ["demand weakening", "Softer customer demand", "market share loss", "shrinking market share"],
    "Regulation and Policy": ["new regulation", "regulatory tightening", "compliance burden", "policy uncertainty"],
    "Technology Disruption": ["AI disruption", "technology disruption", "automation of core services", "new digital entrants"],
    "Cost and Margin Pressure": ["cost pressure", "Cost Pressures", "margin squeeze", "rising input costs", "wage inflation"],
    "Talent and Capability": ["talent shortage", "skills gap", "difficulty hiring"],
    "Cyber and Data Security": ["cyber attack", "data breach risk", "ransomware"],
    "Climate and Sustainability": ["climate transition risk", "ESG disclosure"],
}

# how often each theme appears in the documents of a year (relative weights)
WEIGHTS = {
    2026: {"Demand and Market Share": 6, "Regulation and Policy": 5, "Technology Disruption": 8,
           "Cost and Margin Pressure": 9, "Talent and Capability": 3, "Cyber and Data Security": 4,
           "Climate and Sustainability": 2},
    2025: {"Demand and Market Share": 7, "Regulation and Policy": 4, "Technology Disruption": 4,
           "Cost and Margin Pressure": 6, "Talent and Capability": 4, "Cyber and Data Security": 3,
           "Climate and Sustainability": 1},
}

# a vague label the model was not confident about: it stays below the confidence floor
WEAK_LABELS = ["general uncertainty", "misc commentary"]

# the reference table a user would load (internal view / baseline): theme, value 0-100, owner
REFERENCE = {
    2026: [
        ("Demand and Market Share", 72, "Strategy"),
        ("Regulation and Policy", 55, "Legal"),
        ("Technology Disruption", 40, "Product"),
        ("Cost and Margin Pressure", 35, "Finance"),
        ("Talent and Capability", 60, "People"),
        ("Cyber and Data Security", 80, "Security"),
        ("Supply Chain Disruption", 65, "Operations"),   # in the reference, never mentioned: a blind spot
    ],
    2025: [
        ("Demand and Market Share", 70, "Strategy"),
        ("Regulation and Policy", 50, "Legal"),
        ("Technology Disruption", 45, "Product"),
        ("Cost and Margin Pressure", 55, "Finance"),
        ("Talent and Capability", 55, "People"),
    ],
}

TITLES = ["Sector Outlook", "Annual Review", "Industry Briefing", "Market Watch"]
EVIDENCE = "Illustrative quote about {label}."


def build(year: int) -> tuple[list[dict], list[dict]]:
    """Return (document rows, finding rows) for one year, always the same for the same year."""
    rng = random.Random(year)
    themes = list(WEIGHTS[year])
    weights = [WEIGHTS[year][t] for t in themes]
    documents, findings = [], []

    for s_index, source in enumerate(SOURCES):
        for d_index in range(2 if s_index < 3 else 1):
            doc_id = f"{year}-{s_index + 1}{chr(97 + d_index)}"
            rows = []
            for _ in range(rng.randint(3, 6)):
                theme = rng.choices(themes, weights)[0]
                label = rng.choice(THEMES[theme])
                rows.append({
                    "doc_id": doc_id, "source": source, "period_year": year, "raw_label": label,
                    "direction": rng.choices(["negative", "neutral", "positive"], [6, 2, 1])[0],
                    "severity": rng.choices(["high", "medium", "low"], [4, 4, 2])[0],
                    "confidence": round(rng.uniform(0.62, 0.97), 2),
                    "evidence_text": EVIDENCE.format(label=label), "page_ref": rng.randint(1, 30),
                })
            if rng.random() < 0.6:  # one vague, low-confidence finding in some documents
                label = rng.choice(WEAK_LABELS)
                rows.append({"doc_id": doc_id, "source": source, "period_year": year, "raw_label": label,
                             "direction": "neutral", "severity": "low", "confidence": round(rng.uniform(0.2, 0.4), 2),
                             "evidence_text": EVIDENCE.format(label=label), "page_ref": rng.randint(1, 30)})
            findings.extend(rows)
            documents.append({
                "doc_id": doc_id, "source": source, "period_year": year,
                "title": f"{source} - {rng.choice(TITLES)} {year}",
                "findings_count": len(rows),
                "parsed_at": f"{year}-{rng.randint(1, 9):02d}-{rng.randint(10, 28):02d}T09:{rng.randint(10, 59)}:00",
            })
    return documents, findings


def label_groups(label_counts: dict[str, int], preferred: list[str]) -> list[dict]:
    """Stand-in for the consolidation model call: group known phrases under their theme."""
    groups = []
    for theme, labels in THEMES.items():
        members = [label for label in label_counts if label in labels]
        if members:
            groups.append({"canonical": theme, "members": members})
    return groups  # weak labels are left out on purpose: the pipeline still maps them (low confidence)


def reference_rows(year: int) -> list[dict]:
    return [{"period_year": year, "canonical_theme": t, "reference_value": float(v), "owner": o}
            for t, v, o in REFERENCE.get(year, [])]
