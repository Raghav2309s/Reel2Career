from pathlib import Path
import json
import re
import subprocess
import sys
import time
from urllib.parse import urlparse


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[2]
APP_DIR = Path(__file__).resolve().parent

sys.path.insert(0, str(APP_DIR))

from database import (
    SessionLocal,
    Reel,
    Evidence,
    Analysis,
    Skill,
    ReelSkill,
    Action,
    Resource,
    ReelResource,
)

from github_discovery import extract_github_hints
from github_discovery_service import discover_github_candidates
from github_resolver import resolve_github_resource
from github_persistence import apply_github_resolution


# ============================================================
# CONFIGURATION
# ============================================================

OMNIROUTE = (
    BASE_DIR
    / "node_modules"
    / ".bin"
    / "omniroute.cmd"
)

MODEL = (
    "openrouter/minimax/minimax-m3:free"
)

PROMPT_DIR = (
    BASE_DIR
    / "vault"
    / "ai_prompts"
)

PROMPT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

MAX_AI_ATTEMPTS = 5

# A response can be syntactically invalid even when OmniRoute itself exits
# successfully.  Keep this separate from transport retries so a bad model
# response gets one fresh, smaller JSON-only attempt before the reel fails.
MAX_JSON_ATTEMPTS = 2

# Validation failures are usually recoverable model-format mistakes
# (missing summary, wrong support_level, unsupported extra detail, etc.).
# Give the model a focused correction attempt before quarantining the reel.
MAX_VALIDATION_ATTEMPTS = 2

AI_MAX_TOKENS = 8000

RETRY_DELAYS = [
    3,
    6,
    12,
    24,
    48,
]

ALLOWED_SOURCE_TYPES = {
    "caption",
    "transcript",
    "on_screen_ocr",
    "profile_bio",
    "external_metadata",
}

ALLOWED_SUPPORT_LEVELS = {
    "direct",
    "inference",
}

ABSOLUTE_HTTPS_URL_RE = re.compile(
    r"https://[^\s<>\[\]()\"']+",
    re.IGNORECASE,
)

MARKDOWN_HTTPS_LINK_RE = re.compile(
    r"^\[([^\]]*)\]\((https://[^)\s]+)\)$",
    re.IGNORECASE,
)


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(value):
    """
    Convert a value into a clean string.
    """
    if value is None:
        return ""

    return str(value).strip()


def normalize_whitespace(value):
    """
    Normalize whitespace for evidence-quote comparison.

    This intentionally does NOT aggressively normalize wording.
    The model must still quote actual evidence text.
    """
    value = clean_text(value)

    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def normalize_for_match(value):
    """
    Case-insensitive whitespace-normalized comparison.
    """
    value = normalize_whitespace(value)

    return value.casefold()


def extract_urls(text):
    """
    Extract complete absolute HTTPS URLs from plain text.

    Markdown-wrapped URLs are rejected.
    """
    if not text:
        return []

    urls = []

    for token in text.split():
        token = token.strip(
            ".,;:!?()[]{}<>\"'"
        )

        if not token.startswith("https://"):
            continue

        if "](" in token or "[" in token or "]" in token:
            continue

        if "..." in token or "â€¦" in token:
            continue

        if is_valid_https_url(token):
            if token not in urls:
                urls.append(token)

    return urls


BARE_HTTPS_DOMAIN_RE = re.compile(
    r"(?<![\w.-])"
    r"(?:www\.)?"
    r"(?:[a-zA-Z0-9-]+\.)+"
    r"[a-zA-Z]{2,}"
    r"(?:/[^\s<>\"\\]*)?",
    re.IGNORECASE,
)


def extract_evidence_resource_urls(text):
    """
    Extract complete resource URLs from evidence.

    Rules:
    - Accept complete absolute HTTPS URLs.
    - Accept complete bare GitHub repository URLs.
    - Reject damaged HTTPS such as https:/github.com/...
    - Reject Markdown-wrapped URLs.
    - Reject arbitrary OCR domain-like text.
    - Never infer, reconstruct, repair, or guess URLs.
    """
    if not text:
        return []

    urls = []

    # --------------------------------------------------------
    # 1. Reject Markdown links entirely
    # --------------------------------------------------------

    if re.search(
        r"\[[^\]]*\]\(\s*https://[^)\s]+\s*\)",
        text,
        re.IGNORECASE,
    ):
        text = re.sub(
            r"\[[^\]]*\]\(\s*https://[^)\s]+\s*\)",
            " ",
            text,
            flags=re.IGNORECASE,
        )

    # --------------------------------------------------------
    # 2. Complete raw HTTPS URLs only
    # --------------------------------------------------------

    raw_https_re = re.compile(
        r"(?<![\w:/])"
        r"https://"
        r"[^\s<>\[\](){}\"']+",
        re.IGNORECASE,
    )

    for match in raw_https_re.finditer(text):
        candidate = match.group(0).strip(
            ".,;:!?)]}>\"'"
        )

        if (
            "..." in candidate
            or "…" in candidate
            or "â€¦" in candidate
        ):
            continue

        if is_valid_https_url(candidate):
            if candidate not in urls:
                urls.append(candidate)

    # --------------------------------------------------------
    # 3. Reject damaged HTTPS tokens explicitly
    #
    # Example:
    #     https:/github.com/PrefectHQ/fastmcp
    # --------------------------------------------------------

    damaged_https_re = re.compile(
        r"(?<![\w:/])"
        r"https:/"
        r"(?!/)",
        re.IGNORECASE,
    )

    # We intentionally do not attempt to repair these.
    # Their presence has no effect on extraction.

    # --------------------------------------------------------
    # 4. Complete bare GitHub repository URLs only
    # --------------------------------------------------------

    github_bare_re = re.compile(
        r"(?<![\w./-])"
        r"github\.com/"
        r"[A-Za-z0-9_.-]+/"
        r"[A-Za-z0-9_.-]+"
        r"(?![A-Za-z0-9_.-])",
        re.IGNORECASE,
    )

    for match in github_bare_re.finditer(text):
        candidate = match.group(0).strip(
            ".,;:!?)]}>\"'"
        )

        if (
            "..." in candidate
            or "…" in candidate
            or "â€¦" in candidate
        ):
            continue

        candidate = "https://" + candidate

        if not is_valid_https_url(candidate):
            continue

        if candidate not in urls:
            urls.append(candidate)

    return urls


def is_valid_https_url(url):
    """
    Strict URL validation.

    Requirements:
    - absolute
    - HTTPS
    - valid hostname
    - no obvious truncation
    """
    if not isinstance(
        url,
        str,
    ):
        return False

    url = url.strip()

    if not url:
        return False

    if not url.lower().startswith(
        "https://"
    ):
        return False

    try:
        parsed = urlparse(url)
    except Exception:
        return False

    if parsed.scheme.lower() != "https":
        return False

    if not parsed.netloc:
        return False

    if "." not in parsed.netloc:
        return False

    if "..." in url:
        return False

    if "…" in url:
        return False

    if url.endswith(
        (
            "/?",
            "...",
            "…",
        )
    ):
        return False

    return True


def normalize_resource_url(url):
    """
    Normalize a resource URL from model output.

    Returns a complete absolute HTTPS URL, or None when the
    value is missing, truncated, malformed, or non-HTTPS.

    Does not invent, complete, or guess URLs.
    """
    if url is None:
        return None

    if not isinstance(
        url,
        str,
    ):
        return None

    url = url.strip()

    if not url:
        return None

    if "..." in url:
        return None

    if "…" in url:
        return None

    if (
        MARKDOWN_HTTPS_LINK_RE.fullmatch(
            url
        )
        or url.startswith("[")
        or "](" in url
        or ")(" in url
    ):
        return None

    if not is_valid_https_url(url):
        return None

    return url


def normalize_relevance(value):
    try:
        value = float(value)
    except (
        TypeError,
        ValueError,
    ):
        value = 0.0

    return max(
        0.0,
        min(
            1.0,
            value,
        ),
    )


def normalize_confidence(value):
    try:
        value = float(value)
    except (
        TypeError,
        ValueError,
    ):
        value = 0.0

    return max(
        0.0,
        min(
            1.0,
            value,
        ),
    )


def normalize_minutes(value):
    if value is None:
        return None

    try:
        value = int(value)
    except (
        TypeError,
        ValueError,
    ):
        return None

    if value < 0:
        return None

    return value


# ============================================================
# EVIDENCE SOURCE NORMALIZATION
# ============================================================

