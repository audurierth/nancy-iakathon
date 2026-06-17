import os
import re
import json
import math
import logging
from typing import List, Optional, Dict, Any
from fastapi import FastAPI, HTTPException, Body, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import requests

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CivicAssistBackend")

app = FastAPI(
    title="CivicAssist.IA API",
    description="RAG Search Portal & PWA for French Public Services (ANTAI, Impôts, Service-Public)",
    version="1.0.0",
    docs_url="/docs"
)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths to datasets
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_PATHS = {
    "antai": os.path.join(BASE_DIR, "data", "antai", "antai_rag_corpus.jsonl"),
    "impots": os.path.join(BASE_DIR, "data", "impots", "impots_knowledge_base_rag.jsonl"),
    "service-public": os.path.join(BASE_DIR, "data", "service-public", "corpus_rag_mises_en_demeure.jsonl")
}
IMAGE_ANALYSIS_UPSTREAM_URL = os.environ.get(
    "IMAGE_ANALYSIS_UPSTREAM_URL",
    "https://uncompromisingly-unpromiscuous-dede.ngrok-free.dev/image"
)

# Global in-memory document store
documents: List[Dict[str, Any]] = []
# Global in-memory TF-IDF index fields
vocab: Dict[str, int] = {}
idf: Dict[str, float] = {}
doc_vectors: List[Dict[str, float]] = []

def tokenize(text: str) -> List[str]:
    """Tokenize and normalize text to lowercase words."""
    if not text:
        return []
    # Replace non-alphanumeric with spaces, lowercase, and split
    words = re.findall(r'\b\w\w+\b', text.lower())
    # French stop words (simple filter)
    stop_words = {
        "le", "la", "les", "de", "des", "du", "un", "une", "en", "et", "que", "qui", 
        "dans", "par", "pour", "sur", "avec", "dans", "sans", "sous", "vers", "pour"
    }
    return [w for w in words if w not in stop_words]

def build_index():
    """Build in-memory TF-IDF index across all loaded documents."""
    global vocab, idf, doc_vectors
    logger.info("Building in-memory search index...")
    
    # 1. Gather all terms and compute DF (Document Frequency)
    df_counts: Dict[str, int] = {}
    doc_tfs: List[Dict[str, int]] = []
    
    for idx, doc in enumerate(documents):
        # We index question, titre, and contenu_pour_indexation
        text_to_index = f"{doc.get('question', '')} {doc.get('categorie', '')} {doc.get('contenu_pour_indexation', '')}"
        tokens = tokenize(text_to_index)
        
        # Calculate term frequencies for this doc
        tf: Dict[str, int] = {}
        for token in tokens:
            tf[token] = tf.get(token, 0) + 1
        doc_tfs.append(tf)
        
        # Update document frequency count for terms
        for token in tf.keys():
            df_counts[token] = df_counts.get(token, 0) + 1
            
    # 2. Compute IDF for each term
    N = len(documents)
    idf = {}
    for term, df in df_counts.items():
        # Smoothed IDF
        idf[term] = math.log((N - df + 0.5) / (df + 0.5) + 1.0)
        
    # 3. Create document TF-IDF vectors
    doc_vectors = []
    for tf in doc_tfs:
        vector: Dict[str, float] = {}
        for term, count in tf.items():
            vector[term] = count * idf[term]
        doc_vectors.append(vector)
        
    logger.info(f"Index built successfully. Vocabulary size: {len(df_counts)} terms.")

@app.on_event("startup")
def load_datasets():
    """Load all JSONL datasets into memory and index them on startup."""
    global documents
    documents.clear()
    
    for domain, path in DATA_PATHS.items():
        if not os.path.exists(path):
            logger.warning(f"Dataset for domain '{domain}' not found at {path}. Skipping.")
            continue
            
        logger.info(f"Loading {domain} dataset from {path}...")
        try:
            count = 0
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    doc = json.loads(line)
                    # Normalize domain tags and store
                    doc["domain"] = domain
                    documents.append(doc)
                    count += 1
            logger.info(f"Loaded {count} documents from {domain} dataset.")
        except Exception as e:
            logger.error(f"Error loading {domain} dataset: {e}")
            
    if documents:
        build_index()
    else:
        logger.error("No documents loaded! Search will be unavailable.")

class SearchQuery(BaseModel):
    query: str
    domain: str = "all"  # 'all', 'antai', 'impots', 'service-public'
    limit: int = 5

class ChatMessage(BaseModel):
    role: str # 'user' or 'model' / 'assistant'
    content: str

class ChatQuery(BaseModel):
    query: str
    domain: str = "all"
    history: List[ChatMessage] = []
    apiKey: Optional[str] = None

class ImageAnalysisQuery(BaseModel):
    image_b64: Optional[str] = None
    image: Optional[str] = None

