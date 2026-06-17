#!/usr/bin/env python3
"""
Transforme la base brute ANTAI en corpus chunké JSONL pour l'indexation RAG.

Exécution:
    python3 prepare_rag_corpus.py
    python3 prepare_rag_corpus.py --input antai_knowledge_base.json --output antai_rag_corpus.jsonl
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

DEFAULT_INPUT = "antai_knowledge_base.json"
DEFAULT_OUTPUT_RICH = "antai_rag_corpus.jsonl"
DEFAULT_OUTPUT_VECTOR = "antai_vector_store.jsonl"
DEFAULT_OUTPUT_MARKDOWN = "antai_rag_corpus.md"
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+(?=[0-9A-ZÀÂÄÇÉÈÊËÎÏÔÖÙÛÜ])")
CATEGORY_SPLIT_PATTERN = re.compile(r"\s*\|\s*|\s*\n+\s*")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prépare un corpus JSONL optimisé pour un pipeline RAG à partir de la base ANTAI brute."
    )
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Fichier JSON source.")
    parser.add_argument(
        "--profile",
        choices=["rich", "vector-db", "markdown"],
        default="rich",
        help="Format de sortie: riche pour audit/indexation, minimal orienté base vectorielle, ou Markdown structuré pour ingestion RAG.",
    )
    parser.add_argument("--output", default=None, help="Fichier JSONL de sortie.")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=1200,
        help="Taille cible maximale d'un chunk en caractères.",
    )
    return parser


def normalize_whitespace(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u00ad", "")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value and value not in seen:
            seen.add(value)
            ordered.append(value)
    return ordered


def normalize_category_label(text: str) -> str:
    parts = [
        normalize_whitespace(part)
        for part in CATEGORY_SPLIT_PATTERN.split(text)
        if normalize_whitespace(part)
    ]
    return " | ".join(unique_preserve_order(parts))


def infer_source_type(url: str) -> str:
    return "faq" if "/faq" in url else "particulier"


def split_long_text(text: str, max_chars: int) -> list[str]:
    text = normalize_whitespace(text)
    if len(text) <= max_chars:
        return [text]

    sentences = [segment.strip() for segment in SENTENCE_SPLIT_PATTERN.split(text) if segment.strip()]
    if len(sentences) <= 1:
        words = text.split()
        chunks: list[str] = []
        current: list[str] = []
        current_length = 0
        for word in words:
            extra = len(word) + (1 if current else 0)
            if current and current_length + extra > max_chars:
                chunks.append(" ".join(current))
                current = [word]
                current_length = len(word)
            else:
                current.append(word)
                current_length += extra
        if current:
            chunks.append(" ".join(current))
        return chunks

    chunks = []
    current: list[str] = []
    current_length = 0
    for sentence in sentences:
        extra = len(sentence) + (1 if current else 0)
        if current and current_length + extra > max_chars:
            chunks.append(" ".join(current))
            current = [sentence]
            current_length = len(sentence)
        else:
            current.append(sentence)
            current_length += extra
    if current:
        chunks.append(" ".join(current))
    return chunks


def chunk_response(question: str, response: str, max_chars: int) -> list[str]:
    prefix = f"Question : {question}\n"
    budget = max(300, max_chars - len(prefix))
    paragraphs = [normalize_whitespace(part) for part in response.split("\n") if normalize_whitespace(part)]

    units: list[str] = []
    for paragraph in paragraphs:
        units.extend(split_long_text(paragraph, budget))

    chunks: list[str] = []
    current: list[str] = []
    current_length = 0
    for unit in units:
        extra = len(unit) + (1 if current else 0)
        if current and current_length + extra > budget:
            chunks.append(prefix + "\n".join(current))
            current = [unit]
            current_length = len(unit)
        else:
            current.append(unit)
            current_length += extra

    if current:
        chunks.append(prefix + "\n".join(current))

    return chunks or [prefix + response]


def build_document_id(entry: dict[str, Any]) -> str:
    payload = "||".join(
        [
            entry.get("url", ""),
            normalize_category_label(entry.get("categorie", "")),
            normalize_whitespace(entry.get("question", "")),
        ]
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]


def build_indexation_text(
    *,
    source_type: str,
    categorie: str,
    question: str,
    chunk_text: str,
    delays: list[str],
    links: list[str],
) -> str:
    parts = [
        "Source : ANTAI",
        f"Type : {source_type}",
        f"Catégorie : {categorie}",
        chunk_text,
    ]
    if delays:
        parts.append(f"Délais mentionnés : {'; '.join(delays)}")
    if links:
        parts.append(f"Liens de démarche : {' ; '.join(links)}")
    return "\n".join(parts)


def build_vector_text(
    *,
    categorie: str,
    question: str,
    chunk_text: str,
    delays: list[str],
) -> str:
    parts = [
        f"Catégorie : {categorie}",
        chunk_text,
    ]
    if delays:
        parts.append(f"Délais mentionnés : {'; '.join(delays)}")
    return "\n".join(parts)


def build_rag_records(entries: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for entry in entries:
        categorie = normalize_category_label(entry.get("categorie", ""))
        question = normalize_whitespace(entry.get("question", ""))
        response = normalize_whitespace(entry.get("reponse", ""))
        if not categorie or not question or not response:
            continue

        source_type = infer_source_type(entry.get("url", ""))
        themes = [part for part in categorie.split(" | ") if part]
        delays = [normalize_whitespace(part) for part in str(entry.get("delais_mentionnes") or "").split(";") if normalize_whitespace(part)]
        links = unique_preserve_order([normalize_whitespace(link) for link in entry.get("liens_demarches", []) if normalize_whitespace(link)])
        document_id = build_document_id(entry)
        chunks = chunk_response(question, response, max_chars)

        for index, chunk_text in enumerate(chunks, start=1):
            chunk_id = f"{document_id}-{index:02d}"
            records.append(
                {
                    "id": chunk_id,
                    "document_id": document_id,
                    "source": entry.get("source", "antai.gouv.fr"),
                    "source_type": source_type,
                    "url": entry.get("url", ""),
                    "categorie": categorie,
                    "themes": themes,
                    "question": question,
                    "chunk_index": index,
                    "chunk_count": len(chunks),
                    "chunk_chars": len(chunk_text),
                    "delais_mentionnes": delays,
                    "liens_demarches": links,
                    "contenu": chunk_text,
                    "contenu_pour_indexation": build_indexation_text(
                        source_type=source_type,
                        categorie=categorie,
                        question=question,
                        chunk_text=chunk_text,
                        delays=delays,
                        links=links,
                    ),
                }
            )
    return records


def build_vector_records(entries: list[dict[str, Any]], max_chars: int) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    rich_records = build_rag_records(entries, max_chars=max_chars)

    for record in rich_records:
        metadata = {
            "source": record["source"],
            "source_type": record["source_type"],
            "url": record["url"],
            "categorie": record["categorie"],
            "themes": record["themes"],
            "question": record["question"],
            "chunk_index": record["chunk_index"],
            "chunk_count": record["chunk_count"],
            "chunk_chars": record["chunk_chars"],
            "delais_mentionnes": record["delais_mentionnes"],
            "liens_demarches": record["liens_demarches"],
        }
        records.append(
            {
                "id": record["id"],
                "document_id": record["document_id"],
                "text": build_vector_text(
                    categorie=record["categorie"],
                    question=record["question"],
                    chunk_text=record["contenu"],
                    delays=record["delais_mentionnes"],
                ),
                "metadata": metadata,
            }
        )

    return records


def strip_question_prefix(chunk_text: str, question: str) -> str:
    prefix = f"Question : {question}\n"
    if chunk_text.startswith(prefix):
        return chunk_text[len(prefix) :].strip()
    return chunk_text.strip()


def build_markdown_document(entries: list[dict[str, Any]], max_chars: int) -> str:
    records = build_rag_records(entries, max_chars=max_chars)
    lines = [
        "# Corpus RAG ANTAI",
        "",
        f"Nombre de chunks : {len(records)}",
        "",
        "Chaque section ci-dessous correspond a un chunk pret a etre indexe ou decoupe par un moteur RAG.",
    ]

    for record in records:
        lines.extend(
            [
                "",
                "---",
                "",
                (
                    f"<!-- id: {record['id']} | document_id: {record['document_id']} "
                    f"| chunk: {record['chunk_index']}/{record['chunk_count']} "
                    f"| source_type: {record['source_type']} -->"
                ),
                "",
                f"## {record['categorie']}",
                "",
                f"### {record['question']}",
                "",
                f"Source : {record['source']}",
                f"Type : {record['source_type']}",
                f"URL : {record['url']}",
                f"Chunk : {record['chunk_index']}/{record['chunk_count']}",
                f"Taille : {record['chunk_chars']} caracteres",
            ]
        )

        if record["themes"]:
            lines.append(f"Themes : {', '.join(record['themes'])}")
        if record["delais_mentionnes"]:
            lines.append(f"Delais mentionnes : {'; '.join(record['delais_mentionnes'])}")
        if record["liens_demarches"]:
            lines.extend(["", "Liens de demarche :"])
            lines.extend(f"- {link}" for link in record["liens_demarches"])

        lines.extend(
            [
                "",
                strip_question_prefix(record["contenu"], record["question"]),
            ]
        )

    return "\n".join(lines).strip() + "\n"


def resolve_output_path(profile: str, output: str | None) -> Path:
    if output:
        return Path(output)
    if profile == "markdown":
        return Path(DEFAULT_OUTPUT_MARKDOWN)
    if profile == "vector-db":
        return Path(DEFAULT_OUTPUT_VECTOR)
    return Path(DEFAULT_OUTPUT_RICH)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = resolve_output_path(args.profile, args.output)

    entries = json.loads(input_path.read_text(encoding="utf-8"))
    if args.profile == "markdown":
        output_path.write_text(
            build_markdown_document(entries, max_chars=args.max_chars),
            encoding="utf-8",
        )
        print(f"[done] Markdown ecrit dans {output_path}")
        return 0
    if args.profile == "vector-db":
        records = build_vector_records(entries, max_chars=args.max_chars)
    else:
        records = build_rag_records(entries, max_chars=args.max_chars)

    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"[done] {len(records)} chunks écrits dans {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())