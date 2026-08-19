"""
extractor.py
------------
The "brain" of the scraper. Instead of writing CSS selectors per university
(which breaks the moment a site redesigns), we hand the cleaned page content
to an LLM and ask it to either:
  (a) pull full faculty records directly off the page, or
  (b) tell us this is a listing page and hand back links to individual
      profile pages so we can go one level deeper.

This is what lets ONE tool work across DTU, an IIT, a random state
university's 2009-era table layout, etc. -- the model reads the page the
way a human would, instead of us hard-coding markup assumptions.

Three providers are supported, picked with --provider in scrape.py:
  - gemini    (free tier: Google AI Studio, no card required)
  - groq      (free tier: fast open models like Llama/Kimi, no card required)
  - anthropic (paid API, best structured-extraction quality)

All three implement the same two methods, so scrape.py doesn't care which
one is behind the scenes.
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional

# ---------------------------------------------------------------------------
# Universal schema every university's data gets normalized into.
# Add fields here if you need more (e.g. "office_location", "orcid_id").
# ---------------------------------------------------------------------------
FIELDS = [
    "name",
    "designation",       # Professor / Associate Professor / Librarian / etc.
    "department",
    "qualification",     # e.g. "Ph.D (IIT Delhi), M.Tech, B.Tech"
    "specialization",
    "email",
    "phone",
    "photo_url",
    "bio",
    "profile_url",
]


@dataclass
class FacultyRecord:
    source_university: str
    source_url: str
    name: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    qualification: Optional[str] = None
    specialization: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    photo_url: Optional[str] = None
    bio: Optional[str] = None
    profile_url: Optional[str] = None
    extraction_confidence: Optional[str] = None  # "high"/"medium"/"low", model self-reported

    def to_dict(self):
        return asdict(self)


# ---------------------------------------------------------------------------
# Shared prompt-building + JSON parsing. Providers differ only in HOW they
# send a prompt and get text back -- the prompts themselves stay identical
# so extraction quality is as consistent as possible across providers.
# ---------------------------------------------------------------------------
class BaseExtractor(ABC):
    def analyze_listing_page(self, url: str, cleaned_text: str, links: list[dict]) -> dict:
        prompt = self._listing_prompt(url, cleaned_text, links)
        raw = self._complete(prompt, max_tokens=8192)
        return self._parse_json(raw)

    def extract_detail_page(self, url: str, cleaned_text: str) -> dict:
        prompt = self._detail_prompt(url, cleaned_text)
        raw = self._complete(prompt, max_tokens=1500)
        return self._parse_json(raw)

    @abstractmethod
    def _complete(self, prompt: str, max_tokens: int) -> str:
        """Send prompt to the provider, return raw text response."""
        raise NotImplementedError

    @staticmethod
    def _listing_prompt(url: str, cleaned_text: str, links: list[dict]) -> str:
        return f"""You are looking at a university department/faculty page.

URL: {url}

Here is the extracted visible text of the page:
---
{cleaned_text[:12000]}
---

Here are the links found on the page (text -> href), which may include
navigation, so use judgement:
---
{json.dumps(links[:200], indent=2)[:8000]}
---

Decide which of these is true:
1. "detail_links" - This is a listing/grid page where each faculty/staff
   member has a name + a link to their OWN profile/detail page for more info.
2. "full_records" - This page already shows complete details for each person
   directly (name, designation, qualification, email, etc.) with no need to
   click through anywhere else.
3. "unknown" - This isn't a faculty/staff listing page at all, or you can't
   tell.

Respond with ONLY valid JSON, no markdown fences, no commentary:

If detail_links:
{{"page_type": "detail_links", "profiles": [{{"name": "<name if visible, else null>", "url": "<absolute or relative href>"}}, ...]}}

If full_records:
{{"page_type": "full_records", "records": [{{"name": "...", "designation": "...", "department": "...", "qualification": "...", "specialization": "...", "email": "...", "phone": "...", "photo_url": "...", "bio": "...", "profile_url": null}}, ...]}}

If unknown:
{{"page_type": "unknown", "reason": "..."}}

Use null for any field you can't find. Do not invent data."""

    @staticmethod
    def _detail_prompt(url: str, cleaned_text: str) -> str:
        return f"""Extract structured information about the faculty/staff
member described on this page.

URL: {url}

Page text:
---
{cleaned_text[:12000]}
---

Respond with ONLY valid JSON, no markdown fences, no commentary, matching
exactly this shape (use null for anything not present -- do not invent data,
do not guess a value that isn't actually on the page):

{{"name": "...", "designation": "...", "department": "...", "qualification": "...", "specialization": "...", "email": "...", "phone": "...", "photo_url": "...", "bio": "...", "extraction_confidence": "high|medium|low"}}"""

    @staticmethod
    def _parse_json(text: str) -> dict:
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`")
            if text.startswith("json"):
                text = text[4:]
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # last-ditch: find the outermost { ... }
            start, end = text.find("{"), text.rfind("}")
            if start != -1 and end != -1:
                return json.loads(text[start:end + 1])
            raise


# ---------------------------------------------------------------------------
# Gemini (free tier via Google AI Studio -- aistudio.google.com/apikey,
# no card required). Generous free daily quota, large context window,
# solid structured JSON output.
# ---------------------------------------------------------------------------
class GeminiExtractor(BaseExtractor):
    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-3.6-flash"):
        from google import genai
        self.client = genai.Client(api_key=api_key or os.environ.get("GEMINI_API_KEY"))
        self.model = model

    def _complete(self, prompt: str, max_tokens: int) -> str:
        resp = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
            config={
                "max_output_tokens": max_tokens,
                "response_mime_type": "application/json",
            },
        )
        return resp.text


# ---------------------------------------------------------------------------
# Groq (free tier via console.groq.com -- no card required). Very fast,
# runs open models (Llama, Kimi, etc). Slightly less reliable at strict
# JSON formatting than Gemini/Claude, so we lean on _parse_json's fallback.
# ---------------------------------------------------------------------------
class GroqExtractor(BaseExtractor):
    def __init__(self, api_key: Optional[str] = None, model: str = "llama-3.3-70b-versatile"):
        from groq import Groq
        self.client = Groq(api_key=api_key or os.environ.get("GROQ_API_KEY"))
        self.model = model

    def _complete(self, prompt: str, max_tokens: int) -> str:
        resp = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.choices[0].message.content


# ---------------------------------------------------------------------------
# Anthropic (paid API -- kept as an option since it's the highest-quality
# extractor, in case you want to switch back once you're past prototyping).
# ---------------------------------------------------------------------------
class AnthropicExtractor(BaseExtractor):
    def __init__(self, api_key: Optional[str] = None, model: str = "claude-sonnet-5"):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model

    def _complete(self, prompt: str, max_tokens: int) -> str:
        resp = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text


def get_extractor(provider: str, model: Optional[str] = None) -> BaseExtractor:
    """Factory -- scrape.py calls this so it doesn't need to know provider details."""
    provider = provider.lower()
    if provider == "gemini":
        return GeminiExtractor(model=model) if model else GeminiExtractor()
    if provider == "groq":
        return GroqExtractor(model=model) if model else GroqExtractor()
    if provider == "anthropic":
        return AnthropicExtractor(model=model) if model else AnthropicExtractor()
    raise ValueError(f"Unknown provider: {provider!r}. Choose gemini, groq, or anthropic.")
