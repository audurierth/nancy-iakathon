from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse


TITLE_NODE_NAMES = {"titre", "titreflottant", "titreriche"}
ROOT_SKIP_NAMES = {
    "title",
    "creator",
    "subject",
    "description",
    "publisher",
    "contributor",
    "date",
    "type",
    "format",
    "identifier",
    "source",
    "language",
    "relation",
    "coverage",
    "rights",
    "surtitre",
    "audience",
    "canal",
    "fildariane",
    "theme",
    "sousthemepere",
    "dossierpere",
    "rechercheguideepere",
}
NODE_SKIP_NAMES = {
    "condition",
    "estvrai",
    "source",
    "noticeliee",
    "colonne",
    "pivotlocal",
    "niveau",
}
HEADING_NODE_NAMES = {
    "chapitre",
    "souschapitre",
    "situation",
    "cas",
    "ousadresser",
    "rechercheguidee",
    "serviceenligne",
    "pourensavoirplus",
    "quipeutmaider",
    "definition",
    "abreviation",
    "reference",
}
LABEL_NODE_NAMES = {
    "asavoir": "A savoir",
    "rappel": "Rappel",
    "attention": "Attention",
    "exemple": "Exemple",
    "aide": "Aide",
}
PASSTHROUGH_NODE_NAMES = {
    "publication",
    "introduction",
    "texte",
    "bloccas",
    "listesituations",
    "voiraussi",
}
LEAF_REFERENCE_NAMES = {"fiche", "questionreponse", "commentfairedi", "commentfairesi"}
ACTION_URL_NODE_NAMES = {"serviceenligne", "lienexterne"}
DELAY_PATTERNS = [
    re.compile(
        r"\bdans\s+(?:un|les?)\s+d[ée]lai\s+de\s+\d+\s*(?:jour|jours|mois|an|ans|semaine|semaines|heure|heures)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bd[ée]lai\s+de\s+\d+\s*(?:jour|jours|mois|an|ans|semaine|semaines|heure|heures)\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b\d+\s*(?:jour|jours|mois|an|ans|semaine|semaines|heure|heures)\s+(?:calendaires|ouvr[ée]s|ouvrables|suivants?|qui\s+suivent|après|a\s+compter)\b",
        re.IGNORECASE,
    ),
]
SPACE_RE = re.compile(r"\s+")
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def parse_args() -> argparse.Namespace:
    default_source = "mises_en_demeure_filtrees" if Path("mises_en_demeure_filtrees").is_dir() else "."
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", default=default_source)
    parser.add_argument("--output", "-o", default="corpus_rag_mises_en_demeure.md")
    parser.add_argument("--format", choices=["auto", "md", "jsonl"], default="auto")
    parser.add_argument("--title", default=None)
    parser.add_argument("--max-chars", type=int, default=1400)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--focus-pattern", action="append", default=[])
    parser.add_argument("--focus-window", type=int, default=3)
    return parser.parse_args()


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def collapse_spaces(text: str) -> str:
    return SPACE_RE.sub(" ", text.replace("\xa0", " ")).strip()


def clean_text(element: ET.Element | None) -> str:
    if element is None:
        return ""
    return collapse_spaces(" ".join(element.itertext()))


def ascii_slug(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(character for character in normalized if not unicodedata.combining(character))
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.casefold()).strip("-")
    return slug or "xml"


def direct_children(element: ET.Element, name: str) -> list[ET.Element]:
    target = name.lower()
    return [child for child in element if local_name(child.tag) == target]


def first_direct_child(element: ET.Element, name: str) -> ET.Element | None:
    for child in element:
        if local_name(child.tag) == name.lower():
            return child
    return None


def extract_title(element: ET.Element) -> str:
    for child in element:
        if local_name(child.tag) in TITLE_NODE_NAMES:
            title = clean_text(child)
            if title:
                return title
    return ""