def normalize_source_type(value):
    """
    Convert project-specific evidence labels into the
    controlled provenance vocabulary.
    """
    value = clean_text(value).lower()

    mapping = {
        "caption": "caption",
        "instagram_caption": "caption",

        "transcript": "transcript",
        "audio_transcript": "transcript",
        "speech": "transcript",

        "ocr": "on_screen_ocr",
        "on_screen_ocr": "on_screen_ocr",
        "on-screen-ocr": "on_screen_ocr",

        "profile_bio": "profile_bio",
        "bio": "profile_bio",

        "external_metadata": "external_metadata",
        "metadata": "external_metadata",
        "external": "external_metadata",
    }

    return mapping.get(
        value,
        value,
    )


# ============================================================
# EVIDENCE TEXT EXTRACTION
# ============================================================

def flatten_content(value):
    """
    Convert arbitrary JSON evidence content into searchable
    text while retaining all textual material.
    """
    if value is None:
        return ""

    if isinstance(
        value,
        str,
    ):
        return value

    if isinstance(
        value,
        (int, float, bool),
    ):
        return str(value)

    if isinstance(
        value,
        list,
    ):
        parts = []

        for item in value:
            text = flatten_content(item)

            if text:
                parts.append(text)

        return "\n".join(parts)

    if isinstance(
        value,
        dict,
    ):
        parts = []

        for key, item in value.items():

            key_text = clean_text(key)
            item_text = flatten_content(item)

            if key_text and item_text:
                parts.append(
                    f"{key_text}: {item_text}"
                )

            elif item_text:
                parts.append(item_text)

        return "\n".join(parts)

    return str(value)


def evidence_search_text(row):
    """
    Produce the text against which model evidence quotes and URLs
    will be validated.
    """
    parts = []

    source_path = getattr(
        row,
        "source_path",
        None,
    )

    if source_path:
        parts.append(
            str(source_path)
        )

    content = getattr(
        row,
        "content",
        None,
    )

    parts.append(
        flatten_content(content)
    )

    return "\n".join(
        part
        for part in parts
        if part
    )


# ============================================================
# EVIDENCE COLLECTION
# ============================================================

def collect_evidence(
    db,
    reel_id,
):
    rows = (
        db.query(Evidence)
        .filter(
            Evidence.reel_id == reel_id
        )
        .order_by(
            Evidence.id
        )
        .all()
    )

    evidence = []

    for row in rows:

        raw_content = getattr(
            row,
            "content",
            "",
        )

        try:
            content = json.loads(
                raw_content
            )
        except Exception:
            content = {
                "text": raw_content
            }

        raw_type = getattr(
            row,
            "evidence_type",
            "",
        )

        source_type = normalize_source_type(
            raw_type
        )

        if source_type not in ALLOWED_SOURCE_TYPES:
            source_type = (
                "external_metadata"
            )

        evidence.append(
            {
                "id": row.id,
                "type": source_type,
                "original_type": raw_type,
                "source": getattr(
                    row,
                    "source_path",
                    None,
                ),
                "content": content,
                # Immutable canonical text used for all persisted quotes.
                # The model selects an ID; it never gets to rewrite OCR or
                # transcript wording.
                "content_text": flatten_content(
                    content
                ),
                "search_text": evidence_search_text(
                    row
                ),
            }
        )

    return evidence


# ============================================================
# PROMPT CONSTRUCTION
# ============================================================

