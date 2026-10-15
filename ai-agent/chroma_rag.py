import os
import chromadb
from chromadb.utils import embedding_functions

# Initialize ChromaDB locally
CHROMA_PATH = os.path.join(os.path.dirname(__file__), "chroma_db")
client = chromadb.PersistentClient(path=CHROMA_PATH)

# Use a free huggingface embedding model (runs completely locally, no API key needed)
sentence_transformer_ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")

collection = client.get_or_create_collection(name="sre_knowledge", embedding_function=sentence_transformer_ef)

def init_knowledge_base():
    docs_dir = os.path.join(os.path.dirname(__file__), "knowledge")
    if not os.path.exists(docs_dir):
        return
        
    for idx, file in enumerate(os.listdir(docs_dir)):
        if file.endswith(".md"):
            with open(os.path.join(docs_dir, file), "r", encoding="utf-8") as f:
                content = f.read()
                # Check if document already exists
                existing = collection.get(ids=[str(idx)])
                if not existing['ids']:
                    collection.add(
                        documents=[content],
                        metadatas=[{"source": file}],
                        ids=[str(idx)]
                    )
    print("✅ RAG Knowledge Base Initialized via ChromaDB (HuggingFace Embeddings)")

def search_kb(query: str, limit: int = 2):
    print(f"[*] RAG Searching Knowledge Base for: '{query}'")
    results = collection.query(
        query_texts=[query],
        n_results=limit
    )
    docs = results.get("documents", [[]])[0]
    # Truncate each document to ~1000 characters to heavily reduce token usage
    return [doc[:1000] + "\n...[TRUNCATED]" if len(doc) > 1000 else doc for doc in docs]

if __name__ == "__main__":
    init_knowledge_base()
