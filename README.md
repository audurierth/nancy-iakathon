# iakathon

## Scraper ANTAI

Le script `scrape_antai.py` extrait la FAQ de l'ANTAI et les pages du parcours Particulier, puis génère `antai_knowledge_base.json` au format attendu pour un usage RAG.

Installation :

```bash
python3 -m pip install playwright beautifulsoup4
python3 -m playwright install chromium
```

Exécution :

```bash
python3 scrape_antai.py
python3 scrape_antai.py --headed --output antai_knowledge_base.json
```

Le mode `--headed` est utile si le site filtre plus agressivement le mode headless.

## Préparation RAG

Le script `prepare_rag_corpus.py` transforme `antai_knowledge_base.json` en un corpus JSONL chunké, plus simple à indexer dans un pipeline RAG.

```bash
python3 prepare_rag_corpus.py
python3 prepare_rag_corpus.py --input antai_knowledge_base.json --output antai_rag_corpus.jsonl
```

Pour un export minimal orienté base vectorielle, avec un champ `text` et un bloc `metadata` :

```bash
python3 prepare_rag_corpus.py --profile vector-db
python3 prepare_rag_corpus.py --profile vector-db --output antai_vector_store.jsonl
```

Pour un export Markdown structure, pratique si tu veux donner directement un corpus `.md` a un pipeline RAG :

```bash
python3 prepare_rag_corpus.py --profile markdown
python3 prepare_rag_corpus.py --profile markdown --output antai_rag_corpus.md
```