def build_prompt(
    reel,
    evidence,
):
    evidence_for_model = []

    for item in evidence:

        evidence_for_model.append(
            {
                "id": item["id"],
                "source_type": item["type"],
                "source": item["source"],
                "content": item["content"],
            }
        )

    evidence_json = json.dumps(
        evidence_for_model,
        ensure_ascii=False,
        indent=2,
    )

    caption = clean_text(
        getattr(
            reel,
            "caption",
            "",
        )
    )

    author = clean_text(
        getattr(
            reel,
            "author",
            "",
        )
    )

    url = clean_text(
        getattr(
            reel,
            "url",
            "",
        )
    )

    return f"""
You are the evidence extraction engine for Reel2Career.

Your job is to convert an Instagram reel into structured career
knowledge WITHOUT inventing information.

The most important objective is REEL FIDELITY.

Do not try to make the output look complete.
A sparse answer is correct when the evidence is sparse.

============================================================
ABSOLUTE RULES
============================================================

1. Use ONLY the supplied evidence.

2. Do NOT use outside knowledge.

3. Do NOT fill arrays merely to make the output look complete.

4. Two strongly supported skills are better than ten weak skills.

5. One directly supported action is better than nine inferred
   actions.

6. Every skill, action, resource and claim MUST contain one or more
    evidence objects with:
      - evidence_id
      - source_locator

    evidence_id identifies the captured evidence record.

    source_locator identifies the exact local item inside that
    evidence record.

7. Do NOT generate source_type or quote fields. Python will attach the
   immutable source type and canonical captured evidence text after it
   verifies the evidence_id exists.

8. Do NOT create evidence IDs.

9. Every evidence_id MUST exist in the supplied evidence.

9a. Every source_locator must identify the exact local location
        inside the cited evidence record.

9b. For numbered OCR lists, use:
            item:<number>

        Example:
            11. Automated vulnerability scanner

        The corresponding evidence reference must use:
            {{
              "evidence_id": 53,
              "source_locator": "item:11"
            }}

9c. For evidence that is a single unnumbered text/caption/comment
    record, use:
        text

    Example:
        {{
          "evidence_id": 54,
          "source_locator": "text"
        }}

9d. Do not invent item numbers.
9e. Do not renumber items.
9f. source_locator refers to the location in the supplied evidence,
    NOT the position of the item in the AI output.
9g. If a resource cannot be associated with one unique local item,
    omit the resource rather than guessing.

10. If no supplied evidence supports an item, DO NOT output the item.

11. support_level must be either:
      "direct"
      "inference"

12. Claims MUST ALWAYS use:
      "support_level": "direct"

16. Resources MUST ALWAYS use:
      "support_level": "direct"

17. Resource URLs MUST NEVER be inferred.

18. Resource URLs must be copied exactly from supplied evidence.

19. A resource URL must be a COMPLETE absolute HTTPS URL.

20. Never convert:
      github.com/foo
   into:
      https://github.com/foo

   unless the complete HTTPS URL itself appears in evidence.

21. Never reconstruct URLs from a brand name.

22. Never complete a truncated URL.

23. If no complete HTTPS URL is explicitly present in the
    evidence, return:
      "url": null

24. Claims about numbers, prices, incidents, news, statistics,
    reported events or other externally verifiable assertions
    must be attributed to the reel/creator unless the supplied
    evidence itself contains a verifiable source.

25. Example:
    "The reel claims a student received a $55,444 bill..."
    is acceptable when the reel says this.

    "A student received a $55,444 bill..."
    is NOT acceptable unless the supplied evidence independently
    verifies it.

============================================================
EVIDENCE SOURCE TYPES
============================================================

Every evidence record has one of these source types:

caption
transcript
on_screen_ocr
profile_bio
external_metadata

Use them correctly.

IMPORTANT:

profile_bio is NOT part of the reel's spoken/on-screen content.

If the reel says:
"The link is in my bio"

that is reel content.

If profile_bio evidence contains the actual URL, that URL may be
used as a resource only if it is explicitly supported by the
profile_bio evidence.

Do not make a profile-bio resource appear as though the video
itself displayed the URL.

============================================================
SUPPORT LEVEL
============================================================

Use:

direct
when the evidence explicitly says or shows the information.

Use:

inference
when the information is reasonably derived from the evidence
but not explicitly stated.

Examples:

"API key management" from a sentence explicitly discussing
API keys:
direct

"Security engineering" derived from several security concepts:
inference

However:

CLAIMS:
Only direct claims are allowed.

RESOURCES:
Only direct resources are allowed.

URLs:
Only direct URLs are allowed.

============================================================
SKILLS
============================================================

Return ONLY skills that are genuinely supported.

A skill should represent something the viewer could reasonably
learn from the reel.

Do NOT turn every noun into a skill.

============================================================
ACTIONS
============================================================

IMPORTANT:

Return an action ONLY when the creator explicitly tells the
viewer to do something.

Examples of direct CTA:

"Paste these prompts into Emergent."
"Check your Git history."
"Download the PDF."
"Use this checklist."

Those may become actions.

Do NOT turn general advice into an action.

For example:

"Never expose API keys."

does NOT automatically mean:

"Audit your API keys."

That would be an inferred recommendation.

Put derived best practices into:

suggested_next_steps

instead.

Suggested next steps are NOT creator instructions.

============================================================
RESOURCES
============================================================

A resource must actually be identified by the supplied evidence.

Examples:

A repository explicitly named and linked.

A tool explicitly named and linked.

A document explicitly named and linked.

If a resource is named but no complete HTTPS URL appears,
return:

"url": null

Do NOT invent the URL.

The application may skip such resources when saving because
the current resources.url database column is NOT NULL.

RESOURCE URL RULES:

- Return only complete absolute HTTPS URLs.
- Do not return Markdown-formatted URLs.
- Never return URLs containing "...".
- Never guess or reconstruct a truncated URL.
- If the evidence contains only a partial, truncated, malformed, or uncertain URL, return null for "url".
- Preserve the resource object and its evidence even when "url" is null.
- Do not infer a website URL from the resource title.
- Only return a URL when the complete URL is actually supported by the supplied evidence.

============================================================
NUMERICAL / NEWS CLAIMS
============================================================

Treat numerical and news-style statements cautiously.

If the reel says:

"A student got a $55,444.78 cloud bill."

Represent the claim as:

"The reel claims that a student received a $55,444.78 cloud bill..."

unless the supplied evidence itself provides a verifiable source.

============================================================
REEL METADATA
============================================================

Reel ID:
{reel.id}

Author:
{author}

Instagram URL:
{url}

Caption:
{caption}

============================================================
SUPPLIED EVIDENCE
============================================================

{evidence_json}

============================================================
OUTPUT FORMAT
============================================================

Return exactly one JSON object.

{{
  "summary": "short evidence-grounded summary",

  "topic": "main topic supported by the evidence",

  "career_area": "software engineering|cybersecurity|AI/ML|data|cloud|career|other|unknown",

  "career_relevance": 0.0,

  "career_relevance_reason": "brief evidence-grounded explanation",

  "difficulty": "beginner|intermediate|advanced|unknown",

  "priority": "high|medium|low|unknown",

  "skills": [
    {{
      "name": "specific skill",
      "category": "technical|security|software-engineering|ai-ml|data|cloud|career|other",
      "description": "only what the evidence supports",
      "support_level": "direct|inference",
      "evidence": [
        {{
                    "evidence_id": 1,
                    "source_locator": "item:1"
        }}
      ]
    }}
  ],

  "actions": [
    {{
      "title": "specific creator-directed action",
      "description": "what the creator explicitly tells the viewer to do",
      "action_type": "learn|build|practice|apply|verify|other",
      "priority": "high|medium|low",
      "estimated_minutes": null,
      "support_level": "direct",
      "evidence": [
        {{
                    "evidence_id": 1,
                    "source_locator": "item:1"
        }}
      ]
    }}
  ],

  "suggested_next_steps": [
    {{
      "title": "derived recommendation",
      "description": "a useful next step derived from the evidence but NOT explicitly instructed by the creator",
      "support_level": "inference",
      "evidence": [
        {{
                    "evidence_id": 1,
                    "source_locator": "item:1"
        }}
      ]
    }}
  ],

  "resources": [
    {{
      "title": "resource name exactly supported by evidence",
      "url": null,
      "resource_type": "repository|website|course|tool|article|other",
      "description": "what the evidence explicitly says about the resource",
      "support_level": "direct",
      "evidence": [
        {{
                    "evidence_id": 1,
                    "source_locator": "item:1"
        }}
      ]
    }}
  ],

  "claims": [
    {{
      "claim": "specific factual or creator-attributed claim",
      "confidence": 0.0,
      "support_level": "direct",
      "evidence": [
        {{
                    "evidence_id": 1,
                    "source_locator": "item:1"
        }}
      ]
    }}
  ]
}}

============================================================
FIELD REQUIREMENTS
============================================================

career_relevance MUST be a NUMBER from 0.0 to 1.0.

Do not put explanatory text in career_relevance.

estimated_minutes must be:
- an integer
- or null

confidence must be a NUMBER from 0.0 to 1.0.

Arrays may be empty.

DO NOT invent items to fill arrays.

Every extracted item must have at least one evidence object.

Every evidence object must have one valid evidence_id.
Python supplies the canonical source_type and quote from that record.

Claims cannot use support_level "inference".

Resources cannot use support_level "inference".

Resource URLs cannot use support_level "inference".

If a URL cannot be copied exactly from evidence as a complete
HTTPS URL, use null.

============================================================
RESOURCE URL GROUNDING RULES
============================================================

A resource URL must belong to the specific resource being described.

If the evidence contains multiple URLs for multiple resources:
- identify a URL only when the evidence clearly associates that URL
    with this specific resource
- do not reuse a URL merely because it appears in the same evidence
    record
- do not assign the same URL to multiple unrelated resources unless
    the evidence explicitly shows that they share the same URL
- if the association is ambiguous, use null

A URL must be copied exactly from the cited evidence.

Do not:
- reconstruct truncated URLs
- repair OCR errors
- infer a URL from a resource title
- infer a URL from a repository name
- substitute a homepage for a specific resource
- copy a URL belonging to another resource in the same evidence

When uncertain, use null.

============================================================
RESOURCE VS URL
============================================================

Identifying a resource does not require identifying its URL.

It is valid and preferred to return:
- the resource with url = null

rather than:
- inventing, guessing, borrowing, or reconstructing a URL.

A null URL is not a validation failure.

Keep the response compact: prefer fewer, stronger items and one short
evidence quote per item.  Finish valid JSON before adding another item.
Never close an array until every object in that array is complete.

============================================================
FINAL REQUIREMENT
============================================================

Return JSON only.

No markdown.

No commentary.

No explanation outside the JSON object.
"""


# ============================================================
# EVIDENCE INDEX
# ============================================================

def build_evidence_index(
    evidence,
):
    return {
        item["id"]: item
        for item in evidence
    }


# ============================================================
# VALIDATION HELPERS
# ============================================================

def normalize_source_locator(value):
    """
    Normalize a local evidence source locator.

    Supported formats:
        item:<positive integer>
        text

    Examples:
        item:11
        text
    """
    value = clean_text(value)
    if not value:
        return None

    if value.casefold() == "text":
        return "text"

    match = re.fullmatch(r"item:(\d+)", value, re.IGNORECASE)
    if not match:
        return None

    item_number = int(match.group(1))
    if item_number <= 0:
        return None

    return f"item:{item_number}"


def validate_evidence_reference(
    reference,
    evidence_index,
    item_label,
):
    """
    Validate one evidence object.

    Returns:
        normalized evidence reference
    """

    if not isinstance(
        reference,
        dict,
    ):
        raise ValueError(
            f"{item_label}: evidence entry "
            "must be an object."
        )

    evidence_id = reference.get(
        "evidence_id"
    )

    if isinstance(
        evidence_id,
        bool,
    ):
        raise ValueError(
            f"{item_label}: invalid evidence_id."
        )

    try:
        evidence_id = int(
            evidence_id
        )
    except (
        TypeError,
        ValueError,
    ):
        raise ValueError(
            f"{item_label}: evidence_id "
            "must be an integer."
        )

    if evidence_id not in evidence_index:
        raise ValueError(
            f"{item_label}: unsupported "
            f"evidence_id {evidence_id}."
        )

    source_locator = normalize_source_locator(
        reference.get("source_locator")
    )

    if not source_locator:
        raise ValueError(
            f"{item_label}: evidence reference "
            "requires a valid source_locator."
        )

    evidence_item = evidence_index[evidence_id]
    quote = clean_text(
        evidence_item.get(
            "content_text",
            evidence_item.get(
                "search_text",
                "",
            ),
        )
    )

    if not quote:
        raise ValueError(
            f"{item_label}: evidence {evidence_id} "
            "has no canonical text."
        )

    return {
        "evidence_id": evidence_id,
        "source_locator": source_locator,
        "source_type": evidence_item["type"],
        "quote": quote,
    }


def validate_evidence_list(
    item,
    evidence_index,
    item_label,
):
    evidence = item.get(
        "evidence"
    )

    if not isinstance(
        evidence,
        list,
    ):
        raise ValueError(
            f"{item_label}: evidence must "
            "be a non-empty list."
        )

    if not evidence:
        raise ValueError(
            f"{item_label}: at least one "
            "evidence quote is required."
        )

    validated = []

    seen = set()

    for reference in evidence:

        normalized = validate_evidence_reference(
            reference,
            evidence_index,
            item_label,
        )

        key = (
            normalized["evidence_id"],
            normalized["quote"],
        )

        if key in seen:
            continue

        seen.add(key)
        validated.append(
            normalized
        )

    if not validated:
        raise ValueError(
            f"{item_label}: no valid "
            "evidence references."
        )

    return validated


