#!/usr/bin/env python3
"""
Scrape la FAQ et le parcours Particulier de l'ANTAI pour produire un JSON prêt
pour un pipeline RAG.

Installation:
    python3 -m pip install playwright beautifulsoup4
    python3 -m playwright install chromium

Exécution:
    python3 scrape_antai.py
    python3 scrape_antai.py --headed --output antai_knowledge_base.json
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import sys
import time
from collections import deque
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None  # type: ignore[assignment]

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
    from playwright.sync_api import sync_playwright
except ImportError:
    PlaywrightError = Exception  # type: ignore[assignment]
    PlaywrightTimeoutError = Exception  # type: ignore[assignment]
    sync_playwright = None  # type: ignore[assignment]

BASE_URL = "https://www.antai.gouv.fr"
FAQ_URL = f"{BASE_URL}/faq/"
PARTICULIER_ROOT_URL = f"{BASE_URL}/particulier/"
PARTICULIER_SEED_URL = f"{BASE_URL}/particulier/vous-avez-recu-une-amende"
KNOWN_PARTICULIER_URLS = [
    PARTICULIER_SEED_URL,
    f"{BASE_URL}/particulier/paiement",
    f"{BASE_URL}/particulier/designation-ou-contestation",
    f"{BASE_URL}/particulier/suivre-mon-dossier-infraction",
    f"{BASE_URL}/designation-frauduleuse-si-vous-etes-victime-comment-signaler-votre-situation",
]
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)
HTTP_HEADERS = {
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "DNT": "1",
    "Upgrade-Insecure-Requests": "1",
}
TOTAL_RESULTS_PATTERN = re.compile(r"(\d+)\s+r[ée]sultats?\s+trouv[ée]s", re.IGNORECASE)
DELAY_PATTERN = re.compile(
    r"\b(?:dans\s+un\s+d[ée]lai\s+de\s+|sous\s+)?\d+\s*"
    r"(?:jour|jours|semaine|semaines|mois|an|ans|heure|heures)\b",
    re.IGNORECASE,
)
CATEGORY_SPLIT_PATTERN = re.compile(r"\s*\|\s*|\s*\n+\s*")
SKIP_BLOCK_ANCESTOR_CLASSES = {
    "bloc-question",
    "reponse",
    "toggleAccordion",
    "contentinfo",
    "carousel",
    "carousel-inner",
    "carousel-control",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extrait la FAQ et les pages Particulier de l'ANTAI en JSON."
    )
    parser.add_argument(
        "--output",
        default="antai_knowledge_base.json",
        help="Chemin du fichier JSON de sortie.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Ouvre Chromium en mode visible si le mode headless est bloqué.",
    )
    parser.add_argument(
        "--min-delay",
        type=float,
        default=1.0,
        help="Délai minimal entre deux navigations HTTP.",
    )
    parser.add_argument(
        "--max-delay",
        type=float,
        default=3.0,
        help="Délai maximal entre deux navigations HTTP.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=45000,
        help="Timeout Playwright par navigation ou action.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=2,
        help="Nombre de tentatives supplémentaires si une page répond mal.",
    )
    return parser


def ensure_dependencies() -> None:
    if BeautifulSoup is None or sync_playwright is None:
        raise SystemExit(
            "Dépendances manquantes.\n"
            "Installez-les avec :\n"
            "  python3 -m pip install playwright beautifulsoup4\n"
            "  python3 -m playwright install chromium\n"
        )


def normalize_url(url: str) -> str:
    parsed = urlparse(urljoin(BASE_URL, url))
    return urlunparse(parsed._replace(fragment=""))


def replace_query_param(url: str, name: str, value: str | None) -> str:
    parsed = urlparse(url)
    pairs = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True) if key != name]
    if value is not None:
        pairs.append((name, value))
    return urlunparse(parsed._replace(query=urlencode(pairs), fragment=""))


def build_faq_page_url(category_url: str, page_number: int) -> str:
    if page_number <= 1:
        return replace_query_param(category_url, "page", None)
    return replace_query_param(category_url, "page", str(page_number))


def unique_preserve_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def normalize_whitespace(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u00ad", "")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_category_label(text: str) -> str:
    parts = [
        normalize_whitespace(part)
        for part in CATEGORY_SPLIT_PATTERN.split(text)
        if normalize_whitespace(part)
    ]
    return " | ".join(unique_preserve_order(parts))


def polite_pause(min_delay: float, max_delay: float, reason: str) -> None:
    if max_delay < min_delay:
        min_delay, max_delay = max_delay, min_delay
    delay = random.uniform(min_delay, max_delay)
    print(f"[pause] {reason}: {delay:.1f}s")
    time.sleep(delay)


def short_pause(page: Any, min_ms: int = 120, max_ms: int = 280) -> None:
    page.wait_for_timeout(random.randint(min_ms, max_ms))


def goto_with_retries(
    page: Any,
    url: str,
    *,
    min_delay: float,
    max_delay: float,
    retries: int,
) -> str:
    target = normalize_url(url)
    last_error: Exception | None = None

    for attempt in range(1, retries + 2):
        polite_pause(min_delay, max_delay, f"navigation vers {target}")
        try:
            response = page.goto(target, wait_until="domcontentloaded")
            page.wait_for_timeout(random.randint(900, 1600))
            if response is not None and response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}")
            return normalize_url(page.url)
        except (PlaywrightTimeoutError, PlaywrightError, RuntimeError) as exc:
            last_error = exc
            print(
                f"[warn] Échec de navigation ({attempt}/{retries + 1}) sur {target}: {exc}",
                file=sys.stderr,
            )
            page.wait_for_timeout(400 * attempt)

    raise RuntimeError(f"Impossible de charger {target}") from last_error


def try_goto(
    page: Any,
    url: str,
    *,
    min_delay: float,
    max_delay: float,
    retries: int,
) -> str | None:
    try:
        return goto_with_retries(
            page,
            url,
            min_delay=min_delay,
            max_delay=max_delay,
            retries=retries,
        )
    except Exception as exc:
        print(f"[warn] Page ignorée {url}: {exc}", file=sys.stderr)
        return None


def expand_accordions(page: Any) -> None:
    # Beaucoup de réponses sont déjà dans le DOM, mais l'ouverture des accordéons
    # reste utile pour les cas où le site injecte du contenu au clic.
    try:
        buttons = page.locator('button[aria-label="bouton accordeon"]')
        count = buttons.count()
    except Exception:
        return

    for index in range(count):
        button = buttons.nth(index)
        try:
            expanded = (button.get_attribute("aria-expanded") or "").lower() == "true"
            if expanded:
                continue
            button.scroll_into_view_if_needed(timeout=2500)
            button.click(timeout=4000)
            short_pause(page)
        except Exception as exc:
            print(f"[warn] Accordéon non ouvert: {exc}", file=sys.stderr)


def clean_fragment_text(fragment: Any) -> str:
    if fragment is None:
        return ""

    soup = BeautifulSoup(str(fragment), "html.parser")
    for node in soup.select(
        "script, style, noscript, button, svg, img, picture, source, figure, video, audio, iframe"
    ):
        node.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")

    lines: list[str] = []
    for teaser in soup.select(".chapeau-accordeon"):
        teaser_text = normalize_whitespace(teaser.get_text(" ", strip=True))
        if teaser_text:
            lines.append(teaser_text)

    for element in soup.find_all(["h1", "h2", "h3", "h4", "p", "li"]):
        if element.name == "p" and element.find_parent("li") is not None:
            continue
        text = normalize_whitespace(element.get_text(" ", strip=True))
        if not text:
            continue
        if element.name == "li":
            lines.append(f"- {text}")
        else:
            lines.append(text)

    if not lines:
        return normalize_whitespace(soup.get_text("\n", strip=True))

    return normalize_whitespace("\n".join(unique_preserve_order(lines)))


def extract_links(fragment: Any) -> list[str]:
    if fragment is None:
        return []

    urls: list[str] = []
    for anchor in fragment.select("a[href]"):
        href = normalize_url(anchor.get("href", "").strip())
        scheme = urlparse(href).scheme.lower()
        if scheme in {"http", "https"}:
            urls.append(href)
    return unique_preserve_order(urls)


def extract_delays(text: str) -> str | None:
    matches = unique_preserve_order(match.group(0) for match in DELAY_PATTERN.finditer(text))
    return "; ".join(matches) if matches else None


def build_entry(
    *,
    url: str,
    categorie: str,
    question: str,
    response: str,
    links: list[str],
) -> dict[str, Any] | None:
    response = normalize_whitespace(response)
    categorie = normalize_category_label(categorie)
    question = normalize_whitespace(question)
    if not response or not question:
        return None

    return {
        "source": "antai.gouv.fr",
        "url": normalize_url(url),
        "categorie": categorie or "ANTAI",
        "question": question,
        "reponse": response,
        "delais_mentionnes": extract_delays(response),
        "liens_demarches": links,
    }


def parse_total_results(soup: Any) -> int | None:
    main = soup.select_one("main") or soup
    text = normalize_whitespace(main.get_text(" ", strip=True))
    match = TOTAL_RESULTS_PATTERN.search(text)
    return int(match.group(1)) if match else None


def guess_faq_page_count(soup: Any, articles_count: int) -> int:
    page_count = 1
    total_results = parse_total_results(soup)
    if total_results and articles_count:
        page_count = max(page_count, math.ceil(total_results / articles_count))

    for anchor in soup.select("main a"):
        label = normalize_whitespace(anchor.get_text(" ", strip=True))
        if label.isdigit():
            page_count = max(page_count, int(label))

    return page_count


def discover_faq_category_urls(
    page: Any,
    *,
    min_delay: float,
    max_delay: float,
    retries: int,
) -> list[str]:
    current_url = goto_with_retries(
        page,
        FAQ_URL,
        min_delay=min_delay,
        max_delay=max_delay,
        retries=retries,
    )
    print(f"[info] FAQ chargée: {current_url}")
    soup = BeautifulSoup(page.content(), "html.parser")

    category_urls: list[str] = []
    for anchor in soup.select('main a[href*="field_theme="]'):
        href = anchor.get("href", "")
        url = normalize_url(href)
        parsed = urlparse(url)
        if parsed.netloc != urlparse(BASE_URL).netloc:
            continue
        if parsed.path.rstrip("/") != "/faq":
            continue
        category_urls.append(replace_query_param(url, "page", None))

    return unique_preserve_order(category_urls)


def parse_faq_entries_from_page(current_url: str, soup: Any) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    articles = soup.select("main article.bs-accordeon")
    if not articles:
        articles = soup.select('main article[class*="accordeon"]')

    for article in articles:
        category = clean_fragment_text(article.select_one(".theme")) or "FAQ"

        question_node = article.select_one(".question span")
        if question_node is None:
            question_node = article.select_one(".question")
        question = clean_fragment_text(question_node)
        if question.startswith(category):
            question = normalize_whitespace(question[len(category) :])

        response_node = article.select_one(".reponse")
        response = clean_fragment_text(response_node)
        links = extract_links(response_node)
        entry = build_entry(
            url=current_url,
            categorie=category,
            question=question,
            response=response,
            links=links,
        )
        if entry is not None:
            entries.append(entry)

    return entries


def scrape_faq_category(
    page: Any,
    category_url: str,
    *,
    min_delay: float,
    max_delay: float,
    retries: int,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen_questions: set[tuple[str, str]] = set()

    first_url = goto_with_retries(
        page,
        category_url,
        min_delay=min_delay,
        max_delay=max_delay,
        retries=retries,
    )
    expand_accordions(page)
    first_soup = BeautifulSoup(page.content(), "html.parser")
    first_articles = first_soup.select("main article.bs-accordeon")
    total_pages = guess_faq_page_count(first_soup, len(first_articles))

    for page_number in range(1, total_pages + 1):
        target_url = build_faq_page_url(category_url, page_number)
        current_url = first_url if page_number == 1 else goto_with_retries(
            page,
            target_url,
            min_delay=min_delay,
            max_delay=max_delay,
            retries=retries,
        )
        if page_number != 1:
            expand_accordions(page)
        soup = first_soup if page_number == 1 else BeautifulSoup(page.content(), "html.parser")
        page_entries = parse_faq_entries_from_page(current_url, soup)

        for entry in page_entries:
            key = (entry["categorie"], entry["question"])
            if key in seen_questions:
                continue
            seen_questions.add(key)
            entries.append(entry)

    return entries


def is_particulier_candidate(url: str, allowed_paths: set[str] | None = None) -> bool:
    parsed = urlparse(normalize_url(url))
    if parsed.netloc != urlparse(BASE_URL).netloc:
        return False
    path = parsed.path.rstrip("/") or "/"
    if path.startswith("/particulier"):
        return True
    if allowed_paths and path in allowed_paths:
        return True
    return path.endswith("designation-frauduleuse-si-vous-etes-victime-comment-signaler-votre-situation")


def discover_particulier_urls(
    page: Any,
    *,
    min_delay: float,
    max_delay: float,
    retries: int,
) -> list[str]:
    discovered = {normalize_url(url) for url in KNOWN_PARTICULIER_URLS}
    allowed_paths = {urlparse(url).path.rstrip("/") for url in discovered}

    # La racine /particulier/ renvoie fréquemment 403; on tente quand même puis on
    # bascule sur une sous-page publique pour découvrir le menu réel du parcours.
    root_url = try_goto(
        page,
        PARTICULIER_ROOT_URL,
        min_delay=min_delay,
        max_delay=max_delay,
        retries=retries,
    )
    candidate_seeds = [PARTICULIER_SEED_URL, *KNOWN_PARTICULIER_URLS]
    if root_url is not None:
        candidate_seeds.insert(0, root_url)

    menu_urls: list[str] = []
    for seed in candidate_seeds:
        current_url = try_goto(
            page,
            seed,
            min_delay=min_delay,
            max_delay=max_delay,
            retries=retries,
        )
        if current_url is None:
            continue
        soup = BeautifulSoup(page.content(), "html.parser")
        for anchor in soup.select('nav[aria-label="menu-lvl-1"] a[href], .menu-level1 a[href]'):
            url = normalize_url(anchor.get("href", ""))
            if is_particulier_candidate(url, allowed_paths):
                menu_urls.append(url)
        if menu_urls:
            break

    discovered.update(menu_urls)
    allowed_paths.update(urlparse(url).path.rstrip("/") for url in discovered)

    queue: deque[str] = deque(sorted(discovered))
    visited: set[str] = set()

    while queue:
        url = queue.popleft()
        if url in visited:
            continue
        visited.add(url)
        current_url = try_goto(
            page,
            url,
            min_delay=min_delay,
            max_delay=max_delay,
            retries=retries,
        )
        if current_url is None:
            continue

        soup = BeautifulSoup(page.content(), "html.parser")
        for anchor in soup.select("main a[href]"):
            candidate_url = normalize_url(anchor.get("href", ""))
            if not is_particulier_candidate(candidate_url, allowed_paths):
                continue
            if candidate_url not in discovered:
                discovered.add(candidate_url)
                allowed_paths.add(urlparse(candidate_url).path.rstrip("/"))
                queue.append(candidate_url)

    return sorted(discovered)


def should_skip_particulier_block(tag: Any) -> bool:
    if tag.find_parent(["nav", "footer"]) is not None:
        return True
    for parent in tag.parents:
        classes = set(parent.get("class", []))
        if classes & SKIP_BLOCK_ANCESTOR_CLASSES:
            return True
    return False


def block_to_text(tag: Any) -> str:
    if tag.name in {"ul", "ol"}:
        items = []
        for item in tag.find_all("li", recursive=False):
            item_text = normalize_whitespace(item.get_text(" ", strip=True))
            if item_text:
                items.append(f"- {item_text}")
        return "\n".join(items)
    return normalize_whitespace(tag.get_text(" ", strip=True))


def build_section_entry(
    *,
    page_url: str,
    page_title: str,
    question: str,
    nodes: list[Any],
) -> dict[str, Any] | None:
    text_blocks: list[str] = []
    links: list[str] = []
    for node in nodes:
        text = block_to_text(node)
        if text:
            text_blocks.append(text)
        links.extend(extract_links(node))

    response = normalize_whitespace("\n".join(text_blocks))
    return build_entry(
        url=page_url,
        categorie=page_title,
        question=question,
        response=response,
        links=unique_preserve_order(links),
    )


def collect_particulier_section_entries(
    main_article: Any,
    *,
    page_url: str,
    page_title: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    current_question = page_title
    current_nodes: list[Any] = []

    # On découpe le texte en sections à partir des h2 pour produire des chunks
    # plus faciles à indexer côté RAG qu'une page entière monolithique.
    for tag in main_article.find_all(["h2", "h3", "p", "ul", "ol"], recursive=True):
        if should_skip_particulier_block(tag):
            continue
        if tag.name == "p" and tag.find_parent("li") is not None:
            continue
        if tag.name in {"ul", "ol"} and tag.find_parent(["ul", "ol"]) is not None:
            continue

        if tag.name == "h2":
            entry = build_section_entry(
                page_url=page_url,
                page_title=page_title,
                question=current_question,
                nodes=current_nodes,
            )
            if entry is not None:
                entries.append(entry)
            current_question = normalize_whitespace(tag.get_text(" ", strip=True)) or page_title
            current_nodes = []
            continue

        current_nodes.append(tag)

    entry = build_section_entry(
        page_url=page_url,
        page_title=page_title,
        question=current_question,
        nodes=current_nodes,
    )
    if entry is not None:
        entries.append(entry)

    return entries


def collect_particulier_accordion_entries(
    main_article: Any,
    *,
    page_url: str,
    page_title: str,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []

    for question_block in main_article.select(".bloc-question"):
        question_node = question_block.select_one(".question")
        button = question_block.select_one("button[data-target]")
        if question_node is None or button is None:
            continue

        question = normalize_whitespace(question_node.get_text(" ", strip=True))
        target_id = button.get("data-target", "").lstrip("#")
        if not target_id:
            continue
        response_node = main_article.select_one(f'[id="{target_id}"]')
        response = clean_fragment_text(response_node)
        if not response:
            continue

        previous_heading = question_block.find_previous("h2")
        section_title = (
            normalize_whitespace(previous_heading.get_text(" ", strip=True))
            if previous_heading is not None
            else ""
        )
        category = page_title if not section_title or section_title == page_title else f"{page_title} | {section_title}"

        entry = build_entry(
            url=page_url,
            categorie=category,
            question=question,
            response=response,
            links=extract_links(response_node),
        )
        if entry is not None:
            entries.append(entry)

    return entries


def scrape_particulier_page(
    page: Any,
    url: str,
    *,
    min_delay: float,
    max_delay: float,
    retries: int,
) -> list[dict[str, Any]]:
    current_url = goto_with_retries(
        page,
        url,
        min_delay=min_delay,
        max_delay=max_delay,
        retries=retries,
    )
    expand_accordions(page)
    soup = BeautifulSoup(page.content(), "html.parser")

    main_article = soup.select_one("main article")
    if main_article is None:
        raise RuntimeError("Aucun article principal détecté sur la page Particulier")

    page_title_node = main_article.select_one("h1") or soup.select_one("main h1")
    page_title = clean_fragment_text(page_title_node) or "Particulier"

    entries = collect_particulier_section_entries(
        main_article,
        page_url=current_url,
        page_title=page_title,
    )
    entries.extend(
        collect_particulier_accordion_entries(
            main_article,
            page_url=current_url,
            page_title=page_title,
        )
    )

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for entry in entries:
        key = (entry["categorie"], entry["question"], entry["reponse"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for entry in entries:
        key = (
            entry["url"],
            entry["categorie"],
            entry["question"],
            entry["reponse"],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    ensure_dependencies()

    output_path = Path(args.output)
    all_entries: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        context = browser.new_context(
            user_agent=DEFAULT_USER_AGENT,
            locale="fr-FR",
            viewport={"width": 1440, "height": 2200},
            extra_http_headers=HTTP_HEADERS,
        )
        page = context.new_page()
        page.set_default_timeout(args.timeout_ms)

        try:
            faq_category_urls = discover_faq_category_urls(
                page,
                min_delay=args.min_delay,
                max_delay=args.max_delay,
                retries=args.retries,
            )
            print(f"[info] {len(faq_category_urls)} catégories FAQ trouvées")
            for category_url in faq_category_urls:
                try:
                    category_entries = scrape_faq_category(
                        page,
                        category_url,
                        min_delay=args.min_delay,
                        max_delay=args.max_delay,
                        retries=args.retries,
                    )
                    all_entries.extend(category_entries)
                    print(f"[info] FAQ {category_url} -> {len(category_entries)} entrées")
                except Exception as exc:
                    print(f"[warn] Catégorie FAQ ignorée {category_url}: {exc}", file=sys.stderr)

            particulier_urls = discover_particulier_urls(
                page,
                min_delay=args.min_delay,
                max_delay=args.max_delay,
                retries=args.retries,
            )
            print(f"[info] {len(particulier_urls)} pages Particulier trouvées")
            for particulier_url in particulier_urls:
                try:
                    page_entries = scrape_particulier_page(
                        page,
                        particulier_url,
                        min_delay=args.min_delay,
                        max_delay=args.max_delay,
                        retries=args.retries,
                    )
                    all_entries.extend(page_entries)
                    print(f"[info] Particulier {particulier_url} -> {len(page_entries)} entrées")
                except Exception as exc:
                    print(f"[warn] Page Particulier ignorée {particulier_url}: {exc}", file=sys.stderr)
        finally:
            context.close()
            browser.close()

    all_entries = dedupe_entries(all_entries)
    output_path.write_text(
        json.dumps(all_entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[done] {len(all_entries)} entrées écrites dans {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())