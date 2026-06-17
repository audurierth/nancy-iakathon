# Simplifia: projet de l'IAkathon de Meurthe-et-Moselle, réalisé en moins de 8 heures.
Projet gagnant de l'IAkathon réalisé de 10h à 18h. Le hackathon a été organisé par le département de la Meurthe-et-Moselle et consistait à transformer la relation entre une administration et ses usagers (administrés, citoyens), sans dégrader la confiance, l’accessibilité, l’égalité de traitement et le rôle de l’humain.

Pour cela, nous avons fait le pari de partir sur un projet qui permettrait de simplifier la lecture de documents administratifs en vue des incompréhensions persistantes face à des lettres et mails juridiquement verbeux. Ce projet utilise de l'OCR pour la reconnaissance du texte, utilise un système de RAG pour former des réponses pertinentes avec un modèle de langage. Les données injectées dans le RAG proviennent de site gouvernementaux et de leurs instances (CAF, Ameli...). Le but est d'offrir une simplification de document par IA, tout en conservant la confidentialité et la véracité.

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
