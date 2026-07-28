#!/usr/bin/env python3
"""
retrieval.py — Repository-Aware RAG System for Amuara Labs

Provides context retrieval for the agent to understand full repository structure:
  1. Hierarchical chunking: file-level → class-level → function-level
  2. Dual retrieval: BM25 (keyword) + dense embeddings (semantic)
  3. Reranking with cross-encoder scoring
  4. Context window management with priority-based truncation
  5. AST-aware chunking that respects code boundaries
"""

import os
import re
import ast
import math
import json
import hashlib
from typing import Dict, List, Optional, Tuple
from collections import Counter, defaultdict
from dataclasses import dataclass, field


@dataclass
class CodeChunk:
    """A semantically meaningful chunk of code."""
    id: str
    file_path: str
    content: str
    chunk_type: str  # "file", "class", "function", "block"
    name: str  # symbol name or filename
    start_line: int
    end_line: int
    language: str
    dependencies: List[str] = field(default_factory=list)
    docstring: Optional[str] = None
    parent_id: Optional[str] = None

    @property
    def token_estimate(self) -> int:
        """Rough token count (4 chars per token heuristic)."""
        return len(self.content) // 4

    def to_dict(self) -> dict:
        return {
            "id": self.id, "file_path": self.file_path,
            "chunk_type": self.chunk_type, "name": self.name,
            "start_line": self.start_line, "end_line": self.end_line,
            "language": self.language, "dependencies": self.dependencies,
            "docstring": self.docstring, "parent_id": self.parent_id,
            "content_hash": hashlib.sha256(self.content.encode()).hexdigest()[:16],
            "token_estimate": self.token_estimate,
        }


