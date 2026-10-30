"""Every LLM prompt in one file. Rewrite the wording for your domain; keep the {placeholders}."""

EXTRACTION_PROMPT = """You are an analyst reading a document for {domain_description}.

Extract:
1. title, a one-paragraph summary, and the publication date (YYYY-MM-DD) if visible.
2. Every distinct finding relevant to the task. For each finding give:
   - theme_hint: a short label (2-6 words)
   - direction: negative | positive | neutral | mixed
   - severity: high | medium | low (based on how strongly the document words it)
   - evidence_text: a VERBATIM quote from the document (max 300 characters). Do not paraphrase.
   - page_ref: page number if known, else null
   - confidence: 0.0 to 1.0

Context from the file path (use if the document does not say):
- source: {source}
- year: {year}

Return ONLY JSON matching the schema. If there are no findings return an empty list.
"""

CONSOLIDATION_PROMPT = """You are consolidating free-text theme labels into a short list of canonical themes.

Rules:
- Produce at most {max_themes} canonical themes for all labels together.
- Group labels that describe the same underlying theme. Do not group unrelated labels.
- Use short, portfolio-level names (2-6 words). Do not name a single event or a single company.
{preferred_block}
- Every input label must appear in exactly one group, spelled exactly as given.

Labels (with how many times each occurs):
{labels}

Return ONLY JSON: {{"groups": [{{"canonical": "Theme name", "members": ["label 1", "label 2"]}}]}}
"""