def validate_support_level(
    item,
    item_label,
):
    support_level = clean_text(
        item.get(
            "support_level"
        )
    ).lower()

    if support_level not in ALLOWED_SUPPORT_LEVELS:
        raise ValueError(
            f"{item_label}: invalid "
            f"support_level {support_level!r}."
        )

    return support_level


def extract_github_repo_identity(text):
    """
    Extract a GitHub owner/repository identity only from a
    complete HTTPS GitHub URL.

    This function is for identity only. It never repairs URLs.

    Returns:
        normalized "github:owner/repository", or None.
    """
    if not text:
        return None

    pattern = re.compile(
        r"(?<![\w:/])"
        r"https://github\.com/"
        r"([A-Za-z0-9_.-]+)"
        r"/"
        r"([A-Za-z0-9_.-]+)"
        r"(?![A-Za-z0-9_.-])",
        re.IGNORECASE,
    )

    matches = pattern.findall(text)

    if len(matches) != 1:
        return None

    owner, repo = matches[0]

    return (
        f"github:{owner.casefold()}/"
        f"{repo.casefold()}"
    )


def extract_local_evidence_block(evidence_text, source_locator):
    """
    Return the exact numbered local evidence block identified
    by source_locator.

    Supported:
        item:<positive integer>
        text

    A numbered item ends immediately before the next numbered item.
    The parser accepts common OCR punctuation/bullet prefixes but
    requires the item number to begin a new line.
    """
    locator = normalize_source_locator(source_locator)

    if not locator:
        return None

    if locator.casefold() == "text":
        return evidence_text

    match = re.fullmatch(
        r"item:(\d+)",
        locator,
        re.IGNORECASE,
    )

    if not match:
        return None

    target_number = int(match.group(1))
    text = evidence_text or ""

    # Match numbered evidence items at the beginning of a line.
    #
    # Examples accepted:
    #   1. Reference:
    #   2. Multi-agent pipeline:
    #   • 3. Something
    #   -> 4. Something
    #
    # The number itself must start the actual numbered marker.
    item_re = re.compile(
        r"(?m)^[ \t]*(?:[-*•→>»]\s*)?"
        r"(\d{1,3})[.)]\s+"
    )

    matches = list(item_re.finditer(text))

    for index, item_match in enumerate(matches):
        number = int(item_match.group(1))

        if number != target_number:
            continue

        start = item_match.start()

        if index + 1 < len(matches):
            end = matches[index + 1].start()
        else:
            end = len(text)

        block = text[start:end].strip()

        if not block:
            return None

        return block

    return None

def validate_https_resource_url(
    item,
    evidence_refs,
    evidence_index,
    item_label,
):
    """
    Resolve and validate a resource URL strictly from the
    resource's precise evidence locator.

    Rules:
    - A model-supplied URL must be a complete HTTPS URL.
    - The URL must occur in the exact local evidence block
      identified by source_locator.
    - If the model supplies no URL, recover it only when exactly
      one complete HTTPS URL exists in that local block.
    - Never borrow a URL from another evidence item.
    - Never repair damaged OCR URLs.
    - Never infer a URL from the resource title.
    """

    model_url = normalize_resource_url(
        item.get("url")
    )

    normalized_model_url = (
        normalize_for_match(model_url)
        if model_url
        else None
    )

    for reference in evidence_refs:

        evidence_id = reference.get(
            "evidence_id"
        )

        source_locator = reference.get(
            "source_locator"
        )

        if evidence_id not in evidence_index:
            continue

        evidence_item = evidence_index[
            evidence_id
        ]

        evidence_text = evidence_item.get(
            "content_text",
            evidence_item.get(
                "search_text",
                "",
            ),
        )

        if not isinstance(evidence_text, str):
            evidence_text = str(evidence_text)

        if not evidence_text:
            continue

        local_block = extract_local_evidence_block(
            evidence_text,
            source_locator,
        )

        if not local_block:
            continue

        block_urls = (
            extract_evidence_resource_urls(
                local_block
            )
        )

        # Model supplied a URL.
        if normalized_model_url:

            for evidence_url in block_urls:

                if (
                    normalize_for_match(
                        evidence_url
                    )
                    == normalized_model_url
                ):
                    return model_url

            continue

        # Model supplied url=null.
        # Recover only when the local block contains exactly
        # one clean HTTPS URL.
        if len(block_urls) == 1:
            return block_urls[0]

        # Zero URLs = unresolved.
        # Multiple URLs = ambiguous.

    return None


def validate_item_basic(
    item,
    evidence_index,
    item_label,
    require_direct=False,
):
    if not isinstance(
        item,
        dict,
    ):
        raise ValueError(
            f"{item_label}: item must "
            "be an object."
        )

    support_level = validate_support_level(
        item,
        item_label,
    )

    if (
        require_direct
        and support_level != "direct"
    ):
        raise ValueError(
            f"{item_label}: only direct "
            "support is permitted."
        )

    evidence_refs = validate_evidence_list(
        item,
        evidence_index,
        item_label,
    )

    return (
        support_level,
        evidence_refs,
    )


# ============================================================
# SEMANTIC GROUNDING CHECK
# ============================================================

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "to",
    "of",
    "for",
    "in",
    "on",
    "with",
    "from",
    "this",
    "that",
    "these",
    "those",
    "is",
    "are",
    "be",
    "as",
    "by",
    "it",
    "its",
    "into",
    "your",
    "you",
    "their",
    "they",
    "can",
    "may",
    "should",
    "must",
    "will",
    "how",
    "what",
    "why",
    "when",
    "where",
    "do",
    "does",
    "did",
    "use",
    "using",
    "used",
}


def significant_tokens(text):
    text = clean_text(
        text
    ).casefold()

    tokens = re.findall(
        r"[a-zA-Z0-9_+#.-]+",
        text,
    )

    return {
        token
        for token in tokens
        if (
            len(token) >= 4
            and token not in STOPWORDS
        )
    }


def validate_grounding_tokens(
    item,
    evidence_refs,
    item_label,
):
    """
    Conservative grounding check.

    The model must not introduce a large amount of technical
    terminology that is completely absent from its cited quotes.

    This is intentionally a warning-level check for descriptions
    rather than a hard linguistic equivalence test.
    """

    quote_text = " ".join(
        ref["quote"]
        for ref in evidence_refs
    )

    item_text = " ".join(
        [
            clean_text(
                item.get("name")
            ),
            clean_text(
                item.get("title")
            ),
            clean_text(
                item.get("description")
            ),
            clean_text(
                item.get("claim")
            ),
        ]
    )

    quote_tokens = significant_tokens(
        quote_text
    )

    item_tokens = significant_tokens(
        item_text
    )

    if not item_tokens:
        return

    unsupported = (
        item_tokens
        - quote_tokens
    )

    # Generic paraphrasing naturally introduces some words.
    # Reject only when the majority of significant terminology
    # is absent from the cited quote.
    ratio = (
        len(unsupported)
        / max(
            len(item_tokens),
            1,
        )
    )

    if ratio > 0.70:
        raise ValueError(
            f"{item_label}: too much "
            "technical/detail text is absent "
            "from the cited evidence quote."
        )


def is_item_grounded(
    item,
    evidence_refs,
    item_label,
):
    """Keep the grounding threshold strict without losing the whole reel."""
    try:
        validate_grounding_tokens(
            item,
            evidence_refs,
            item_label,
        )
    except ValueError:
        return False

    return True


# ============================================================
# POST-GENERATION VALIDATOR
# ============================================================