def extract_theme(root: ET.Element) -> str:
    dossier = first_direct_child(root, "DossierPere")
    if dossier is not None:
        titre = first_direct_child(dossier, "Titre")
        text = clean_text(titre)
        if text:
            return text

    sous_theme = clean_text(first_direct_child(root, "SousThemePere"))
    if sous_theme:
        return sous_theme

    for theme in direct_children(root, "Theme"):
        titre = first_direct_child(theme, "Titre")
        text = clean_text(titre)
        if text:
            return text

    subject = clean_text(first_direct_child(root, "subject"))
    if subject:
        return subject

    return "Sans theme"


def append_unique(values: list[str], value: str) -> None:
    cleaned = collapse_spaces(value)
    if cleaned and cleaned not in values:
        values.append(cleaned)


def extract_themes(root: ET.Element) -> list[str]:
    themes: list[str] = []

    for theme in direct_children(root, "Theme"):
        titre = first_direct_child(theme, "Titre")
        if titre is not None:
            append_unique(themes, clean_text(titre))

    sous_theme = first_direct_child(root, "SousThemePere")
    if sous_theme is not None:
        append_unique(themes, clean_text(sous_theme))

    dossier = first_direct_child(root, "DossierPere")
    if dossier is not None:
        titre = first_direct_child(dossier, "Titre")
        if titre is not None:
            append_unique(themes, clean_text(titre))

    if not themes:
        append_unique(themes, extract_theme(root))

    return themes


def extract_title_metadata(root: ET.Element, file_path: Path) -> str:
    title = clean_text(first_direct_child(root, "title"))
    if title:
        return title
    title = extract_title(root)
    if title:
        return title
    return file_path.stem


def extract_type(root: ET.Element) -> str:
    raw_type = clean_text(first_direct_child(root, "type")) or root.attrib.get("type", "xml")
    return ascii_slug(raw_type)


def extract_source_label(source_url: str) -> str:
    if not source_url:
        return "service-public.fr"
    host = urlparse(source_url).netloc.casefold()
    if host.startswith("www."):
        host = host[4:]
    return host or "service-public.fr"


def source_display_name(source_label: str) -> str:
    lowered = source_label.casefold()
    if "service-public" in lowered:
        return "Service Public"

    primary = source_label.split(".", 1)[0].replace("-", " ").strip()
    if not primary:
        return source_label
    if len(primary) <= 5:
        return primary.upper()
    return primary.title()