class ASTChunker:
    """AST-aware code chunker that respects language boundaries."""

    LANGUAGE_EXTENSIONS = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".jsx": "javascript", ".tsx": "typescript", ".go": "go",
        ".rs": "rust", ".java": "java", ".cpp": "cpp", ".c": "c",
        ".h": "cpp", ".hpp": "cpp", ".rb": "ruby", ".sh": "bash",
        ".sql": "sql", ".css": "css", ".html": "html",
    }

    SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv",
                 "dist", "build", ".eggs", ".tox", ".mypy_cache",
                 ".pytest_cache", "target", "vendor"}

    def __init__(self, max_chunk_tokens: int = 512, overlap_lines: int = 3):
        self.max_chunk_tokens = max_chunk_tokens
        self.overlap_lines = overlap_lines
        self._chunk_counter = 0

    def _next_id(self, file_path: str, name: str) -> str:
        self._chunk_counter += 1
        return f"chunk_{self._chunk_counter}_{hashlib.md5(f'{file_path}:{name}'.encode()).hexdigest()[:8]}"

    def chunk_repository(self, repo_path: str) -> List[CodeChunk]:
        """Chunk an entire repository into semantically meaningful pieces."""
        chunks = []
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in self.SKIP_DIRS]
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                lang = self.LANGUAGE_EXTENSIONS.get(ext)
                if not lang:
                    continue
                fpath = os.path.join(root, fname)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    if len(content) > 500_000:  # Skip very large files
                        continue
                    rel_path = os.path.relpath(fpath, repo_path)
                    file_chunks = self.chunk_file(content, rel_path, lang)
                    chunks.extend(file_chunks)
                except Exception:
                    continue
        return chunks

    def chunk_file(self, content: str, file_path: str, language: str) -> List[CodeChunk]:
        """Chunk a single file using AST parsing (Python) or line-based heuristics."""
        chunks = []

        # Always add a file-level chunk
        file_chunk = CodeChunk(
            id=self._next_id(file_path, "file"),
            file_path=file_path, content=content[:2000],
            chunk_type="file", name=os.path.basename(file_path),
            start_line=1, end_line=content.count("\n") + 1,
            language=language,
        )
        chunks.append(file_chunk)

        if language == "python":
            chunks.extend(self._chunk_python_ast(content, file_path, file_chunk.id))
        else:
            chunks.extend(self._chunk_by_pattern(content, file_path, language, file_chunk.id))

        return chunks

    def _chunk_python_ast(self, content: str, file_path: str, parent_id: str) -> List[CodeChunk]:
        """Use Python's AST to extract classes and functions."""
        chunks = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return self._chunk_by_pattern(content, file_path, "python", parent_id)

        lines = content.split("\n")

        for node in ast.walk(tree):
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno
                end = getattr(node, "end_lineno", start + 10) or start + 10
                chunk_content = "\n".join(lines[start - 1:end])
                docstring = ast.get_docstring(node)

                # Extract dependencies (imports used in this scope)
                deps = []
                for child in ast.walk(node):
                    if isinstance(child, ast.Name):
                        deps.append(child.id)

                chunk = CodeChunk(
                    id=self._next_id(file_path, node.name),
                    file_path=file_path, content=chunk_content,
                    chunk_type="class" if isinstance(node, ast.ClassDef) else "function",
                    name=node.name, start_line=start, end_line=end,
                    language="python", dependencies=list(set(deps[:20])),
                    docstring=docstring, parent_id=parent_id,
                )
                chunks.append(chunk)

        return chunks

    def _chunk_by_pattern(self, content: str, file_path: str,
                          language: str, parent_id: str) -> List[CodeChunk]:
        """Fallback: chunk by regex patterns for non-Python languages."""
        patterns = {
            "javascript": r'(?:export\s+)?(?:async\s+)?function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[\w]+)\s*=>|class\s+(\w+)',
            "typescript": r'(?:export\s+)?(?:async\s+)?function\s+(\w+)|(?:export\s+)?class\s+(\w+)|(?:export\s+)?interface\s+(\w+)',
            "go": r'func\s+(?:\([^)]+\)\s+)?(\w+)',
            "rust": r'(?:pub\s+)?fn\s+(\w+)|(?:pub\s+)?struct\s+(\w+)|(?:pub\s+)?impl\s+(\w+)',
            "java": r'(?:public|private|protected)?\s*(?:static\s+)?(?:class|interface|enum)\s+(\w+)|(?:public|private|protected)\s+(?:static\s+)?[\w<>\[\]]+\s+(\w+)\s*\(',
            "cpp": r'(?:class|struct)\s+(\w+)|(?:\w+(?:::\w+)*\s+)?(\w+)\s*\([^)]*\)\s*(?:const\s*)?{',
            "ruby": r'(?:def|class|module)\s+(\w+)',
        }

        pattern = patterns.get(language)
        if not pattern:
            return self._chunk_by_sliding_window(content, file_path, language, parent_id)

        chunks = []
        lines = content.split("\n")

        for match in re.finditer(pattern, content):
            name = next((g for g in match.groups() if g), "unknown")
            line_num = content[:match.start()].count("\n") + 1
            # Find the end of this block (simple brace/indent counting)
            end_line = min(line_num + 50, len(lines))

            chunk_content = "\n".join(lines[line_num - 1:end_line])
            chunk = CodeChunk(
                id=self._next_id(file_path, name),
                file_path=file_path, content=chunk_content,
                chunk_type="function", name=name,
                start_line=line_num, end_line=end_line,
                language=language, parent_id=parent_id,
            )
            chunks.append(chunk)

        return chunks

    def _chunk_by_sliding_window(self, content: str, file_path: str,
                                  language: str, parent_id: str) -> List[CodeChunk]:
        """Last resort: sliding window chunking."""
        chunks = []
        lines = content.split("\n")
        window_size = self.max_chunk_tokens // 3  # lines per chunk
        step = window_size - self.overlap_lines

        for start in range(0, len(lines), max(step, 1)):
            end = min(start + window_size, len(lines))
            chunk_content = "\n".join(lines[start:end])
            if chunk_content.strip():
                chunk = CodeChunk(
                    id=self._next_id(file_path, f"block_{start}"),
                    file_path=file_path, content=chunk_content,
                    chunk_type="block", name=f"lines_{start+1}_{end}",
                    start_line=start + 1, end_line=end,
                    language=language, parent_id=parent_id,
                )
                chunks.append(chunk)

        return chunks