def local_search(query_str: str, domain: str = "all", limit: int = 5) -> List[Dict[str, Any]]:
    """Perform quick TF-IDF RAG search."""
    if not documents:
        return []
        
    query_tokens = tokenize(query_str)
    if not query_tokens:
        # Return random/first docs if query is empty
        filtered = [doc for doc in documents if domain == "all" or doc.get("domain") == domain]
        return filtered[:limit]
        
    scores = []
    for idx, doc in enumerate(documents):
        # Filter by domain if specified
        if domain != "all" and doc.get("domain") != domain:
            continue
            
        score = 0.0
        doc_vector = doc_vectors[idx]
        
        # Basic TF-IDF score
        for token in query_tokens:
            if token in doc_vector:
                score += doc_vector[token]
                
        # Question Boost: if terms match the question or category, boost the score
        question_tokens = tokenize(doc.get("question", ""))
        category_tokens = tokenize(doc.get("categorie", ""))
        for token in query_tokens:
            if token in question_tokens:
                score += 3.0 * idf.get(token, 1.0)
            if token in category_tokens:
                score += 2.0 * idf.get(token, 1.0)
                
        if score > 0:
            scores.append((score, doc))
            
    # Sort and return top results
    scores.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scores[:limit]]

@app.get("/api/config")
def get_config():
    """Return administrative counts and environment setup status."""
    counts = {"antai": 0, "impots": 0, "service-public": 0}
    for doc in documents:
        d = doc.get("domain")
        if d in counts:
            counts[d] += 1
            
    return {
        "status": "success",
        "total_documents": len(documents),
        "domain_counts": counts,
        "server_api_key_configured": bool(os.environ.get("GEMINI_API_KEY")),
        "datasets": list(DATA_PATHS.keys())
    }

@app.post("/api/search")
def api_search(payload: SearchQuery):
    """Search endpoint to browse administrative documents."""
    results = local_search(payload.query, payload.domain, payload.limit)
    return {
        "query": payload.query,
        "domain": payload.domain,
        "results": results
    }