def validate_ai_result(
    result,
    evidence,
):
    """
    Validate the entire AI response before SQLite persistence.
    """

    if not isinstance(
        result,
        dict,
    ):
        raise ValueError(
            "AI result must be a JSON object."
        )

    evidence_index = build_evidence_index(
        evidence
    )

    # --------------------------------------------------------
    # Required scalar fields
    # --------------------------------------------------------

    if "summary" not in result:
        raise ValueError(
            "AI result missing summary."
        )

    if "topic" not in result:
        raise ValueError(
            "AI result missing topic."
        )

    if "career_area" not in result:
        raise ValueError(
            "AI result missing career_area."
        )

    result["career_relevance"] = (
        normalize_relevance(
            result.get(
                "career_relevance",
                0.0,
            )
        )
    )

    # --------------------------------------------------------
    # Normalize arrays
    # --------------------------------------------------------

    array_fields = [
        "skills",
        "actions",
        "suggested_next_steps",
        "resources",
        "claims",
    ]

    for field in array_fields:

        value = result.get(
            field,
            [],
        )

        if value is None:
            value = []

        if not isinstance(
            value,
            list,
        ):
            raise ValueError(
                f"AI result field {field!r} "
                "must be an array."
            )

        result[field] = value

    # --------------------------------------------------------
    # SKILLS
    # --------------------------------------------------------

    validated_skills = []

    for index, item in enumerate(
        result["skills"],
        start=1,
    ):
        label = (
            f"skills[{index}]"
        )

        support_level, evidence_refs = (
            validate_item_basic(
                item,
                evidence_index,
                label,
            )
        )

        if not is_item_grounded(
            item,
            evidence_refs,
            label,
        ):
            continue

        item["support_level"] = (
            support_level
        )

        item["evidence"] = evidence_refs

        validated_skills.append(
            item
        )

    result["skills"] = validated_skills

    # --------------------------------------------------------
    # ACTIONS
    # --------------------------------------------------------

    validated_actions = []

    for index, item in enumerate(
        result["actions"],
        start=1,
    ):
        label = (
            f"actions[{index}]"
        )

        support_level, evidence_refs = (
            validate_item_basic(
                item,
                evidence_index,
                label,
                require_direct=True,
            )
        )

        # Creator-directed actions must be direct.
        if support_level != "direct":
            raise ValueError(
                f"{label}: actions must "
                "be directly supported."
            )

        if not is_item_grounded(
            item,
            evidence_refs,
            label,
        ):
            continue

        item["support_level"] = "direct"
        item["evidence"] = evidence_refs

        item["estimated_minutes"] = (
            normalize_minutes(
                item.get(
                    "estimated_minutes"
                )
            )
        )

        validated_actions.append(
            item
        )

    result["actions"] = validated_actions

    # --------------------------------------------------------
    # SUGGESTED NEXT STEPS
    # --------------------------------------------------------

    validated_next_steps = []

    for index, item in enumerate(
        result["suggested_next_steps"],
        start=1,
    ):
        label = (
            f"suggested_next_steps[{index}]"
        )

        support_level, evidence_refs = (
            validate_item_basic(
                item,
                evidence_index,
                label,
            )
        )

        if support_level != "inference":
            raise ValueError(
                f"{label}: suggested_next_steps "
                "must use support_level "
                "'inference'."
            )

        if not is_item_grounded(
            item,
            evidence_refs,
            label,
        ):
            continue

        item["support_level"] = (
            "inference"
        )

        item["evidence"] = evidence_refs

        validated_next_steps.append(
            item
        )

    result["suggested_next_steps"] = (
        validated_next_steps
    )

    # --------------------------------------------------------
    # RESOURCES
    # --------------------------------------------------------

    validated_resources = []

    for index, item in enumerate(
        result["resources"],
        start=1,
    ):
        label = (
            f"resources[{index}]"
        )

        support_level, evidence_refs = (
            validate_item_basic(
                item,
                evidence_index,
                label,
                require_direct=True,
            )
        )

        if support_level != "direct":
            raise ValueError(
                f"{label}: resources must "
                "be directly supported."
            )

        url = validate_https_resource_url(
            item,
            evidence_refs,
            evidence_index,
            label,
        )

        item["support_level"] = "direct"
        item["evidence"] = evidence_refs
        item["url"] = url

        if not is_item_grounded(
            item,
            evidence_refs,
            label,
        ):
            continue

        validated_resources.append(
            item
        )

    result["resources"] = (
        validated_resources
    )

    # --------------------------------------------------------
    # CLAIMS
    # --------------------------------------------------------

    validated_claims = []

    for index, item in enumerate(
        result["claims"],
        start=1,
    ):
        label = (
            f"claims[{index}]"
        )

        support_level, evidence_refs = (
            validate_item_basic(
                item,
                evidence_index,
                label,
                require_direct=True,
            )
        )

        if support_level != "direct":
            raise ValueError(
                f"{label}: claims must "
                "use support_level 'direct'."
            )

        item["support_level"] = "direct"

        item["evidence"] = evidence_refs

        item["confidence"] = (
            normalize_confidence(
                item.get(
                    "confidence",
                    0.0,
                )
            )
        )

        if not is_item_grounded(
            item,
            evidence_refs,
            label,
        ):
            continue

        validated_claims.append(
            item
        )

    result["claims"] = (
        validated_claims
    )

    # --------------------------------------------------------
    # Final provenance object
    # --------------------------------------------------------

    result["_validation"] = {
        "validated": True,
        "validator_version": "3.0",
        "evidence_count": len(
            evidence
        ),
        "skills_validated": len(
            result["skills"]
        ),
        "actions_validated": len(
            result["actions"]
        ),
        "suggested_next_steps_validated": len(
            result["suggested_next_steps"]
        ),
        "resources_validated": len(
            result["resources"]
        ),
        "claims_validated": len(
            result["claims"]
        ),
    }

    return result


# ============================================================
# OMNIROUTE CALL WITH RETRIES
# ============================================================

def iter_json_object_candidates(output):
    """Yield complete JSON objects while ignoring braces in strings/log noise."""
    for start, character in enumerate(output):
        if character != "{":
            continue

        depth = 0
        in_string = False
        escaped = False
        for end in range(start, len(output)):
            current = output[end]
            if in_string:
                if escaped:
                    escaped = False
                elif current == "\\":
                    escaped = True
                elif current == '"':
                    in_string = False
                continue
            if current == '"':
                in_string = True
            elif current == "{":
                depth += 1
            elif current == "}":
                depth -= 1
                if depth == 0:
                    yield output[start:end + 1]
                    break


def parse_ai_json_output(output):
    """Parse complete JSON, repairing only the observed extra array closure."""
    candidates = list(iter_json_object_candidates(output))
    if not candidates:
        raise ValueError("AI response did not contain a complete JSON object.")

    errors = []
    best_result = None
    expected_keys = {
        "summary",
        "topic",
        "skills",
        "actions",
        "resources",
        "claims",
    }
    for candidate in candidates:
        repaired = re.sub(
            r"\]\s*}\s*\]\s*,\s*{",
            "]},{",
            candidate,
        )
        for label, json_text in (
            ("original", candidate),
            ("extra-array-close repair", repaired),
        ):
            if label != "original" and json_text == candidate:
                continue
            try:
                parsed = json.loads(json_text)
            except json.JSONDecodeError as exc:
                errors.append(f"{label}: {exc}")
                continue
            if isinstance(parsed, dict):
                score = len(expected_keys.intersection(parsed))
                if (
                    best_result is None
                    or score > best_result[0]
                ):
                    best_result = (score, parsed)
                continue
            errors.append(f"{label}: JSON value was not an object")

    if best_result is not None:
        return best_result[1]

    raise ValueError(
        "AI response contained no parseable JSON object. "
        + " | ".join(errors[-2:])
    )


