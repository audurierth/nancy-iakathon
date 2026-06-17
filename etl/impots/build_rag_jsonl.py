#!/usr/bin/env python3
"""Convertit la base JSON impots en JSONL chunké pour ingestion RAG."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from typing import Any


DEFAULT_INPUT = "impots_knowledge_base.json"
DEFAULT_OUTPUT = "impots_knowledge_base_rag.jsonl"
DEFAULT_CHUNK_SIZE = 1200


def clean_text(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = value.replace("\xa0", " ")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\s*\n\s*", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def stable_document_id(record: dict[str, Any]) -> str:
    fingerprint = "\u241f".join(
        [
            str(record.get("source", "")),
            str(record.get("url", "")),
            str(record.get("type_document", "")),
            str(record.get("titre_ou_question", "")),
        ]
    )
    return hashlib.blake2b(fingerprint.encode("utf-8"), digest_size=8).hexdigest()


def derive_source_type(type_document: str) -> str:
    lowered = (type_document or "").strip().lower()
    if "faq" in lowered:
        return "faq"
    if "pdf" in lowered:
        return "guide_pdf"
    return re.sub(r"\s+", "_", lowered)


def derive_themes(category: str) -> list[str]:
    parts = [clean_text(part) for part in re.split(r"\s*\|\s*", category or "") if clean_text(part)]
    return parts or ([clean_text(category)] if clean_text(category) else [])


def normalize_delay_mentions(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        candidates = raw_value
    else:
        candidates = str(raw_value).split(" | ")
    return ordered_unique([clean_text(candidate) for candidate in candidates if clean_text(str(candidate))])


def normalize_links(raw_value: Any) -> list[str]:
    if raw_value is None:
        return []
    if isinstance(raw_value, list):
        candidates = raw_value
    else:
        candidates = [raw_value]
    return ordered_unique([clean_text(str(candidate)) for candidate in candidates if clean_text(str(candidate))])


def split_sentences(text: str) -> list[str]:
    text = clean_text(text)
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [clean_text(part) for part in parts if clean_text(part)]


def split_oversized_unit(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]

    sentence_parts = split_sentences(text)
    if len(sentence_parts) > 1:
        chunks: list[str] = []
        current = ""
        for sentence in sentence_parts:
            candidate = sentence if not current else f"{current} {sentence}"
            if len(candidate) <= max_chars:
                current = candidate
                continue
            if current:
                chunks.append(current)
            if len(sentence) <= max_chars:
                current = sentence
                continue
            word_chunks = split_by_words(sentence, max_chars)
            chunks.extend(word_chunks[:-1])
            current = word_chunks[-1]
        if current:
            chunks.append(current)
        return chunks

    return split_by_words(text, max_chars)


def split_by_words(text: str, max_chars: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        chunks.append(current)
        current = word
    if current:
        chunks.append(current)
    return chunks


def build_body_chunks(content: str, max_chars: int) -> list[str]:
    paragraphs = [clean_text(paragraph) for paragraph in content.split("\n") if clean_text(paragraph)]
    units: list[str] = []
    for paragraph in paragraphs:
        units.extend(split_oversized_unit(paragraph, max_chars))

    if not units:
        return []

    chunks: list[str] = []
    current = units[0]
    for unit in units[1:]:
        candidate = f"{current}\n{unit}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        chunks.append(current)
        current = unit
    if current:
        chunks.append(current)
    return chunks


def build_chunked_rows(record: dict[str, Any], *, chunk_size: int) -> list[dict[str, Any]]:
    question = clean_text(str(record.get("titre_ou_question", "")))
    content = clean_text(str(record.get("contenu", "")))
    if not question or not content:
        return []

    prefix = f"Question : {question}\n"
    body_budget = max(250, chunk_size - len(prefix))
    body_chunks = build_body_chunks(content, body_budget)
    if not body_chunks:
        body_chunks = [content]

    document_id = stable_document_id(record)
    delay_mentions = normalize_delay_mentions(record.get("delais_mentionnes"))
    links = normalize_links(record.get("liens_demarches"))
    source_type = derive_source_type(str(record.get("type_document", "")))
    category = clean_text(str(record.get("categorie", "")))
    themes = derive_themes(category)

    rows: list[dict[str, Any]] = []
    chunk_count = len(body_chunks)
    for index, body_chunk in enumerate(body_chunks, start=1):
        content_chunk = f"{prefix}{body_chunk}"
        indexation_lines = [
            f"Source : {clean_text(str(record.get('source', '')))}",
            f"Type : {source_type}",
            f"Catégorie : {category}",
            f"Question : {question}",
            body_chunk,
        ]
        if delay_mentions:
            indexation_lines.append(f"Délais mentionnés : {'; '.join(delay_mentions)}")
        if links:
            indexation_lines.append(f"Liens de démarche : {'; '.join(links)}")

        rows.append(
            {
                "id": f"{document_id}-{index:02d}",
                "document_id": document_id,
                "source": clean_text(str(record.get("source", ""))),
                "source_type": source_type,
                "url": clean_text(str(record.get("url", ""))),
                "categorie": category,
                "themes": themes,
                "question": question,
                "chunk_index": index,
                "chunk_count": chunk_count,
                "chunk_chars": len(content_chunk),
                "delais_mentionnes": delay_mentions,
                "liens_demarches": links,
                "contenu": content_chunk,
                "contenu_pour_indexation": "\n".join(indexation_lines),
            }
        )
    return rows


def load_records(input_path: Path) -> list[dict[str, Any]]:
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Le fichier d'entrée doit contenir un tableau JSON.")
    return payload


def write_jsonl(rows: list[dict[str, Any]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Construit un JSONL chunké pour ingestion RAG.")
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Fichier JSON source.")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Fichier JSONL de sortie.")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE, help="Taille cible maximale d'un chunk en caractères, métadonnées exclues.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    records = load_records(input_path)
    rows: list[dict[str, Any]] = []
    for record in records:
        rows.extend(build_chunked_rows(record, chunk_size=args.chunk_size))

    write_jsonl(rows, output_path)
    print(f"{len(rows)} lignes écrites dans {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())