def call_gemini_api(api_key: str, system_prompt: str, prompt: str, history: List[ChatMessage]) -> str:
    """Call Google Generative AI API using secure direct REST calls."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    
    # Format message history for Gemini API API
    contents = []
    
    # Add history messages
    for msg in history:
        role = "user" if msg.role == "user" else "model"
        contents.append({
            "role": role,
            "parts": [{"text": msg.content}]
        })
        
    # Append the current prompt
    contents.append({
        "role": "user",
        "parts": [{"text": f"{system_prompt}\n\n{prompt}"}]
    })
    
    payload = {
        "contents": contents,
        "generationConfig": {
            "temperature": 0.3,
            "maxOutputTokens": 2048
        }
    }
    
    headers = {"Content-Type": "application/json"}
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        # Extract text from response
        candidates = data.get("candidates", [])
        if candidates:
            return candidates[0]["content"]["parts"][0]["text"]
        return "Erreur: Impossible de lire le contenu généré par l'IA."
    except Exception as e:
        logger.error(f"Error calling Gemini REST API: {e}")
        raise HTTPException(status_code=502, detail=f"Gemini API Error: {str(e)}")

@app.post("/api/chat")
def api_chat(payload: ChatQuery):
    """Secure RAG chatbot with local simulated search as a fallback."""
    # 1. Retrieve context
    results = local_search(payload.query, payload.domain, limit=4)
    
    # 2. Get API key (from request payload, headers, or server environment)
    api_key = payload.apiKey or os.environ.get("GEMINI_API_KEY")
    
    if not results:
        # If no results found, give a standard fallback
        return {
            "answer": "Désolé, je n'ai trouvé aucun document officiel dans nos bases concernant votre demande. Veuillez affiner vos termes de recherche (ex: 'contester PV', 'déclaration revenus', 'logement social').",
            "sources": [],
            "mode": "no_context"
        }
        
    # Format context for RAG
    context_blocks = []
    for doc in results:
        delais = ", ".join(doc.get("delais_mentionnes", [])) or "Aucun délai spécifié"
        liens = ", ".join(doc.get("liens_demarches", [])) or "Aucun lien officiel"
        block = (
            f"--- SOURCE: {doc.get('source')} ({doc.get('categorie')}) ---\n"
            f"Question/Titre: {doc.get('question') or doc.get('titre')}\n"
            f"Contenu: {doc.get('contenu')}\n"
            f"Délais mentionnés: {delais}\n"
            f"Liens officiels: {liens}\n"
            f"URL d'origine: {doc.get('url')}\n"
        )
        context_blocks.append(block)
    context_str = "\n".join(context_blocks)
    
    # If API Key is configured, run Gemini RAG
    if api_key:
        system_prompt = (
            "Vous êtes CivicAssist.IA, un assistant virtuel d'aide administrative française premium. "
            "Vous assistez les citoyens de façon claire, rassurante et professionnelle.\n\n"
            "Règles strictes :\n"
            "1. Répondez UNIQUEMENT en français en vous basant sur le contexte fourni ci-dessous.\n"
            "2. Citez impérativement les URL officielles fournies dans le contexte sous forme de liens clairs (ex: [Titre](url)).\n"
            "3. Indiquez clairement les délais importants mentionnés (ex: 45 jours, 3 mois) en gras précédés de l'émoji 📅.\n"
            "4. Si le contexte ne contient pas la réponse, dites-le poliment et proposez de reformuler.\n"
            "5. Structurez votre réponse avec des titres de section courts (Markdown) et des puces pour une clarté absolue."
        )
        
        prompt = (
            f"CONTEXTE RETROUVÉ :\n{context_str}\n\n"
            f"QUESTION DE L'USAGER :\n{payload.query}"
        )
        
        try:
            answer = call_gemini_api(api_key, system_prompt, prompt, payload.history)
            return {
                "answer": answer,
                "sources": results,
                "mode": "gemini_rag"
            }
        except Exception as e:
            logger.error(f"Gemini API call failed, falling back to simulated search: {e}")
            # Fall back to simulated search on error
            
    # Simulated search mode (standard out-of-the-box experience)
    best_doc = results[0]
    title = best_doc.get("question") or best_doc.get("titre")
    source_name = "ANTAI" if best_doc.get("domain") == "antai" else ("Impôts" if best_doc.get("domain") == "impots" else "Service-Public")
    
    delais_list = best_doc.get("delais_mentionnes", [])
    delais_str = "\n".join([f"- 📅 **{d}**" for d in delais_list]) if delais_list else "- Aucun délai spécifique trouvé dans ce document."
    
    liens_list = best_doc.get("liens_demarches", [])
    liens_str = "\n".join([f"- [Accéder à la démarche en ligne]({link})" for link in liens_list if link.startswith("http")])
    if not liens_str:
        liens_str = f"- [Consulter la page officielle de référence]({best_doc.get('url')})"
        
    answer = (
        f"🔍 **[CivicAssist - Recherche Locale active]**\n\n"
        f"Voici les informations officielles extraites de la base de données **{source_name}** concernant votre demande :\n\n"
        f"### {title}\n\n"
        f"{best_doc.get('contenu')}\n\n"
        f"### 📅 Délais & Modalités importantes :\n"
        f"{delais_str}\n\n"
        f"### 🔗 Liens & Démarches utiles :\n"
        f"{liens_str}\n\n"
        f"---\n"
        f"*💡 Note : CivicAssist.IA fonctionne actuellement en mode local optimisé car aucune clé Gemini n'est configurée. Pour obtenir des réponses rédigées dynamiquement par l'IA, ajoutez votre clé Gemini sécurisée dans les Réglages.*"
    )
    
    return {
        "answer": answer,
        "sources": results,
        "mode": "simulated_rag"
    }

@app.post("/api/image")
def api_image(payload: ImageAnalysisQuery):
    """Relay image analysis through the backend to avoid browser CORS issues."""
    image_b64 = (payload.image_b64 or payload.image or "").strip()

    if not image_b64:
        raise HTTPException(status_code=400, detail="Image base64 manquante.")

    try:
        response = requests.post(
            IMAGE_ANALYSIS_UPSTREAM_URL,
            json={"image_b64": image_b64},
            headers={"Content-Type": "application/json"},
            timeout=60,
        )
    except requests.RequestException as e:
        logger.error(f"Error calling upstream image analysis API: {e}")
        raise HTTPException(status_code=502, detail="Service d'analyse d'image indisponible.")

    try:
        data = response.json()
    except ValueError as e:
        logger.error(f"Invalid JSON from upstream image analysis API: {e}")
        raise HTTPException(
            status_code=502,
            detail="Le service d'analyse d'image a renvoyé une réponse invalide.",
        )

    result_type = data.get("type")
    error_message = data.get("error") or data.get("detail")

    if not response.ok:
        detail = data.get("answer") or error_message or "Le service d'analyse d'image a renvoyé une erreur."
        raise HTTPException(status_code=502, detail=detail)

    answer = data.get("answer")

    if isinstance(error_message, str) and error_message.strip() and (not isinstance(answer, str) or not answer.strip()):
        raise HTTPException(status_code=502, detail=error_message)

    if not isinstance(answer, str) or not answer.strip():
        raise HTTPException(
            status_code=502,
            detail="Le service d'analyse d'image a renvoyé une réponse invalide.",
        )

    return {
        "answer": answer,
        "type": result_type if isinstance(result_type, str) else "success",
    }

# Mount static frontend files
if os.path.exists(os.path.join(BASE_DIR, "front")):
    app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "front"), html=True), name="front")
else:
    logger.warning("Frontend 'front/' directory not found. Please create it so the server can serve static files.")