def run_ai_from_file(
    prompt,
    reel_id,
    json_attempt=1,
):
    prompt_file = (
        PROMPT_DIR
        / (
            f"reel_{reel_id}_analysis_json_retry.txt"
            if json_attempt > 1
            else f"reel_{reel_id}_analysis.txt"
        )
    )

    prompt_file.write_text(
        prompt,
        encoding="utf-8",
    )

    command = [
        "cmd.exe",
        "/d",
        "/c",
        str(OMNIROUTE),
        "chat",
        "--file",
        str(prompt_file),
        "--model",
        MODEL,
        "--max-tokens",
        str(AI_MAX_TOKENS),
        "--no-history",
    ]

    last_result = None

    for attempt in range(
        1,
        MAX_AI_ATTEMPTS + 1,
    ):
        print(
            f"    OmniRoute attempt "
            f"{attempt}/{MAX_AI_ATTEMPTS}..."
        )

        result = subprocess.run(
            command,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        last_result = result

        if result.returncode == 0:
            break

        combined_output = (
            result.stdout
            + "\n"
            + result.stderr
        )

        transient = any(
            marker in combined_output
            for marker in (
                "429 Too Many Requests",
                "502 Bad Gateway",
                "503 Service Unavailable",
                "504 Gateway Timeout",
                "upstream_empty_response",
            )
        )

        if (
            not transient
            or attempt >= MAX_AI_ATTEMPTS
        ):
            raise RuntimeError(
                "OmniRoute failed.\n\n"
                "STDOUT:\n"
                + result.stdout
                + "\n\n"
                "STDERR:\n"
                + result.stderr
                + "\n\n"
                "Return code: "
                + str(
                    result.returncode
                )
            )

        delay = RETRY_DELAYS[
            attempt - 1
        ]

        print(
            "    OmniRoute returned "
            "a transient error."
        )

        print(
            f"    Retrying in "
            f"{delay} seconds..."
        )

        time.sleep(
            delay
        )

    if last_result is None:
        raise RuntimeError(
            "OmniRoute did not produce "
            "a result."
        )

    output = (
        last_result.stdout.strip()
    )

    try:
        parsed = parse_ai_json_output(output)
    except ValueError as exc:
        if json_attempt < MAX_JSON_ATTEMPTS:
            print(
                "    AI returned malformed JSON; retrying with a compact JSON-only prompt."
            )
            retry_prompt = (
                prompt
                + "\n\nYOUR PREVIOUS RESPONSE WAS NOT PARSEABLE JSON. "
                "Start over from the supplied evidence. Return exactly one complete "
                "JSON object, with fewer items and shorter quotes if necessary. Do "
                "not include Markdown, logs, commentary, partial JSON, or any text "
                "outside the object. Do not invent or repair missing evidence."
            )
            return run_ai_from_file(
                retry_prompt,
                reel_id,
                json_attempt=json_attempt + 1,
            )
        raise ValueError(
            "AI returned invalid JSON after JSON-only retry: "
            + str(exc)
        ) from exc

    return (
        parsed,
        output,
        prompt_file,
    )

# ============================================================
# PROVENANCE EXTRACTION
# ============================================================

def build_provenance(
    result,
):
    """
    Preserve the full structured provenance in Analysis.explanation.

    This avoids requiring a DB migration while still ensuring
    that skills/actions/resources/claims do not lose their
    evidence links after persistence.
    """

    return {
        "career_relevance_reason": result.get(
            "career_relevance_reason",
            "",
        ),

        "skills": result.get(
            "skills",
            [],
        ),

        "actions": result.get(
            "actions",
            [],
        ),

        "suggested_next_steps": result.get(
            "suggested_next_steps",
            [],
        ),

        "resources": result.get(
            "resources",
            [],
        ),

        "claims": result.get(
            "claims",
            [],
        ),

        "validation": result.get(
            "_validation",
            {},
        ),
    }


# ============================================================
# SAVE ANALYSIS
# ============================================================

def get_or_create_resource(
    db,
    reel,
    item,
    title,
    url,
    identity_key,
    resource_type,
    source_domain,
    description,
):
    """
    Idempotently resolve a Resource.

    Identity precedence:
      1. durable GitHub identity_key
      2. exact URL
      3. existing Reel + evidence locator
      4. unresolved title match
      5. create new Resource
    """

    # ----------------------------------------------------
    # 1. Durable identity
    # ----------------------------------------------------
    if identity_key:
        resource = (
            db.query(Resource)
            .filter(Resource.identity_key == identity_key)
            .first()
        )

        if resource is not None:
            if url and resource.url is None:
                resource.url = url

            if resource_type and not resource.resource_type:
                resource.resource_type = resource_type

            if source_domain and not resource.source_domain:
                resource.source_domain = source_domain

            if description and not resource.description:
                resource.description = description

            return resource

    # ----------------------------------------------------
    # 2. Exact URL
    # ----------------------------------------------------
    if url:
        resource = (
            db.query(Resource)
            .filter(Resource.url == url)
            .first()
        )

        if resource is not None:
            return resource

    # ----------------------------------------------------
    # 3. Same Reel + evidence location
    # ----------------------------------------------------
    resource_evidence = item.get("evidence") or []

    if resource_evidence:
        first_evidence = resource_evidence[0] or {}

        evidence_id = first_evidence.get("evidence_id")

        source_locator = normalize_source_locator(
            first_evidence.get("source_locator")
        )

        if evidence_id and source_locator:
            link = (
                db.query(ReelResource)
                .filter(
                    ReelResource.reel_id == reel.id,
                    ReelResource.source_evidence_id == evidence_id,
                    ReelResource.source_locator == source_locator,
                )
                .order_by(ReelResource.id.asc())
                .first()
            )

            if link is not None:
                resource = (
                    db.query(Resource)
                    .filter(Resource.id == link.resource_id)
                    .first()
                )

                if resource is not None:
                    return resource

    # ----------------------------------------------------
    # 4. Existing unresolved title
    # ----------------------------------------------------
    resource = (
        db.query(Resource)
        .filter(
            Resource.url.is_(None),
            Resource.title == title,
        )
        .first()
    )

    if resource is not None:
        return resource

    # ----------------------------------------------------
    # 5. Create
    # ----------------------------------------------------
    resource = Resource(
        title=title,
        url=url,
        identity_key=identity_key,
        resource_type=resource_type,
        source_domain=source_domain,
        description=description,
        verification_status="unverified",
    )

    db.add(resource)
    db.flush()

    return resource


def save_analysis(
    db,
    reel,
    result,
    raw_output,
    evidence,
):
    evidence_index = build_evidence_index(
        evidence
    )

    # ========================================================
    # ANALYSIS
    # ========================================================

    analysis = (
        db.query(Analysis)
        .filter(
            Analysis.reel_id == reel.id
        )
        .first()
    )

    if analysis is None:
        analysis = Analysis(
            reel_id=reel.id
        )

        db.add(
            analysis
        )

    analysis.summary = clean_text(
        result.get(
            "summary",
            "",
        )
    )

    analysis.topic = clean_text(
        result.get(
            "topic",
            "",
        )
    )[:255]

    analysis.career_area = clean_text(
        result.get(
            "career_area",
            "",
        )
    )[:255]

    analysis.career_relevance = (
        normalize_relevance(
            result.get(
                "career_relevance",
                0.0,
            )
        )
    )

    analysis.difficulty = clean_text(
        result.get(
            "difficulty",
            "unknown",
        )
    )[:32]

    analysis.priority = clean_text(
        result.get(
            "priority",
            "unknown",
        )
    )[:32]

    # Full provenance is persisted here.
    provenance = build_provenance(
        result
    )

    analysis.explanation = json.dumps(
        provenance,
        ensure_ascii=False,
    )

    analysis.raw_model_output = (
        raw_output
    )

    analysis.model_name = MODEL

    db.flush()

    # ========================================================
    # ACTIONS
    # ========================================================

    db.query(Action).filter(
        Action.reel_id == reel.id
    ).delete(
        synchronize_session=False
    )

    db.flush()

    actions = result.get(
        "actions",
        [],
    )

    if not isinstance(
        actions,
        list,
    ):
        actions = []

    for item in actions:

        if not isinstance(
            item,
            dict,
        ):
            continue

        title = clean_text(
            item.get(
                "title",
                "",
            )
        )

        if not title:
            continue

        description = clean_text(
            item.get(
                "description",
                "",
            )
        )

        action_type = clean_text(
            item.get(
                "action_type",
                "other",
            )
        )[:32]

        priority = clean_text(
            item.get(
                "priority",
                "medium",
            )
        )[:32]

        estimated_minutes = (
            normalize_minutes(
                item.get(
                    "estimated_minutes"
                )
            )
        )

        db.add(
            Action(
                reel_id=reel.id,
                title=title,
                description=description,
                action_type=action_type,
                priority=priority,
                status="pending",
                estimated_minutes=(
                    estimated_minutes
                ),
            )
        )

    db.flush()

    # ========================================================
    # SKILLS
    # ========================================================

    skills = result.get(
        "skills",
        [],
    )

    if not isinstance(
        skills,
        list,
    ):
        skills = []

    for item in skills:

        if not isinstance(
            item,
            dict,
        ):
            continue

        name = clean_text(
            item.get(
                "name",
                "",
            )
        )

        if not name:
            continue

        category = clean_text(
            item.get(
                "category",
                "other",
            )
        )[:64]

        description = clean_text(
            item.get(
                "description",
                "",
            )
        )

        skill = (
            db.query(Skill)
            .filter(
                Skill.name == name
            )
            .first()
        )

        if skill is None:

            skill = Skill(
                name=name,
                category=category,
                description=description,
            )

            db.add(
                skill
            )

            db.flush()

        else:

            if not skill.category:
                skill.category = category

            if (
                not skill.description
                and description
            ):
                skill.description = (
                    description
                )

        existing_link = (
            db.query(ReelSkill)
            .filter(
                ReelSkill.reel_id
                == reel.id,

                ReelSkill.skill_id
                == skill.id,
            )
            .first()
        )

        if existing_link is None:

            db.add(
                ReelSkill(
                    reel_id=reel.id,
                    skill_id=skill.id,
                )
            )

    db.flush()

    # ========================================================
    # RESOURCES
    # ========================================================

    resources = result.get(
        "resources",
        [],
    )

    if not isinstance(
        resources,
        list,
    ):
        resources = []

    resource_by_key = {}
    seen_reel_resource_keys = set()

    for item in resources:

        if not isinstance(
            item,
            dict,
        ):
            continue

        title = clean_text(
            item.get(
                "title",
                "",
            )
        )

        if not title:
            continue

        # ----------------------------------------------------
        # Current DB schema requires resources.url NOT NULL.
        #
        # The model may legitimately return url=null when the
        # reel names a resource without providing a complete
        # HTTPS URL.
        #
        # Such resources are retained in Analysis.explanation
        # provenance but are NOT inserted into resources.
        # ----------------------------------------------------

        url = validate_https_resource_url(
            item=item,
            evidence_refs=item.get(
                "evidence",
                [],
            ),
            evidence_index=evidence_index,
            item_label=title,
        )

        # ----------------------------------------------------
        # GITHUB RESOLUTION
        # ----------------------------------------------------

        github_resolution = None

        if not url:
            resource_evidence = item.get("evidence") or []

            local_evidence_parts = []

            for evidence_ref in resource_evidence:
                if not isinstance(evidence_ref, dict):
                    continue

                evidence_id = evidence_ref.get("evidence_id")
                source_locator = normalize_source_locator(
                    evidence_ref.get("source_locator")
                )

                if not evidence_id or not source_locator:
                    continue

                evidence_record = (
                    db.query(Evidence)
                    .filter(Evidence.id == evidence_id)
                    .first()
                )

                if evidence_record is None:
                    continue

                local_block = extract_local_evidence_block(
                    evidence_record.content,
                    source_locator,
                )

                if local_block:
                    local_evidence_parts.append(local_block)

            local_evidence = "\n".join(
                local_evidence_parts
            )

            github_hints = extract_github_hints(
                local_evidence
            )

            github_candidates = (
                discover_github_candidates(
                    title,
                    github_hints,
                    evidence_text=local_evidence,
                )
            )

            github_resolution = (
                resolve_github_resource(
                    title,
                    github_hints,
                    github_candidates,
                    evidence_text=local_evidence,
                )
            )

            if github_resolution.status == "verified":
                print(
                    "    GitHub verified candidate:",
                    (
                        github_resolution.selected.owner
                        + "/"
                        + github_resolution.selected.repository
                    ),
                )

            elif github_resolution.status == "ambiguous":
                top = (
                    github_resolution.ranking[0]
                    if github_resolution.ranking
                    else None
                )

                if top:
                    print(
                        "    GitHub match ambiguous:",
                        title,
                        "->",
                        (
                            top.candidate.owner
                            + "/"
                            + top.candidate.repository
                        ),
                    )
                else:
                    print(
                        "    GitHub match ambiguous:",
                        title,
                    )

            elif github_resolution.status == "not_found":
                print(
                    "    GitHub match not found:",
                    title,
                )

        if not url:
            print(
                "    Resource without verified evidence URL:",
                title,
            )

        # ----------------------------------------------------
        # SOURCE DOMAIN
        # ----------------------------------------------------

        source_domain = None

        if url:
            try:
                source_domain = (
                    urlparse(url).netloc
                    or None
                )
            except Exception:
                source_domain = None

        # ----------------------------------------------------
        # RESOURCE METADATA
        # ----------------------------------------------------

        resource_type = clean_text(
            item.get(
                "resource_type",
                "other",
            )
        )[:64]

        description = clean_text(
            item.get(
                "description",
                "",
            )
        )

        identity_key = None

        # A verified GitHub resolution is authoritative.
        if (
            github_resolution is not None
            and github_resolution.status == "verified"
            and github_resolution.selected is not None
        ):
            url = github_resolution.selected.url
            identity_key = (
                f"github:"
                f"{github_resolution.selected.owner.casefold()}/"
                f"{github_resolution.selected.repository.casefold()}"
            )
        elif url:
            identity_key = extract_github_repo_identity(url)

        resource_key = (
            url.casefold()
            if url
            else (
                f"identity:{identity_key}"
                if identity_key
                else f"unresolved:{reel.id}:{title.casefold()}"
            )
        )

        resource = resource_by_key.get(resource_key)

        if resource is None:
            resource = get_or_create_resource(
                db=db,
                reel=reel,
                item=item,
                title=title,
                url=url,
                identity_key=identity_key,
                resource_type=resource_type,
                source_domain=source_domain,
                description=description,
            )

        # ----------------------------------------------------
        # APPLY VERIFIED GITHUB RESOLUTION
        # ----------------------------------------------------

        if (
            github_resolution is not None
            and github_resolution.status == "verified"
        ):
            apply_github_resolution(
                resource,
                github_resolution,
            )

        resource_by_key[resource_key] = resource

        if resource.identity_key:
            resource_by_key[
                f"identity:{resource.identity_key}"
            ] = resource

        if resource.url:
            resource_by_key[
                resource.url.casefold()
            ] = resource

        # ----------------------------------------------------
        # RESOURCE LINK
        # ----------------------------------------------------

        reel_resource_key = (
            reel.id,
            resource.id,
        )

        if reel_resource_key in seen_reel_resource_keys:
            continue

        seen_reel_resource_keys.add(
            reel_resource_key
        )

        existing_link = (
            db.query(ReelResource)
            .filter(
                ReelResource.reel_id
                == reel.id,

                ReelResource.resource_id
                == resource.id,
            )
            .first()
        )

        resource_evidence = item.get("evidence") or []

        source_evidence_id = None
        source_locator = None

        if resource_evidence:
            first_evidence = resource_evidence[0] or {}

            candidate_evidence_id = first_evidence.get(
                "evidence_id"
            )

            candidate_locator = normalize_source_locator(
                first_evidence.get("source_locator")
            )

            if (
                candidate_evidence_id
                and candidate_locator
                and candidate_evidence_id in evidence_index
            ):
                evidence_record = (
                    db.query(Evidence)
                    .filter(
                        Evidence.id == candidate_evidence_id
                    )
                    .first()
                )

                if evidence_record is not None:
                    local_block = extract_local_evidence_block(
                        evidence_record.content,
                        candidate_locator,
                    )

                    if local_block:
                        source_evidence_id = (
                            candidate_evidence_id
                        )
                        source_locator = candidate_locator

                    else:
                        print(
                            "    Rejected unsafe provenance:",
                            title,
                            "->",
                            candidate_locator,
                        )

        if existing_link is None:

            db.add(
                ReelResource(
                    reel_id=reel.id,
                    resource_id=resource.id,
                    source_evidence_id=source_evidence_id,
                    source_locator=source_locator,
                )
            )

        else:

            existing_link.source_evidence_id = (
                source_evidence_id
            )

            existing_link.source_locator = (
                source_locator
            )

    db.flush()


# ============================================================
# BATCH-SAFE VALIDATION / RETRY HELPERS
# ============================================================

def build_validation_retry_prompt(
    original_prompt,
    validation_error,
    previous_output,
):
    """
    Ask the model to repair a validation failure without changing the
    evidence-grounding rules.

    This is deliberately a full re-generation request rather than a
    request to patch arbitrary JSON. That prevents Python from silently
    inventing missing fields or evidence.
    """
    return (
        original_prompt
        + "\n\n"
        + "============================================================\n"
        + "VALIDATION REPAIR ATTEMPT\n"
        + "============================================================\n"
        + "Your previous JSON was parseable but failed the Python validator.\n"
        + "Validation error:\n"
        + validation_error
        + "\n\n"
        + "Generate a NEW complete JSON object from the supplied evidence.\n"
        + "Do not output a patch. Do not output commentary.\n"
        + "Do not invent evidence IDs, quotes, URLs, or facts.\n"
        + "If an item cannot satisfy the schema and evidence rules, OMIT it.\n"
        + "If a field is required, provide a conservative value supported by\n"
        + "the evidence. If the evidence is genuinely insufficient, use the\n"
        + "allowed unknown/empty representation from the schema.\n"
        + "In particular:\n"
        + "- summary must always be present\n"
        + "- suggested_next_steps must use support_level 'inference'\n"
        + "- actions must use support_level 'direct'\n"
        + "- resources must use support_level 'direct'\n"
        + "- claims must use support_level 'direct'\n"
        + "- every extracted item needs valid evidence\n"
        + "- resource URLs must never be guessed\n"
        + "- return exactly one complete JSON object\n"
        + "\n"
        + "Previous output is included only to help you understand what failed;\n"
        + "do not copy unsupported material from it:\n"
        + previous_output[:12000]
    )


def save_failed_output(
    reel_id,
    raw_output,
    reason,
):
    """
    Quarantine the last model output for debugging.

    Failure artifacts never enter SQLite.
    """
    failed_dir = PROMPT_DIR / "failed"
    failed_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_file = (
        failed_dir
        / f"reel_{reel_id}_failed_output.txt"
    )

    header = (
        "Reel2Career extraction failure\n"
        f"Reel: {reel_id}\n"
        f"Reason: {reason}\n"
        + "=" * 60
        + "\n"
    )

    output_file.write_text(
        header + clean_text(raw_output),
        encoding="utf-8",
    )

    return output_file


# ============================================================
# MAIN
# ============================================================

def main():
    print(
        "=== Reel2Career AI Extraction ==="
    )

    print()

    print(
        "Model:",
        MODEL,
    )

    print()

    if not OMNIROUTE.exists():
        raise FileNotFoundError(
            "OmniRoute executable not found:\n"
            + str(OMNIROUTE)
        )

    db = SessionLocal()

    stats = {
        "total": 0,
        "successful": 0,
        "validation_repaired": 0,
        "json_repaired": 0,
        "no_evidence": 0,
        "failed": 0,
        "transport_failures": 0,
        "validation_failures": 0,
        "json_failures": 0,
    }

    try:
        reels = (
            db.query(Reel)
            .filter(
                Reel.id == 7
            )
            .all()
        )

        stats["total"] = len(reels)

        print(
            f"Reels available: "
            f"{len(reels)}"
        )

        print()

        for index, reel in enumerate(
            reels,
            start=1,
        ):
            print(
                f"[{index}/{len(reels)}] "
                f"Reel {reel.id}"
            )

            # ------------------------------------------------
            # IMPORTANT:
            # Everything for ONE reel lives inside this block.
            # A bad reel can never terminate the batch.
            # ------------------------------------------------

            evidence = []

            try:
                evidence = collect_evidence(
                    db,
                    reel.id,
                )

                print(
                    f"    Evidence records: "
                    f"{len(evidence)}"
                )

                if not evidence:
                    stats["no_evidence"] += 1
                    print(
                        "    No evidence records. "
                        "Allowing the model to return an empty/unknown analysis."
                    )

                prompt = build_prompt(
                    reel,
                    evidence,
                )

                print(
                    f"    Prompt size: "
                    f"{len(prompt):,} characters"
                )

                print(
                    "    Writing prompt file..."
                )

                print(
                    "    Sending evidence to "
                    "OmniRoute..."
                )

                parsed = None
                raw_output = ""
                prompt_file = None
                validation_error = None
                validation_repaired = False

                for validation_attempt in range(
                    1,
                    MAX_VALIDATION_ATTEMPTS + 1,
                ):
                    if validation_attempt > 1:
                        print(
                            "    Validation repair "
                            f"attempt {validation_attempt}/"
                            f"{MAX_VALIDATION_ATTEMPTS}..."
                        )

                    current_prompt = prompt

                    if validation_error is not None:
                        current_prompt = (
                            build_validation_retry_prompt(
                                prompt,
                                validation_error,
                                raw_output,
                            )
                        )

                    try:
                        (
                            parsed,
                            raw_output,
                            candidate_prompt_file,
                        ) = run_ai_from_file(
                            current_prompt,
                            reel.id,
                        )
                        prompt_file = candidate_prompt_file

                    except ValueError as exc:
                        stats["json_failures"] += 1

                        if validation_attempt < MAX_VALIDATION_ATTEMPTS:
                            validation_error = str(exc)

                            print(
                                "    JSON extraction failed; "
                                "retrying the reel..."
                            )
                            continue

                        stats["failed"] += 1

                        failed_file = save_failed_output(
                            reel.id,
                            raw_output,
                            str(exc),
                        )

                        print(
                            "    Failed after JSON retries: "
                            + str(exc)
                        )
                        print(
                            "    Failed output saved to: "
                            + str(failed_file)
                        )

                        db.rollback()
                        break

                    # ----------------------------------------
                    # Validate BEFORE any SQLite persistence.
                    # ----------------------------------------

                    print(
                        "    Validating AI evidence..."
                    )

                    try:
                        parsed = validate_ai_result(
                            parsed,
                            evidence,
                        )

                        if validation_attempt > 1:
                            validation_repaired = True

                        break

                    except ValueError as exc:
                        validation_error = str(exc)
                        stats["validation_failures"] += 1

                        print(
                            "    Validation failed: "
                            + validation_error
                        )

                        if (
                            validation_attempt
                            < MAX_VALIDATION_ATTEMPTS
                        ):
                            print(
                                "    Sending a targeted "
                                "validation-repair prompt..."
                            )
                            continue

                        stats["failed"] += 1

                        failed_file = save_failed_output(
                            reel.id,
                            raw_output,
                            validation_error,
                        )

                        print(
                            "    Skipping reel after validation retries."
                        )
                        print(
                            "    Failed AI output saved to: "
                            + str(failed_file)
                        )

                        db.rollback()
                        parsed = None
                        break

                else:
                    stats["failed"] += 1
                    db.rollback()
                    print(
                        "    Skipping reel: "
                        "extraction loop exhausted."
                    )
                    continue

                # If validation never produced a valid result,
                # continue to the NEXT reel.
                if parsed is None:
                    continue

                # ------------------------------------------------
                # Successful extraction
                # ------------------------------------------------

                print(
                    "    Evidence validation passed."
                )

                print(
                    "    AI extraction successful."
                )

                if validation_repaired:
                    stats["validation_repaired"] += 1
                    print(
                        "    Recovered through validation repair."
                    )

                print(
                    "    Topic:",
                    parsed.get(
                        "topic",
                        "unknown",
                    ),
                )

                print(
                    "    Career area:",
                    parsed.get(
                        "career_area",
                        "unknown",
                    ),
                )

                print(
                    "    Career relevance:",
                    normalize_relevance(
                        parsed.get(
                            "career_relevance",
                            0.0,
                        )
                    ),
                )

                print(
                    "    Skills:",
                    len(
                        parsed.get(
                            "skills",
                            [],
                        )
                    ),
                )

                print(
                    "    Direct actions:",
                    len(
                        parsed.get(
                            "actions",
                            [],
                        )
                    ),
                )

                print(
                    "    Suggested next steps:",
                    len(
                        parsed.get(
                            "suggested_next_steps",
                            [],
                        )
                    ),
                )

                print(
                    "    Resources:",
                    len(
                        parsed.get(
                            "resources",
                            [],
                        )
                    ),
                )

                print(
                    "    Claims:",
                    len(
                        parsed.get(
                            "claims",
                            [],
                        )
                    ),
                )

                # ------------------------------------------------
                # SINGLE COMMIT POINT.
                # Nothing is committed until the complete result
                # has passed validation.
                # ------------------------------------------------

                save_analysis(
                    db,
                    reel,
                    parsed,
                    raw_output,
                    evidence,
                )

                db.commit()

                stats["successful"] += 1

                print(
                    "    Saved to SQLite."
                )

                print(
                    "    Provenance persisted."
                )

                print(
                    "    Prompt:",
                    prompt_file,
                )

                print()

            except Exception as exc:
                # --------------------------------------------
                # LAST LINE OF DEFENSE:
                # An unexpected Python/DB error for one reel
                # must not stop tomorrow's 100-reel batch.
                # --------------------------------------------

                db.rollback()
                stats["failed"] += 1

                failed_file = save_failed_output(
                    reel.id,
                    "",
                    "Unexpected reel-level exception: "
                    + repr(exc),
                )

                print(
                    "    Unexpected reel-level failure: "
                    + repr(exc)
                )

                print(
                    "    Failed output saved to: "
                    + str(failed_file)
                )

                print()

                continue

        print(
            "=== AI Extraction Complete ==="
        )

        print()

        print(
            "Batch summary:"
        )

        print(
            f"    Total reels:              {stats['total']}"
        )

        print(
            f"    Successful:               {stats['successful']}"
        )

        print(
            f"    Validation repaired:      {stats['validation_repaired']}"
        )

        print(
            f"    No evidence:              {stats['no_evidence']}"
        )

        print(
            f"    Failed:                   {stats['failed']}"
        )

        print(
            f"    Validation failures:     {stats['validation_failures']}"
        )

        print(
            f"    JSON failures/retries:    {stats['json_failures']}"
        )

    except Exception as exc:
        # Only truly batch-level failures escape here, e.g. database
        # connection/query failure before a reel can be processed.
        db.rollback()

        print()
        print(
            "FATAL BATCH ERROR:",
            str(exc),
        )

        raise

    finally:
        db.close()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
