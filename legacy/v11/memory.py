#!/usr/bin/env python3
"""
memory.py — Long-Term Memory System for Amuara Labs Nova 1.5b Agent

Implements persistent semantic memory allowing the agent to:
  1. Store past solutions and insights.
  2. Recall relevant context across conversational sessions.
  3. Manage token limits by retrieving only semantically relevant history.
"""

import os
import json
import time
import hashlib
from typing import List, Dict, Any, Optional

# Optional fallback to basic keyword matching if embedding models aren't installed
try:
    import numpy as np
    from sentence_transformers import SentenceTransformer
    HAS_EMBEDDINGS = True
except ImportError:
    HAS_EMBEDDINGS = False


class SemanticMemory:
    """
    Long-term memory store using local embeddings or fallback keyword matching.
    """
    def __init__(self, memory_dir: str = ".fable_memory", model_name: str = "all-MiniLM-L6-v2"):
        self.memory_dir = os.path.abspath(memory_dir)
        os.makedirs(self.memory_dir, exist_ok=True)
        self.store_path = os.path.join(self.memory_dir, "memory_store.json")
        self.index_path = os.path.join(self.memory_dir, "embeddings.npy")
        
        self.memories: List[Dict[str, Any]] = []
        self.embeddings = None
        
        if HAS_EMBEDDINGS:
            # We load the model lazily if needed
            self.model_name = model_name
            self.encoder = None
        
        self._load_store()

    def _load_store(self):
        if os.path.exists(self.store_path):
            with open(self.store_path, "r") as f:
                self.memories = json.load(f)
                
        if HAS_EMBEDDINGS and os.path.exists(self.index_path):
            self.embeddings = np.load(self.index_path)
            # Basic sanity check
            if len(self.embeddings) != len(self.memories):
                print("[Memory] Embedding mismatch. Rebuilding index on next save.")
                self.embeddings = None

    def _save_store(self):
        with open(self.store_path, "w") as f:
            json.dump(self.memories, f, indent=2)
            
        if HAS_EMBEDDINGS and self.embeddings is not None:
            np.save(self.index_path, self.embeddings)

    def _get_encoder(self):
        if not HAS_EMBEDDINGS:
            return None
        if self.encoder is None:
            self.encoder = SentenceTransformer(self.model_name)
        return self.encoder

    def add_memory(self, text: str, tags: List[str] = None, metadata: Dict[str, Any] = None):
        """Add a new memory to the persistent store."""
        memory_id = hashlib.md5(f"{text}{time.time()}".encode()).hexdigest()[:12]
        entry = {
            "id": memory_id,
            "timestamp": time.time(),
            "text": text,
            "tags": tags or [],
            "metadata": metadata or {}
        }
        
        self.memories.append(entry)
        
        if HAS_EMBEDDINGS:
            encoder = self._get_encoder()
            emb = encoder.encode([text])[0]
            if self.embeddings is None:
                self.embeddings = np.array([emb])
            else:
                self.embeddings = np.vstack([self.embeddings, emb])
                
        self._save_store()
        print(f"[Memory] Added memory {memory_id}")
        return memory_id

    def create_snapshot(self) -> str:
        """Create a checkpoint of the current memory state for episodic rollbacks."""
        snapshot_id = hashlib.md5(str(time.time()).encode()).hexdigest()[:8]
        snapshot_path = os.path.join(self.memory_dir, f"snapshot_{snapshot_id}.json")
        with open(snapshot_path, "w") as f:
            json.dump(self.memories, f, indent=2)
        print(f"[Memory] Created snapshot {snapshot_id}")
        return snapshot_id

    def rollback(self, snapshot_id: str) -> bool:
        """Rollback memory state to a previous snapshot."""
        snapshot_path = os.path.join(self.memory_dir, f"snapshot_{snapshot_id}.json")
        if not os.path.exists(snapshot_path):
            print(f"[Memory] Rollback failed: Snapshot {snapshot_id} not found.")
            return False
            
        with open(snapshot_path, "r") as f:
            self.memories = json.load(f)
            
        # Rebuild embeddings from scratch since we altered the history
        if HAS_EMBEDDINGS and self.memories:
            encoder = self._get_encoder()
            texts = [m["text"] for m in self.memories]
            self.embeddings = encoder.encode(texts)
        else:
            self.embeddings = None
            
        self._save_store()
        print(f"[Memory] Rolled back to snapshot {snapshot_id}")
        return True

    def retrieve(self, query: str, top_k: int = 3, threshold: float = 0.3) -> List[Dict[str, Any]]:
        """Retrieve the most relevant memories for a given query."""
        if not self.memories:
            return []

        if HAS_EMBEDDINGS and self.embeddings is not None:
            encoder = self._get_encoder()
            query_emb = encoder.encode([query])[0]
            
            # Cosine similarity
            norms = np.linalg.norm(self.embeddings, axis=1)
            q_norm = np.linalg.norm(query_emb)
            if q_norm == 0:
                return []
                
            sims = np.dot(self.embeddings, query_emb) / (norms * q_norm)
            
            # Get top k indices above threshold
            indices = np.argsort(sims)[::-1]
            results = []
            for idx in indices[:top_k]:
                if sims[idx] >= threshold:
                    mem = self.memories[idx].copy()
                    mem["score"] = float(sims[idx])
                    results.append(mem)
            return results
            
        else:
            # Fallback BM25-ish keyword matching (simplified)
            query_terms = set(query.lower().split())
            scored = []
            for mem in self.memories:
                text_terms = set(mem["text"].lower().split())
                tag_terms = set([t.lower() for t in mem["tags"]])
                
                # Simple overlap score
                overlap = len(query_terms.intersection(text_terms))
                overlap += len(query_terms.intersection(tag_terms)) * 2 # Weight tags higher
                
                if overlap > 0:
                    scored.append((overlap, mem))
                    
            scored.sort(key=lambda x: x[0], reverse=True)
            return [mem for score, mem in scored[:top_k]]

    def clear(self):
        """Clear all memories."""
        self.memories = []
        self.embeddings = None
        if os.path.exists(self.store_path):
            os.remove(self.store_path)
        if os.path.exists(self.index_path):
            os.remove(self.index_path)
        print("[Memory] Cleared all memories.")


def _self_test():
    """Run a basic functionality test."""
    print("="*40)
    print(" MEMORY SYSTEM SELF-TEST ")
    print("="*40)
    
    # Use a temporary directory
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        mem = SemanticMemory(memory_dir=tmp)
        
        # Add memories
        mem.add_memory("The user prefers using pytest for all Python testing.", tags=["preference", "testing"])
        mem.add_memory("Nova 1.5b router logic was updated to use ReAct pattern.", tags=["architecture"])
        mem.add_memory("To clear the cache, run redis-cli flushall.", tags=["command", "database"])
        
        assert len(mem.memories) == 3, "Failed to add memories"
        print("✓ Memory addition successful.")
        
        # Test Retrieval
        res = mem.retrieve("How do I clear the redis database?")
        assert len(res) > 0, "Retrieval failed"
        assert "flushall" in res[0]["text"], "Incorrect memory retrieved"
        print(f"✓ Retrieval successful (Top result: {res[0]['text'][:30]}...)")
        
        print("\nAll memory tests PASSED ✓")

if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        _self_test()
    else:
        print("Run with --self-test to execute tests.")
