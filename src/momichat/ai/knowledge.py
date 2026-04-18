"""
Knowledge Base manager for the AI.
Loads Menu.csv into an O(1) in-memory dictionary for exact price lookup
and into ChromaDB for semantic search.
"""

import csv
import logging
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Menu in-memory dictionary
MENU_DICT: dict[str, dict] = {}


class KnowledgeBase:
    def __init__(self) -> None:
        self.chroma_client = chromadb.HttpClient(host="localhost", port=8000)
        # We will lazily load the model on first use to speed up app startups
        self._encoder: SentenceTransformer | None = None
        
        try:
            self.collection = self.chroma_client.get_or_create_collection(name="menu")
        except Exception as e:
            logger.error(f"Failed to connect to ChromaDB: {e}")
            self.collection = None

    @property
    def encoder(self) -> SentenceTransformer:
        if self._encoder is None:
            logger.info("Lazily initializing SentenceTransformer...")
            self._encoder = SentenceTransformer("all-MiniLM-L6-v2")
        return self._encoder

    def initialize_menu(self, csv_path: Path) -> None:
        """Parses Menu.csv, builds MENU_DICT, and vectors strings into ChromaDB."""
        if not csv_path.exists():
            logger.error(f"Menu file not found at {csv_path}")
            return

        documents = []
        ids = []
        metadatas = []

        with open(csv_path, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                item_id = row["item_id"]
                # Store exact data
                MENU_DICT[item_id] = {
                    "name": row["name"],
                    "description": row["description"],
                    "category": row.get("category", "Khác"),
                    "price_m": float(row["price_m"]) if row["price_m"] else None,
                    "price_l": float(row["price_l"]) if row["price_l"] else None,
                    "available": str(row["available"]).lower() == "true",
                }
                
                # Build search document
                search_text = f"{row['category']} - {row['name']}: {row['description']}"
                documents.append(search_text)
                ids.append(item_id)
                metadatas.append({"category": row["category"], "name": row["name"]})

        logger.info(f"Loaded {len(MENU_DICT)} items into memory dictionary.")

        # Vectorize to ChromaDB (only if collection is empty to save time)
        if self.collection and self.collection.count() == 0:
            embeddings = self.encoder.encode(documents).tolist()
            self.collection.add(
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas,
                ids=ids,
            )
            logger.info("Embedded menu items into ChromaDB.")

    def search_menu(self, query: str, k: int = 10) -> list[dict]:
        """Semantically search the menu."""
        if not self.collection:
            return []
            
        embeddings = self.encoder.encode([query]).tolist()
        results = self.collection.query(
            query_embeddings=embeddings,
            n_results=k
        )
        
        out = []
        if results and results["documents"]:
            for item_id, doc in zip(results["ids"][0], results["documents"][0]):
                out.append({"item_id": item_id, "snippet": doc})
        return out