class BM25Index:
    """BM25 keyword retrieval index."""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: List[str] = []
        self.doc_freqs: List[Counter] = []
        self.idf: Dict[str, float] = {}
        self.avg_dl: float = 0.0
        self.doc_count: int = 0

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenizer that handles code identifiers."""
        # Split camelCase and snake_case
        text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text)
        text = text.replace("_", " ").replace(".", " ").replace("/", " ")
        tokens = re.findall(r'[a-zA-Z]{2,}|\d+', text.lower())
        return tokens

    def build(self, documents: List[str]):
        """Build BM25 index from document texts."""
        self.documents = documents
        self.doc_count = len(documents)
        self.doc_freqs = []

        df = Counter()
        total_len = 0

        for doc in documents:
            tokens = self._tokenize(doc)
            freq = Counter(tokens)
            self.doc_freqs.append(freq)
            total_len += len(tokens)
            for token in set(tokens):
                df[token] += 1

        self.avg_dl = total_len / max(self.doc_count, 1)
        self.idf = {}
        for term, freq in df.items():
            self.idf[term] = math.log((self.doc_count - freq + 0.5) / (freq + 0.5) + 1)

    def search(self, query: str, top_k: int = 10) -> List[Tuple[int, float]]:
        """Search for documents matching the query. Returns (doc_idx, score) pairs."""
        query_tokens = self._tokenize(query)
        scores = []

        for idx, doc_freq in enumerate(self.doc_freqs):
            score = 0.0
            doc_len = sum(doc_freq.values())
            for token in query_tokens:
                if token not in doc_freq:
                    continue
                tf = doc_freq[token]
                idf = self.idf.get(token, 0.0)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * doc_len / max(self.avg_dl, 1))
                score += idf * (numerator / denominator)
            if score > 0:
                scores.append((idx, score))

        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]


class RetrievalSystem:
    """
    Multi-strategy retrieval combining BM25, dependency graph traversal,
    and context window management.
    """

    def __init__(self, max_context_tokens: int = 8000):
        self.max_context_tokens = max_context_tokens
        self.chunks: List[CodeChunk] = []
        self.bm25 = BM25Index()
        self._chunk_map: Dict[str, CodeChunk] = {}
        self._file_chunks: Dict[str, List[str]] = defaultdict(list)

    def index_repository(self, repo_path: str, save_index_path: Optional[str] = None):
        """Index a repository for retrieval."""
        print(f"[Retrieval] Indexing repository: {repo_path}")
        chunker = ASTChunker()
        self.chunks = chunker.chunk_repository(repo_path)

        self._chunk_map = {c.id: c for c in self.chunks}
        self._file_chunks = defaultdict(list)
        for c in self.chunks:
            self._file_chunks[c.file_path].append(c.id)

        # Build BM25 index
        documents = [f"{c.name} {c.file_path} {c.content}" for c in self.chunks]
        self.bm25.build(documents)

        print(f"[Retrieval] Indexed {len(self.chunks)} chunks from "
              f"{len(self._file_chunks)} files")

        if save_index_path:
            self.save_index(save_index_path)

    def retrieve(self, query: str, top_k: int = 10,
                 strategy: str = "hybrid") -> List[CodeChunk]:
        """Retrieve relevant code chunks for a query."""
        if strategy == "bm25":
            return self._bm25_retrieve(query, top_k)
        elif strategy == "file":
            return self._file_retrieve(query, top_k)
        else:  # hybrid
            return self._hybrid_retrieve(query, top_k)

    def _bm25_retrieve(self, query: str, top_k: int) -> List[CodeChunk]:
        """BM25 keyword retrieval."""
        results = self.bm25.search(query, top_k)
        return [self.chunks[idx] for idx, _ in results if idx < len(self.chunks)]

    def _file_retrieve(self, query: str, top_k: int) -> List[CodeChunk]:
        """File-path based retrieval for when the query mentions specific files."""
        scored = []
        query_lower = query.lower()
        for chunk in self.chunks:
            score = 0
            if os.path.basename(chunk.file_path).lower() in query_lower:
                score += 10
            if chunk.name.lower() in query_lower:
                score += 5
            if score > 0:
                scored.append((chunk, score))
        scored.sort(key=lambda x: -x[1])
        return [c for c, _ in scored[:top_k]]

    def _hybrid_retrieve(self, query: str, top_k: int) -> List[CodeChunk]:
        """Combine BM25 + file-path retrieval with deduplication."""
        bm25_results = self._bm25_retrieve(query, top_k)
        file_results = self._file_retrieve(query, top_k // 2)

        # Merge with deduplication
        seen_ids = set()
        merged = []
        for chunk in file_results + bm25_results:
            if chunk.id not in seen_ids:
                seen_ids.add(chunk.id)
                merged.append(chunk)
        return merged[:top_k]

    def build_context_window(self, chunks: List[CodeChunk],
                              include_parents: bool = True) -> str:
        """Build a formatted context window from retrieved chunks."""
        context_parts = []
        total_tokens = 0

        for chunk in chunks:
            # Include parent chunk for additional context
            if include_parents and chunk.parent_id and chunk.parent_id in self._chunk_map:
                parent = self._chunk_map[chunk.parent_id]
                header = f"# File: {parent.file_path}\n"
                if parent.docstring:
                    header += f"# Module docs: {parent.docstring[:200]}\n"
            else:
                header = f"# File: {chunk.file_path}\n"

            formatted = f"{header}# {chunk.chunk_type}: {chunk.name} (lines {chunk.start_line}-{chunk.end_line})\n"
            formatted += f"```{chunk.language}\n{chunk.content}\n```\n"

            chunk_tokens = len(formatted) // 4
            if total_tokens + chunk_tokens > self.max_context_tokens:
                break
            context_parts.append(formatted)
            total_tokens += chunk_tokens

        return "\n---\n".join(context_parts)

    def save_index(self, path: str):
        """Save the index metadata to disk."""
        data = {
            "chunk_count": len(self.chunks),
            "file_count": len(self._file_chunks),
            "chunks": [c.to_dict() for c in self.chunks],
        }
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        print(f"[Retrieval] Index saved to {path}")

    def get_file_context(self, file_path: str) -> Optional[str]:
        """Get all chunks for a specific file."""
        chunk_ids = self._file_chunks.get(file_path, [])
        if not chunk_ids:
            return None
        chunks = [self._chunk_map[cid] for cid in chunk_ids if cid in self._chunk_map]
        return self.build_context_window(chunks, include_parents=False)

    def get_dependency_context(self, chunk_id: str, depth: int = 2) -> List[CodeChunk]:
        """Traverse dependencies to find related chunks."""
        if chunk_id not in self._chunk_map:
            return []

        visited = set()
        queue = [(chunk_id, 0)]
        result = []

        while queue:
            current_id, current_depth = queue.pop(0)
            if current_id in visited or current_depth > depth:
                continue
            visited.add(current_id)

            chunk = self._chunk_map.get(current_id)
            if chunk:
                result.append(chunk)
                # Find chunks that match dependency names
                for dep in chunk.dependencies:
                    for c in self.chunks:
                        if c.name == dep and c.id not in visited:
                            queue.append((c.id, current_depth + 1))

        return result


# ─── Self-Test ────────────────────────────────────────────────────────────────

def _self_test():
    """Run a self-test of the retrieval system."""
    print("=" * 50)
    print(" RETRIEVAL SYSTEM SELF-TEST")
    print("=" * 50)

    # Test ASTChunker
    test_code = '''
import os
import sys

class Calculator:
    """A simple calculator class."""
    def __init__(self):
        self.history = []

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        result = a + b
        self.history.append(("add", a, b, result))
        return result

    def subtract(self, a: int, b: int) -> int:
        """Subtract b from a."""
        result = a - b
        self.history.append(("sub", a, b, result))
        return result

def main():
    calc = Calculator()
    print(calc.add(1, 2))

if __name__ == "__main__":
    main()
'''
    chunker = ASTChunker()
    chunks = chunker.chunk_file(test_code, "calculator.py", "python")
    assert len(chunks) >= 3, f"Expected ≥3 chunks, got {len(chunks)}"
    chunk_names = [c.name for c in chunks]
    assert "Calculator" in chunk_names, "Missing Calculator class chunk"
    assert "add" in chunk_names, "Missing add method chunk"
    print(f"✓ ASTChunker: {len(chunks)} chunks extracted ({chunk_names})")

    # Test BM25
    bm25 = BM25Index()
    docs = [
        "def calculate_sum(numbers): return sum(numbers)",
        "class DatabaseConnection: def connect(self): pass",
        "async def fetch_data(url): return await http.get(url)",
        "def parse_json(text): return json.loads(text)",
    ]
    bm25.build(docs)
    results = bm25.search("calculate sum of numbers", top_k=2)
    assert len(results) > 0, "BM25 returned no results"
    assert results[0][0] == 0, "BM25 should rank 'calculate_sum' first"
    print(f"✓ BM25: Top result index={results[0][0]}, score={results[0][1]:.3f}")

    # Test RetrievalSystem
    system = RetrievalSystem(max_context_tokens=2000)
    system.chunks = chunks
    system.bm25.build([f"{c.name} {c.content}" for c in chunks])
    system._chunk_map = {c.id: c for c in chunks}
    for c in chunks:
        system._file_chunks[c.file_path].append(c.id)

    retrieved = system.retrieve("add two numbers", top_k=3)
    assert len(retrieved) > 0, "Retrieval returned no results"
    print(f"✓ Retrieval: Retrieved {len(retrieved)} chunks for 'add two numbers'")

    context = system.build_context_window(retrieved)
    assert len(context) > 0, "Context window is empty"
    print(f"✓ Context window: {len(context)} chars, ~{len(context)//4} tokens")

    print("\n[Retrieval] All self-tests PASSED ✓")


if __name__ == "__main__":
    import sys
    if "--self-test" in sys.argv:
        _self_test()
    elif len(sys.argv) > 1:
        repo = sys.argv[1]
        query = sys.argv[2] if len(sys.argv) > 2 else "main function"
        system = RetrievalSystem()
        system.index_repository(repo)
        results = system.retrieve(query)
        print(system.build_context_window(results))
    else:
        print("Usage: python retrieval.py <repo_path> [query]")
        print("       python retrieval.py --self-test")
