#!/usr/bin/env python3
"""
Scraper ciblé pour construire une base de connaissances RAG depuis impots.gouv.fr.

Le script cible deux surfaces :
1. Les FAQ particulières liées au paiement, aux retards, aux difficultés et au recouvrement.
2. Les guides "Pas-à-pas" des particuliers, souvent servis directement en PDF.

Pré-requis :
    pip install -r requirements.txt
    playwright install chromium

Exemples :
    python3 scrape_impots_knowledge_base.py
    python3 scrape_impots_knowledge_base.py --max-faq 5 --max-guides 3 --min-delay 0 --max-delay 0 --no-playwright
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import time
import unicodedata
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import urljoin, urldefrag, urlparse

import pdfplumber
import requests
from bs4 import BeautifulSoup, Tag
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

try:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    PlaywrightTimeoutError = RuntimeError
    sync_playwright = None


LOGGER = logging.getLogger("impots_scraper")

BASE_URL = "https://www.impots.gouv.fr"
SOURCE_NAME = "impots.gouv.fr"
DEFAULT_OUTPUT = "impots_knowledge_base.json"
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)

# Mots-clés métier demandés par le besoin.
PRIORITY_TERMS = [
    "mise en demeure",
    "retard",
    "majoration",
    "délai de paiement",
    "difficulté",
    "recouvrement",
    "saisie",
    "amende",
    "post stationnement",
]

# Variantes et termes associés utiles pour rattraper les libellés du site.
DISCOVERY_TERMS = [
    "mise en demeure",
    "retard",
    "majoration",
    "delai",
    "difficult",
    "recouvr",
    "saisie",
    "penalit",
    "paiement",
    "payer",
    "amende",
    "mensual",
    "prelev",
    "echeance",
    "rejet",
    "rappel d'impot",
    "remise gracieuse",
    "etalement",
    "solde",
    "messagerie",
    "coordonnees bancaires",
    "rib",
]

ACTION_TERMS = [
    "comment",
    "quand",
    "que faire",
    "obtenir",
    "demander",
    "demarches",
    "en ligne",
    "espace finances publiques",
    "messagerie securisee",
    "etaler",
    "etalement",
    "refuse",
]

# Ces termes écartent les questions sur l'assiette de l'impôt, peu utiles pour ce RAG.
EXCLUDE_TERMS = [
    "taxe d'habitation",
    "taxe fonciere",
    "quels impots dois je payer",
    "quitus fiscal",
    "succession vacante",
    "exonere",
    "locataire",
    "garage",
    "rsa",
]

GUIDE_TERMS = [
    "paie",
    "paiement",
    "amende",
    "messagerie",
    "prelev",
    "rejet",
    "coordonnees bancaires",
    "difficult",
    "delai",
    "espace finances publiques",
    "rendez vous",
]

FAQ_SEED_URLS = [
    f"{BASE_URL}/particulier/payer-mes-impots-taxes",
    f"{BASE_URL}/particulier/presenter-un-recours-aupres-de-la-dgfip",
    f"{BASE_URL}/particulier/jai-des-difficultes-pour-payer-page-en-cours-de-creation-0",
    f"{BASE_URL}/particulier/je-dois-payer-une-amende-ou-un-forfait-de-post-stationnement",
    f"{BASE_URL}/particulier/je-suis-mes-paiements-et-je-gere-mes-prelevements",
]
GUIDE_INDEX_URL = f"{BASE_URL}/pas-a-pas-des-services-en-ligne-des-particuliers"

STOP_MARKERS = [
    "cette reponse vous a t elle ete utile",
    "aucune option n a ete selectionnee",
    "soumettre votre avis",
    "envoyer votre avis",
    "merci votre avis a bien ete pris en compte",
    "partager la page",
    "partager sur facebook",
    "partager sur twitter",
    "partager sur linkedin",
    "questions frequentes",
    "suivez nous",
    "rubriques du site",
    "informations",
    "qualite de service",
    "autres sites",
    "menu institutionnel",
    "menu legal",
]

SKIP_LINE_PATTERNS = [
    re.compile(r"^publie le ", re.IGNORECASE),
    re.compile(r"^lecture \d+", re.IGNORECASE),
    re.compile(r"^imprimer l'article$", re.IGNORECASE),
    re.compile(r"^particulier$", re.IGNORECASE),
    re.compile(r"^haut de page$", re.IGNORECASE),
    re.compile(r"^envoyer votre avis$", re.IGNORECASE),
]

NOISE_URL_SNIPPETS = [
    "/votre-avis-sur-le-site",
    "/contacts",
    "/gestion-des-cookies",
    "/mentions-legales",
    "/accessibilite",
    "/sitemap",
]

FAQ_IRRELEVANT_TERMS = [
    "taux de prelevement a la source",
    "augmenter mon taux",
    "diminuer mon taux",
    "moduler mon taux",
    "variation de revenus",
    "situation de famille",
    "tribunal administratif",
    "tribunal judiciaire",
    "saisine du tribunal",
    "faire appel d un jugement",
]

GUIDE_EXCLUDE_TERMS = [
    "cree mon espace",
    "me connecte",
    "adresse electronique",
    "numero fiscal",
    "mot de passe",
    "declare mes revenus",
    "corrige ma declaration",
    "corriger une erreur",
    "copie d avis d impot",
    "prends rendez vous",
    "signale un changement d adresse",
    "declare un don",
    "timbre fiscal",
    "facture locale",
    "gere mes biens immobiliers",
]

DELAY_SENTENCE_PATTERNS = [
    re.compile(r"\b\d+\s*(?:jour|jours|mois|an|ans|semaine|semaines)\b", re.IGNORECASE),
    re.compile(r"\bj\s*\+\s*\d+\b", re.IGNORECASE),
    re.compile(r"\b\d+\s*%\b", re.IGNORECASE),
    re.compile(r"majoration|penalite|p[ée]nalit|retard|date limite|echeance|[ée]ch[ée]ance", re.IGNORECASE),
]

URL_PATTERN = re.compile(r"https?://[^\s)\]>]+", re.IGNORECASE)


@dataclass(frozen=True)
class LinkCandidate:
    url: str
    text: str


@dataclass
class CrawlTarget:
    url: str
    depth: int
    source_text: str = ""


@dataclass
class KnowledgeRecord:
    source: str
    url: str
    type_document: str
    categorie: str
    titre_ou_question: str
    contenu: str
    delais_mentionnes: Optional[str]
    liens_demarches: list[str] = field(default_factory=list)


def fold_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    without_accents = "".join(char for char in normalized if not unicodedata.combining(char))
    lowered = without_accents.lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return lowered.strip()


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip(" \n\t")


def ordered_unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value:
            continue
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def canonicalize_url(url: str, base_url: str = BASE_URL) -> Optional[str]:
    if not url:
        return None
    if url.startswith(("#", "mailto:", "tel:", "javascript:")):
        return None
    absolute = urljoin(base_url, url)
    absolute, _ = urldefrag(absolute)
    parsed = urlparse(absolute)
    if parsed.scheme not in {"http", "https"}:
        return None
    if "impots.gouv.fr" not in parsed.netloc:
        return None
    normalized_path = parsed.path or "/"
    if normalized_path != "/":
        normalized_path = normalized_path.rstrip("/")
    return parsed._replace(path=normalized_path, query="", fragment="").geturl()


def is_question_url(url: str) -> bool:
    return "/particulier/questions/" in url


def is_pdf_url(url: str) -> bool:
    return url.lower().endswith(".pdf")


def is_guide_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.path.startswith("/node/") or is_pdf_url(url)


def is_listing_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.path == "/particulier/questions":
        return True
    if parsed.path == "/pas-a-pas-des-services-en-ligne-des-particuliers":
        return True
    return parsed.path.startswith("/particulier/") and not is_question_url(url)


def contains_any_term(text: str, terms: Iterable[str]) -> bool:
    folded = fold_text(text)
    return any(fold_text(term) in folded for term in terms)


def is_excluded_topic(text: str, *, for_guides: bool) -> bool:
    if for_guides:
        return contains_any_term(text, GUIDE_EXCLUDE_TERMS)
    return contains_any_term(text, EXCLUDE_TERMS) or contains_any_term(text, FAQ_IRRELEVANT_TERMS)


def relevance_score(text: str, url: str, *, for_guides: bool) -> int:
    haystack = f"{text} {url}"
    folded = fold_text(haystack)

    score = 0
    for term in PRIORITY_TERMS:
        if fold_text(term) in folded:
            score += 3
    for term in DISCOVERY_TERMS if not for_guides else GUIDE_TERMS:
        if fold_text(term) in folded:
            score += 1
    for term in ACTION_TERMS:
        if fold_text(term) in folded:
            score += 1
    return score


def should_follow_faq_link(text: str, url: str) -> bool:
    if not (is_question_url(url) or is_listing_url(url)):
        return False
    if any(snippet in url for snippet in NOISE_URL_SNIPPETS):
        return False
    if is_excluded_topic(f"{text} {url}", for_guides=False):
        return False
    score = relevance_score(text, url, for_guides=False)
    return score >= 3 or contains_any_term(url, PRIORITY_TERMS)


def should_follow_guide_link(text: str, url: str) -> bool:
    if not is_guide_url(url):
        return False
    if is_excluded_topic(f"{text} {url}", for_guides=True):
        return False
    score = relevance_score(text, url, for_guides=True)
    return score >= 1


def infer_category(title: str, content: str, url: str) -> str:
    haystack = fold_text(f"{title} {content} {url}")
    if any(term in haystack for term in ["mise en demeure", "saisie", "recouvr"]):
        return "Recouvrement et poursuites"
    if any(term in haystack for term in ["majoration", "penalit", "retard"]):
        return "Majoration et retard"
    if any(term in haystack for term in ["difficulte", "delai", "etal", "remise gracieuse", "rappel d'impot"]):
        return "Difficultés de paiement"
    if any(term in haystack for term in ["amende", "post stationnement", "fps"]):
        return "Amendes et forfaits"
    if any(term in haystack for term in ["prelev", "mensual", "rib", "coordonnees bancaires", "echeance"]):
        return "Paiement et prélèvements"
    return "Paiement des particuliers"


def extract_delay_sentences(text: str) -> Optional[str]:
    cleaned = clean_text(text)
    if not cleaned:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", cleaned.replace("\n", " "))
    matches: list[str] = []
    for sentence in sentences:
        sentence = clean_text(sentence)
        if not sentence:
            continue
        if any(pattern.search(sentence) for pattern in DELAY_SENTENCE_PATTERNS):
            matches.append(sentence)
    unique_matches = ordered_unique(matches)
    return " | ".join(unique_matches) if unique_matches else None


def extract_navigation_paths(text: str) -> list[str]:
    paths: list[str] = []
    for line in text.splitlines():
        folded = fold_text(line)
        if "selectionnez" not in folded and "rubrique" not in folded and "chemin" not in folded:
            continue
        quoted_segments = re.findall(r"[«\"]\s*([^«»\"]+?)\s*[»\"]", line)
        if len(quoted_segments) >= 2:
            paths.append(" > ".join(clean_text(segment) for segment in quoted_segments))
    return ordered_unique(paths)


def should_skip_line(text: str) -> bool:
    normalized = clean_text(text)
    if not normalized:
        return True
    if len(normalized) == 1:
        return True
    return any(pattern.search(normalized) for pattern in SKIP_LINE_PATTERNS)


def strip_leading_article_metadata(text: str) -> str:
    text = re.sub(
        r"^Publie le .*?(?:Lecture\s*\d+\s*minute(?:s)?)\s*",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"^Publié le .*?(?:Lecture\s*\d+\s*minute(?:s)?)\s*",
        "",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return clean_text(text)


class ImpotsKnowledgeBaseScraper:
    def __init__(
        self,
        *,
        min_delay: float,
        max_delay: float,
        timeout: int,
        max_depth: int,
        use_playwright: bool,
        user_agent: str,
    ) -> None:
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.timeout = timeout
        self.max_depth = max_depth
        self.use_playwright = use_playwright and sync_playwright is not None
        self.user_agent = user_agent
        self.session = self._build_session()
        self.random = random.Random()
        self._playwright = None
        self._browser = None
        self._context = None

    def __enter__(self) -> "ImpotsKnowledgeBaseScraper":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=3,
            connect=3,
            read=3,
            status=3,
            backoff_factor=1.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        session.headers.update(
            {
                "User-Agent": self.user_agent,
                "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.7,en;q=0.6",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )
        return session

    def _wait(self) -> None:
        if self.max_delay <= 0:
            return
        delay = self.random.uniform(self.min_delay, self.max_delay)
        time.sleep(delay)

    def _get(self, url: str) -> requests.Response:
        self._wait()
        response = self.session.get(url, timeout=self.timeout, allow_redirects=True)
        response.raise_for_status()
        return response

    def _ensure_playwright_context(self):
        if not self.use_playwright:
            return None
        if self._context is not None:
            return self._context
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=True)
        self._context = self._browser.new_context(user_agent=self.user_agent, locale="fr-FR")
        return self._context

    def _fetch_html_with_playwright(self, url: str) -> Optional[str]:
        if not self.use_playwright:
            return None
        try:
            self._wait()
            context = self._ensure_playwright_context()
            page = context.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=self.timeout * 1000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except PlaywrightTimeoutError:
                pass
            html = page.content()
            page.close()
            return html
        except Exception as exc:
            LOGGER.warning("Fallback Playwright impossible pour %s: %s", url, exc)
            return None

    def fetch_document(self, url: str) -> tuple[str, str, bytes | str]:
        response = self._get(url)
        final_url = canonicalize_url(response.url, response.url) or response.url
        content_type = response.headers.get("content-type", "").lower()
        if "pdf" in content_type or is_pdf_url(final_url):
            return final_url, "pdf", response.content
        return final_url, "html", response.text

    def fetch_html(self, url: str) -> tuple[str, Optional[str]]:
        final_url, kind, payload = self.fetch_document(url)
        if kind != "html":
            return final_url, None
        return final_url, payload

    def extract_links(self, html: str, base_url: str) -> list[LinkCandidate]:
        soup = BeautifulSoup(html, "lxml")
        container = soup.select_one("main#main-content") or soup.find("main") or soup.body or soup

        for selector in ["header", "footer", "nav", "aside", "script", "style", "noscript"]:
            for node in container.select(selector):
                node.decompose()

        links: list[LinkCandidate] = []
        for anchor in container.select("a[href]"):
            href = anchor.get("href", "")
            normalized = canonicalize_url(href, base_url)
            if not normalized:
                continue
            if any(snippet in normalized for snippet in NOISE_URL_SNIPPETS):
                continue
            text = clean_text(anchor.get_text(" ", strip=True))
            links.append(LinkCandidate(url=normalized, text=text))
        return ordered_unique_links(links)

    def extract_main_text_and_links(self, html: str, url: str) -> tuple[str, list[str], str]:
        soup = BeautifulSoup(html, "lxml")
        container = soup.select_one("main#main-content") or soup.find("main") or soup.find("article") or soup.body
        if container is None:
            return "", [], ""

        for selector in ["header", "footer", "nav", "aside", "script", "style", "noscript", "svg", "form"]:
            for node in container.select(selector):
                node.decompose()

        title_tag = soup.find("h1") or container.find("h1")
        title = clean_text(title_tag.get_text(" ", strip=True)) if title_tag else ""

        blocks: list[str] = []
        links: list[str] = []
        seen_blocks: set[str] = set()

        for element in container.find_all(["h2", "h3", "p", "li"], recursive=True):
            if not isinstance(element, Tag):
                continue
            text = clean_text(element.get_text(" ", strip=True))
            folded = fold_text(text)
            if any(marker in folded for marker in STOP_MARKERS):
                break
            if should_skip_line(text):
                continue

            if element.name in {"h2", "h3"}:
                block = f"{text}:"
            elif element.name == "li":
                block = f"- {text}"
            else:
                block = text

            if block in seen_blocks:
                continue
            seen_blocks.add(block)
            blocks.append(block)

            for anchor in element.select("a[href]"):
                normalized = canonicalize_url(anchor.get("href", ""), url)
                if normalized:
                    links.append(normalized)

        content = strip_leading_article_metadata(clean_text("\n".join(blocks)))
        if not content:
            content = self._extract_text_fallback(container, title)
        return title, ordered_unique(links), content

    @staticmethod
    def _extract_text_fallback(container: Tag, title: str) -> str:
        blocks: list[str] = []
        seen_blocks: set[str] = set()

        for raw_text in container.stripped_strings:
            text = clean_text(raw_text)
            if not text:
                continue
            folded = fold_text(text)
            if any(marker in folded for marker in STOP_MARKERS):
                break
            if should_skip_line(text):
                continue
            if title and text == title:
                continue
            if text in seen_blocks:
                continue
            seen_blocks.add(text)
            blocks.append(text)

        return strip_leading_article_metadata(clean_text("\n".join(blocks)))

    def extract_pdf_text(self, payload: bytes) -> str:
        lines_by_page: list[list[str]] = []
        header_footer_candidates: Counter[str] = Counter()

        with pdfplumber.open(BytesIO(payload)) as pdf:
            for page in pdf.pages:
                text = page.extract_text(x_tolerance=2, y_tolerance=3) or ""
                lines = [clean_text(line) for line in text.splitlines() if clean_text(line)]
                lines_by_page.append(lines)
                for line in lines[:3] + lines[-3:]:
                    if line:
                        header_footer_candidates[fold_text(line)] += 1

        if not lines_by_page:
            return ""

        threshold = max(2, int(len(lines_by_page) * 0.6 + 0.5))
        repeated_margin_lines = {
            normalized_line
            for normalized_line, count in header_footer_candidates.items()
            if count >= threshold
        }

        cleaned_pages: list[str] = []
        for lines in lines_by_page:
            kept_lines: list[str] = []
            for index, line in enumerate(lines):
                normalized = fold_text(line)
                is_margin = index < 3 or index >= max(len(lines) - 3, 0)
                if is_margin and normalized in repeated_margin_lines:
                    continue
                if re.fullmatch(r"\d+(?:/\d+)?", line):
                    continue
                if normalized in {"impots.gouv.fr", "direction generale des finances publiques"}:
                    continue
                kept_lines.append(line)
            cleaned_pages.append(self._merge_wrapped_pdf_lines(kept_lines))

        return clean_text("\n\n".join(page for page in cleaned_pages if page))

    @staticmethod
    def _merge_wrapped_pdf_lines(lines: list[str]) -> str:
        blocks: list[str] = []
        current = ""
        for line in lines:
            if not line:
                if current:
                    blocks.append(current.strip())
                    current = ""
                continue
            if line.startswith(("•", "-", "*")) or line.endswith(":"):
                if current:
                    blocks.append(current.strip())
                current = line
                blocks.append(current.strip())
                current = ""
                continue
            if not current:
                current = line
                continue
            if current.endswith("-"):
                current = current[:-1] + line.lstrip()
            else:
                current = f"{current} {line}"
        if current:
            blocks.append(current.strip())
        return clean_text("\n".join(blocks))

    def scrape_faq(self, *, max_documents: Optional[int]) -> list[KnowledgeRecord]:
        # Le site n'exposant pas de point d'entrée de recherche publique stable,
        # on simule une recherche métier en partant des pages semences puis en
        # ne suivant que les liens dont le texte ou l'URL correspondent aux thèmes ciblés.
        queue: deque[CrawlTarget] = deque(CrawlTarget(url=url, depth=0) for url in FAQ_SEED_URLS)
        visited: set[str] = set()
        collected: list[KnowledgeRecord] = []

        while queue and (max_documents is None or len(collected) < max_documents):
            target = queue.popleft()
            normalized_target = canonicalize_url(target.url, target.url)
            if not normalized_target or normalized_target in visited:
                continue
            visited.add(normalized_target)
            LOGGER.info("FAQ crawl: %s", normalized_target)

            try:
                final_url, html = self.fetch_html(normalized_target)
            except requests.RequestException as exc:
                LOGGER.warning("Impossible de récupérer %s: %s", normalized_target, exc)
                continue

            if not html:
                continue

            if is_question_url(final_url):
                record = self._build_faq_record(final_url, html, source_text=target.source_text)
                if record is None and self.use_playwright:
                    fallback_html = self._fetch_html_with_playwright(final_url)
                    if fallback_html:
                        record = self._build_faq_record(final_url, fallback_html, source_text=target.source_text)
                if record is not None:
                    collected.append(record)
                    if max_documents is not None and len(collected) >= max_documents:
                        break

            if target.depth >= self.max_depth:
                continue

            for link in self.extract_links(html, final_url):
                if should_follow_faq_link(link.text, link.url):
                    queue.append(CrawlTarget(url=link.url, depth=target.depth + 1, source_text=link.text))

        return deduplicate_records(collected)

    def scrape_guides(self, *, max_documents: Optional[int]) -> list[KnowledgeRecord]:
        try:
            final_url, html = self.fetch_html(GUIDE_INDEX_URL)
        except requests.RequestException as exc:
            LOGGER.warning("Impossible de récupérer l'index des guides: %s", exc)
            return []

        if not html:
            return []

        candidates = [
            link
            for link in self.extract_links(html, final_url)
            if should_follow_guide_link(link.text, link.url)
        ]

        collected: list[KnowledgeRecord] = []
        for candidate in candidates:
            if max_documents is not None and len(collected) >= max_documents:
                break
            LOGGER.info("Guide crawl: %s", candidate.url)
            try:
                record = self._build_guide_record(candidate)
            except requests.RequestException as exc:
                LOGGER.warning("Impossible de récupérer le guide %s: %s", candidate.url, exc)
                continue
            if record is not None:
                collected.append(record)
        return deduplicate_records(collected)

    def _build_faq_record(self, url: str, html: str, *, source_text: str) -> Optional[KnowledgeRecord]:
        title, content_links, content = self.extract_main_text_and_links(html, url)
        title = title or clean_text(source_text)
        if not title or not content:
            return None
        if is_excluded_topic(f"{title} {url}", for_guides=False):
            return None
        if relevance_score(title + " " + content[:800], url, for_guides=False) < 3:
            return None

        links_demarches = ordered_unique(content_links + extract_navigation_paths(content))
        return KnowledgeRecord(
            source=SOURCE_NAME,
            url=url,
            type_document="FAQ",
            categorie=infer_category(title, content, url),
            titre_ou_question=title,
            contenu=content,
            delais_mentionnes=extract_delay_sentences(content),
            liens_demarches=links_demarches,
        )

    def _build_guide_record(self, candidate: LinkCandidate) -> Optional[KnowledgeRecord]:
        final_url, kind, payload = self.fetch_document(candidate.url)

        if kind == "pdf":
            try:
                content = self.extract_pdf_text(payload)
            except Exception as exc:
                LOGGER.warning("PDF corrompu ou illisible ignoré %s: %s", final_url, exc)
                return None
            title = clean_text(candidate.text) or self._guess_title_from_pdf_text(content)
            if not title or not content:
                return None
            if is_excluded_topic(f"{title} {final_url}", for_guides=True):
                return None
            if relevance_score(title + " " + content[:800], final_url, for_guides=True) < 1:
                return None
            links_demarches = ordered_unique([final_url] + extract_navigation_paths(content) + URL_PATTERN.findall(content))
            return KnowledgeRecord(
                source=SOURCE_NAME,
                url=final_url,
                type_document="Guide PDF",
                categorie=infer_category(title, content, final_url),
                titre_ou_question=title,
                contenu=content,
                delais_mentionnes=extract_delay_sentences(content),
                liens_demarches=links_demarches,
            )

        html = payload
        pdf_links = [link for link in self.extract_links(html, final_url) if is_pdf_url(link.url)]
        if pdf_links:
            preferred_pdf = pdf_links[0]
            inherited_text = candidate.text or preferred_pdf.text
            return self._build_guide_record(LinkCandidate(url=preferred_pdf.url, text=inherited_text))

        title, content_links, content = self.extract_main_text_and_links(html, final_url)
        title = title or clean_text(candidate.text)
        if not title or not content:
            return None
        if is_excluded_topic(f"{title} {final_url}", for_guides=True):
            return None
        if relevance_score(title + " " + content[:800], final_url, for_guides=True) < 1:
            return None

        links_demarches = ordered_unique(content_links + extract_navigation_paths(content))
        return KnowledgeRecord(
            source=SOURCE_NAME,
            url=final_url,
            type_document="Guide PDF",
            categorie=infer_category(title, content, final_url),
            titre_ou_question=title,
            contenu=content,
            delais_mentionnes=extract_delay_sentences(content),
            liens_demarches=links_demarches,
        )

    @staticmethod
    def _guess_title_from_pdf_text(text: str) -> str:
        for line in text.splitlines():
            cleaned = clean_text(line)
            if cleaned and len(cleaned) <= 160:
                return cleaned
        return ""


def ordered_unique_links(links: Iterable[LinkCandidate]) -> list[LinkCandidate]:
    seen: set[str] = set()
    deduplicated: list[LinkCandidate] = []
    for link in links:
        if link.url in seen:
            continue
        seen.add(link.url)
        deduplicated.append(link)
    return deduplicated


def deduplicate_records(records: Iterable[KnowledgeRecord]) -> list[KnowledgeRecord]:
    seen: set[tuple[str, str]] = set()
    deduplicated: list[KnowledgeRecord] = []
    for record in records:
        key = (record.type_document, record.url)
        if key in seen:
            continue
        seen.add(key)
        deduplicated.append(record)
    return deduplicated


def write_records(records: list[KnowledgeRecord], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = [asdict(record) for record in records]
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape impots.gouv.fr pour alimenter une base RAG.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Chemin du fichier JSON de sortie.")
    parser.add_argument("--min-delay", type=float, default=2.0, help="Délai minimum entre deux requêtes.")
    parser.add_argument("--max-delay", type=float, default=4.0, help="Délai maximum entre deux requêtes.")
    parser.add_argument("--timeout", type=int, default=45, help="Timeout HTTP en secondes.")
    parser.add_argument("--max-depth", type=int, default=2, help="Profondeur maximale de crawl FAQ.")
    parser.add_argument("--max-faq", type=int, default=None, help="Limite optionnelle du nombre de FAQ.")
    parser.add_argument("--max-guides", type=int, default=None, help="Limite optionnelle du nombre de guides.")
    parser.add_argument(
        "--no-playwright",
        action="store_true",
        help="Désactive le fallback Playwright et force un scraping requests/BeautifulSoup uniquement.",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        help="User-Agent HTTP à utiliser pour les requêtes.",
    )
    parser.add_argument("--log-level", default="INFO", help="Niveau de logs (DEBUG, INFO, WARNING...).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO), format="%(levelname)s %(message)s")

    output_path = Path(args.output)
    with ImpotsKnowledgeBaseScraper(
        min_delay=args.min_delay,
        max_delay=max(args.min_delay, args.max_delay),
        timeout=args.timeout,
        max_depth=args.max_depth,
        use_playwright=not args.no_playwright,
        user_agent=args.user_agent,
    ) as scraper:
        faq_records = scraper.scrape_faq(max_documents=args.max_faq)
        guide_records = scraper.scrape_guides(max_documents=args.max_guides)

    records = deduplicate_records(faq_records + guide_records)
    write_records(records, output_path)
    LOGGER.info("%s documents écrits dans %s", len(records), output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())