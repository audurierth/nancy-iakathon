from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import unicodedata
from pathlib import Path


DEFAULT_DESTINATION_NAME = "mises_en_demeure_filtrees"

MAIN_TERMS = [
    ("mise en demeure de payer", re.compile(r"\bmise\s+en\s+demeure\s+de\s+payer\b")),
    ("mise en demeure", re.compile(r"\bmise\s+en\s+demeure\b")),
]

EMITTERS = [
    ("impot", re.compile(r"\bimpots?\b")),
    ("dgfip", re.compile(r"\bdgfip\b")),
    ("amende", re.compile(r"\bamendes?\b")),
    ("urssaf", re.compile(r"\burssaf\b")),
    ("cotisation", re.compile(r"\bcotisations?\b")),
    ("tresor public", re.compile(r"\btresor\s+public\b")),
]

TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", default=".")
    parser.add_argument("--destination", "-d", default=None)
    return parser.parse_args()


def resolve_destination(source_dir: Path, destination: str | None) -> Path:
    if destination is None:
        return source_dir / DEFAULT_DESTINATION_NAME
    destination_path = Path(destination)
    if destination_path.is_absolute():
        return destination_path
    return Path.cwd() / destination_path


def decode_xml_text(file_path: Path) -> str | None:
    try:
        raw_bytes = file_path.read_bytes()
    except OSError:
        return None

    for encoding in ("utf-8", "utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return None


def normalize_text(text: str) -> str:
    text = html.unescape(text)
    text = TAG_RE.sub(" ", text)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(character for character in text if not unicodedata.combining(character))
    text = text.casefold()
    return WHITESPACE_RE.sub(" ", text).strip()


def find_match(normalized_text: str) -> tuple[str, str] | None:
    main_term = None
    emitter = None

    for label, pattern in MAIN_TERMS:
        if pattern.search(normalized_text):
            main_term = label
            break

    if main_term is None:
        return None

    for label, pattern in EMITTERS:
        if pattern.search(normalized_text):
            emitter = label
            break

    if emitter is None:
        return None

    return main_term, emitter


def unique_destination_path(destination_dir: Path, source_file: Path) -> Path:
    candidate = destination_dir / source_file.name
    if not candidate.exists():
        return candidate

    stem = source_file.stem
    suffix = source_file.suffix
    counter = 1
    while True:
        candidate = destination_dir / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def format_display_path(path: Path) -> str:
    try:
        relative_path = path.resolve().relative_to(Path.cwd().resolve())
        posix_path = relative_path.as_posix()
        return f"./{posix_path}"
    except ValueError:
        return path.resolve().as_posix()


def iter_xml_files(source_dir: Path, destination_dir: Path):
    destination_resolved = destination_dir.resolve()

    for root, dirnames, filenames in os.walk(source_dir, topdown=True):
        root_path = Path(root)

        dirnames[:] = sorted(
            directory_name
            for directory_name in dirnames
            if (root_path / directory_name).resolve() != destination_resolved
        )

        for filename in sorted(filenames):
            file_path = root_path / filename
            if file_path.suffix.lower() == ".xml":
                yield file_path


def main() -> int:
    args = parse_args()
    source_dir = Path(args.source).resolve()
    destination_dir = resolve_destination(source_dir, args.destination).resolve()

    if not source_dir.is_dir() or destination_dir == source_dir:
        return 1

    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return 1

    for file_path in iter_xml_files(source_dir, destination_dir):
        decoded_text = decode_xml_text(file_path)
        if decoded_text is None:
            continue

        match = find_match(normalize_text(decoded_text))
        if match is None:
            continue

        destination_file = unique_destination_path(destination_dir, file_path)
        try:
            shutil.copy2(file_path, destination_file)
        except OSError:
            continue

        main_term, emitter = match
        print(
            f"[SUCCESS] {format_display_path(file_path)} -> Motif : contient '{main_term}' et '{emitter}'"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())