def extract_action_urls(root: ET.Element) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()

    for element in root.iter():
        if local_name(element.tag) not in ACTION_URL_NODE_NAMES:
            continue
        url = element.attrib.get("URL", "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        urls.append(url)

    return urls


def extract_deadlines(text: str) -> list[str]:
    matches: list[tuple[int, int, str]] = []
    for pattern in DELAY_PATTERNS:
        for match in pattern.finditer(text):
            matches.append((match.start(), match.end(), collapse_spaces(match.group(0))))

    matches.sort(key=lambda item: (item[0], -(item[1] - item[0])))

    deadlines: list[str] = []
    seen: set[str] = set()
    kept_ranges: list[tuple[int, int]] = []

    for start, end, value in matches:
        if any(start >= kept_start and end <= kept_end for kept_start, kept_end in kept_ranges):
            continue
        lowered = value.casefold()
        if lowered in seen:
            continue
        seen.add(lowered)
        kept_ranges.append((start, end))
        deadlines.append(value)

    return deadlines


def render_list_lines(element: ET.Element, level: int = 0) -> list[str]:
    lines: list[str] = []

    for item in direct_children(element, "Item"):
        first_line = True
        item_lines: list[str] = []
        nested_lines: list[str] = []

        for child in item:
            child_name = local_name(child.tag)
            if child_name == "paragraphe":
                text = clean_text(child)
                if text:
                    item_lines.append(text)
            elif child_name == "liste":
                nested_lines.extend(render_list_lines(child, level + 1))
            else:
                for block in render_node(child, depth=6):
                    block_text = collapse_spaces(block.replace("\n", " "))
                    if block_text:
                        item_lines.append(block_text)

        for text in item_lines:
            prefix = "  " * level + ("- " if first_line else "  ")
            lines.append(prefix + text)
            first_line = False

        if not item_lines:
            title = extract_title(item)
            if title:
                lines.append("  " * level + "- " + title)

        lines.extend(nested_lines)

    return lines


def render_table(element: ET.Element, depth: int) -> list[str]:
    blocks: list[str] = []
    title = extract_title(element)
    if title:
        blocks.append(f"{'#' * min(depth, 6)} {title}")

    rows: list[list[str]] = []
    for row in direct_children(element, "Rangée"):
        cells: list[str] = []
        for cell in direct_children(row, "Cellule"):
            cell_text = clean_text(cell)
            if cell_text:
                cells.append(cell_text)
        if cells:
            rows.append(cells)

    rendered_rows: list[str] = []
    for row in rows:
        if len(row) == 1:
            rendered_rows.append(f"- {row[0]}")
        elif len(row) == 2:
            rendered_rows.append(f"- {row[0]} : {row[1]}")
        else:
            rendered_rows.append("- " + " | ".join(row))

    if rendered_rows:
        blocks.append("\n".join(rendered_rows))

    return blocks


def render_node(element: ET.Element, depth: int = 4) -> list[str]:
    name = local_name(element.tag)

    if name in NODE_SKIP_NAMES or name in TITLE_NODE_NAMES:
        return []

    if name == "paragraphe":
        text = clean_text(element)
        return [text] if text else []

    if name == "liste":
        lines = render_list_lines(element)
        return ["\n".join(lines)] if lines else []

    if name == "tableau":
        return render_table(element, depth)

    if name in LEAF_REFERENCE_NAMES:
        title = extract_title(element)
        return [f"- {title}"] if title else []

    blocks: list[str] = []
    next_depth = depth
    title = extract_title(element)

    if name in LABEL_NODE_NAMES:
        heading = LABEL_NODE_NAMES[name]
        if title and ascii_slug(title) != ascii_slug(heading):
            heading = f"{heading} - {title}"
        blocks.append(f"{'#' * min(depth, 6)} {heading}")
        next_depth = min(depth + 1, 6)
    elif name in HEADING_NODE_NAMES and title:
        blocks.append(f"{'#' * min(depth, 6)} {title}")
        next_depth = min(depth + 1, 6)
    elif name not in PASSTHROUGH_NODE_NAMES and title:
        blocks.append(f"{'#' * min(depth, 6)} {title}")
        next_depth = min(depth + 1, 6)

    if name == "reference":
        complement = clean_text(first_direct_child(element, "Complement"))
        if complement:
            blocks.append(complement)

    for child in element:
        child_name = local_name(child.tag)
        if child_name in TITLE_NODE_NAMES:
            continue
        if child_name in ROOT_SKIP_NAMES or child_name in NODE_SKIP_NAMES:
            continue
        if name == "reference" and child_name == "complement":
            continue
        blocks.extend(render_node(child, depth=next_depth))

    return blocks


def render_document_blocks(root: ET.Element) -> list[str]:
    blocks: list[str] = []

    for child in root:
        name = local_name(child.tag)
        if name in ROOT_SKIP_NAMES:
            continue
        blocks.extend(render_node(child, depth=4))

    cleaned: list[str] = []
    for block in blocks:
        stripped = block.strip()
        if stripped:
            cleaned.append(stripped)

    return cleaned


def filter_blocks_by_focus(blocks: list[str], patterns: list[re.Pattern[str]], window: int) -> list[str]:
    if not patterns:
        return blocks

    matched_indexes: set[int] = set()
    for index, block in enumerate(blocks):
        if any(pattern.search(block) for pattern in patterns):
            start = max(0, index - window)
            end = min(len(blocks), index + window + 1)
            matched_indexes.update(range(start, end))

    if not matched_indexes:
        return blocks

    return [blocks[index] for index in sorted(matched_indexes)]


def merge_heading_blocks(blocks: list[str]) -> list[str]:
    merged: list[str] = []
    index = 0

    while index < len(blocks):
        block = blocks[index]
        if block.startswith("#") and index + 1 < len(blocks):
            merged.append(block + "\n\n" + blocks[index + 1])
            index += 2
            continue
        merged.append(block)
        index += 1

    return merged


def split_long_line(line: str, max_chars: int) -> list[str]:
    if len(line) <= max_chars:
        return [line]

    sentences = [segment.strip() for segment in SENTENCE_RE.split(line) if segment.strip()]
    if len(sentences) <= 1:
        words = line.split()
        parts: list[str] = []
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if current and len(candidate) > max_chars:
                parts.append(current)
                current = word
            else:
                current = candidate
        if current:
            parts.append(current)
        return parts

    parts = []
    current = ""
    for sentence in sentences:
        candidate = sentence if not current else f"{current} {sentence}"
        if current and len(candidate) > max_chars:
            parts.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def split_block(block: str, max_chars: int) -> list[str]:
    if len(block) <= max_chars:
        return [block]

    lines = [line.rstrip() for line in block.splitlines() if line.strip()]
    persistent_headings = [line for line in lines if line.startswith("#")]
    content_lines = [line for line in lines if not line.startswith("#")]

    if not content_lines:
        return split_long_line(block, max_chars)

    segments: list[str] = []
    current_lines: list[str] = persistent_headings.copy()

    def current_length(items: list[str]) -> int:
        return len("\n".join(items))

    for content_line in content_lines:
        for piece in split_long_line(content_line, max_chars):
            candidate_lines = current_lines + [piece]
            if current_lines != persistent_headings and current_length(candidate_lines) > max_chars:
                segments.append("\n".join(current_lines).strip())
                current_lines = persistent_headings.copy() + [piece]
            else:
                current_lines = candidate_lines

    if current_lines:
        segments.append("\n".join(current_lines).strip())

    return [segment for segment in segments if segment]


def chunk_markdown(text: str, max_chars: int) -> list[str]:
    raw_blocks = [block.strip() for block in re.split(r"\n{2,}", text) if block.strip()]
    merged_blocks = merge_heading_blocks(raw_blocks)

    segments: list[str] = []
    for block in merged_blocks:
        segments.extend(split_block(block, max_chars))

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0

    for segment in segments:
        segment_length = len(segment)
        separator_length = 2 if current else 0
        if current and current_length + separator_length + segment_length > max_chars:
            chunks.append("\n\n".join(current))
            current = [segment]
            current_length = segment_length
        else:
            current.append(segment)
            current_length += separator_length + segment_length

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def build_document_id(file_path: Path, publication_id: str) -> str:
    digest = hashlib.sha1(f"{publication_id}:{file_path.as_posix()}".encode("utf-8")).hexdigest()
    return digest[:16]


def display_path(file_path: Path) -> str:
    try:
        return file_path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return file_path.resolve().as_posix()


def question_like(source_type: str, title: str) -> bool:
    return source_type in {"question-reponse", "faq"} or title.endswith("?")


def normalize_chunk_text(chunk: str) -> str:
    cleaned_lines: list[str] = []

    for raw_line in chunk.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue

        line = re.sub(r"^#+\s*", "", line)
        stripped = line.lstrip()
        if stripped.startswith("- "):
            normalized_line = "- " + collapse_spaces(stripped[2:])
        else:
            normalized_line = collapse_spaces(stripped)

        is_continuation = raw_line.startswith("  ") and not stripped.startswith("- ")
        if is_continuation and cleaned_lines and cleaned_lines[-1] != "":
            cleaned_lines[-1] = cleaned_lines[-1] + " " + normalized_line
        else:
            cleaned_lines.append(normalized_line)

    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()

    return "\n".join(cleaned_lines)


def build_chunk_content(title: str, source_type: str, chunk: str) -> str:
    label = "Question" if question_like(source_type, title) else "Titre"
    body = normalize_chunk_text(chunk)
    if body:
        return f"{label} : {title}\n{body}"
    return f"{label} : {title}"


def build_indexable_content(
    source_display: str,
    source_type: str,
    categorie: str,
    title: str,
    chunk: str,
    deadlines: list[str],
    links: list[str],
) -> str:
    label = "Question" if question_like(source_type, title) else "Titre"
    parts = [
        f"Source : {source_display}",
        f"Type : {source_type}",
        f"Catégorie : {categorie}",
        f"{label} : {title}",
    ]

    body = normalize_chunk_text(chunk)
    if body:
        parts.append(body)
    if deadlines:
        parts.append(f"Délais mentionnés : {'; '.join(deadlines)}")
    if links:
        parts.append(f"Liens de démarche : {'; '.join(links)}")

    return "\n".join(parts)


def output_format_for_path(requested_format: str, output_path: Path) -> str:
    if requested_format != "auto":
        return requested_format
    if output_path.suffix.casefold() == ".jsonl":
        return "jsonl"
    return "md"


def iter_xml_files(source_path: Path, limit: int | None):
    if source_path.is_file() and source_path.suffix.lower() == ".xml":
        yield source_path
        return

    count = 0
    for file_path in sorted(source_path.rglob("*.xml")):
        yield file_path
        count += 1
        if limit is not None and count >= limit:
            break


def convert_file(
    file_path: Path,
    max_chars: int,
    focus_patterns: list[re.Pattern[str]],
    focus_window: int,
) -> tuple[dict[str, object], list[str]] | None:
    try:
        root = ET.parse(file_path).getroot()
    except (ET.ParseError, OSError):
        return None

    publication_id = root.attrib.get("ID", file_path.stem)
    source_url = root.attrib.get("spUrl", "")
    title = extract_title_metadata(root, file_path)
    theme = extract_theme(root)
    themes = extract_themes(root)
    source_type = extract_type(root)
    source_label = extract_source_label(source_url)
    source_display = source_display_name(source_label)
    action_urls = extract_action_urls(root)
    content_blocks = render_document_blocks(root)
    content_blocks = filter_blocks_by_focus(content_blocks, focus_patterns, focus_window)
    content = "\n\n".join(content_blocks)
    if not content:
        return None

    deadlines = extract_deadlines(content)
    document_id = build_document_id(file_path, publication_id)
    metadata = {
        "document_id": document_id,
        "publication_id": publication_id,
        "title": title,
        "theme": theme,
        "themes": themes,
        "source_label": source_label,
        "source_display": source_display,
        "source_type": source_type,
        "source_url": source_url,
        "source_path": display_path(file_path),
        "links": action_urls,
        "deadlines": deadlines,
    }
    chunks = chunk_markdown(content, max_chars=max_chars)
    if not chunks:
        return None

    return metadata, chunks


def render_corpus(title: str, documents: list[tuple[dict[str, object], list[str]]]) -> str:
    total_chunks = sum(len(chunks) for _, chunks in documents)
    width = max(2, len(str(max(total_chunks, 1))))
    parts = [
        f"# {title}",
        "",
        f"Nombre de chunks : {total_chunks}",
        "",
        "Chaque section ci-dessous correspond a un chunk pret a etre indexe ou decoupe par un moteur RAG.",
        "",
        "---",
        "",
    ]

    for metadata, chunks in documents:
        links = metadata["links"]
        deadlines = metadata["deadlines"]
        total_for_document = len(chunks)
        for index, chunk in enumerate(chunks, start=1):
            chunk_id = f"{metadata['document_id']}-{index:0{width}d}"
            parts.extend(
                [
                    f"<!-- id: {chunk_id} | document_id: {metadata['document_id']} | chunk: {index}/{total_for_document} | source_type: {metadata['source_type']} -->",
                    "",
                    f"## {metadata['theme']}",
                    "",
                    f"### {metadata['title']}",
                    "",
                    f"Source : {metadata['source_label']}",
                    f"Type : {metadata['source_type']}",
                    f"URL : {metadata['source_url'] or 'N/A'}",
                    f"Fichier source : {metadata['source_path']}",
                    f"Chunk : {index}/{total_for_document}",
                    f"Taille : {len(chunk)} caracteres",
                    f"Themes : {'; '.join(metadata['themes'])}",
                    f"Delais mentionnes : {'; '.join(deadlines) if deadlines else 'Aucun'}",
                    "",
                    "Liens de demarche :",
                    "\n".join(f"- {url}" for url in links) or "- Aucun",
                    "",
                    chunk,
                    "",
                    "---",
                    "",
                ]
            )

    return "\n".join(parts).rstrip() + "\n"


def render_jsonl(documents: list[tuple[dict[str, object], list[str]]]) -> str:
    lines: list[str] = []

    for metadata, chunks in documents:
        total_for_document = len(chunks)
        width = max(2, len(str(total_for_document)))
        categorie = " | ".join(metadata["themes"])

        for index, chunk in enumerate(chunks, start=1):
            chunk_id = f"{metadata['document_id']}-{index:0{width}d}"
            contenu = build_chunk_content(str(metadata["title"]), str(metadata["source_type"]), chunk)
            record = {
                "id": chunk_id,
                "document_id": metadata["document_id"],
                "source": metadata["source_label"],
                "source_type": metadata["source_type"],
                "url": metadata["source_url"],
                "categorie": categorie,
                "themes": metadata["themes"],
                "question": metadata["title"],
                "chunk_index": index,
                "chunk_count": total_for_document,
                "chunk_chars": len(contenu),
                "delais_mentionnes": metadata["deadlines"],
                "liens_demarches": metadata["links"],
                "contenu": contenu,
                "contenu_pour_indexation": build_indexable_content(
                    str(metadata["source_display"]),
                    str(metadata["source_type"]),
                    categorie,
                    str(metadata["title"]),
                    chunk,
                    list(metadata["deadlines"]),
                    list(metadata["links"]),
                ),
            }
            lines.append(json.dumps(record, ensure_ascii=False))

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    source_path = Path(args.source).resolve()
    output_path = Path(args.output).resolve()
    output_format = output_format_for_path(args.format, output_path)
    focus_patterns = [re.compile(pattern, re.IGNORECASE) for pattern in args.focus_pattern]

    if not source_path.exists():
        return 1

    documents: list[tuple[dict[str, object], list[str]]] = []
    for file_path in iter_xml_files(source_path, limit=args.limit):
        converted = convert_file(
            file_path,
            max_chars=args.max_chars,
            focus_patterns=focus_patterns,
            focus_window=args.focus_window,
        )
        if converted is None:
            continue
        documents.append(converted)

    if not documents:
        return 1

    source_name = source_path.stem if source_path.is_file() else source_path.name
    corpus_title = args.title or f"Corpus RAG {source_name.replace('_', ' ')}"
    if output_format == "jsonl":
        corpus_text = render_jsonl(documents)
    else:
        corpus_text = render_corpus(corpus_title, documents)

    try:
        output_path.write_text(corpus_text, encoding="utf-8")
    except OSError:
        return 1

    print(f"Corpus ecrit : {output_path.as_posix()}")
    print(f"Documents convertis : {len(documents)}")
    print(f"Nombre de chunks : {sum(len(chunks) for _, chunks in documents)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())