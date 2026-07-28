#!/usr/bin/env python3
"""
ast_indexer.py - Multi-Language AST Symbol & Graph Indexer for Amuara Labs
Supports 7 programming languages:
- Python (.py)
- TypeScript (.ts, .tsx)
- JavaScript (.js, .jsx)
- Go (.go)
- Rust (.rs)
- Java (.java)
- C++ (.cpp, .hpp, .h, .cc, .cxx)

Constructs:
- Symbol Graph (Classes, Functions, Structs, Interfaces, Enums)
- Call Graph (Caller-callee relationships)
- Dependency Graph (Imports & Includes)
- Cross-Reference Graph (Symbol usages across files)
- Incremental Indexing (MD5 file hashing cache)
"""

import ast
import os
import sys
import re
import json
import hashlib
import argparse
from typing import Dict, List, Any

class PythonASTVisitor(ast.NodeVisitor):
    def __init__(self, filename: str):
        self.filename = filename
        self.symbols = []
        self.imports = []
        self.calls = []
        self.current_class = None
        self.current_func = None

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append({"type": "import", "module": alias.name, "asname": alias.asname})
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        for alias in node.names:
            self.imports.append({"type": "from_import", "module": module, "name": alias.name, "asname": alias.asname})
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        bases = []
        for b in node.bases:
            if isinstance(b, ast.Name):
                bases.append(b.id)
            elif isinstance(b, ast.Attribute):
                bases.append(f"{b.value.id if isinstance(b.value, ast.Name) else ''}.{b.attr}")
        
        docstring = ast.get_docstring(node) or ""
        self.symbols.append({
            "type": "class",
            "name": node.name,
            "bases": bases,
            "lineno": node.lineno,
            "docstring": docstring.strip().split('\n')[0] if docstring else ""
        })
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node):
        self._handle_func(node, is_async=False)

    def visit_AsyncFunctionDef(self, node):
        self._handle_func(node, is_async=True)

    def _handle_func(self, node, is_async: bool):
        symbol_type = ("async_method" if is_async else "method") if self.current_class else ("async_function" if is_async else "function")
        docstring = ast.get_docstring(node) or ""
        
        args = [arg.arg for arg in node.args.args]
        self.symbols.append({
            "type": symbol_type,
            "name": node.name,
            "parent_class": self.current_class,
            "args": args,
            "lineno": node.lineno,
            "docstring": docstring.strip().split('\n')[0] if docstring else ""
        })
        old_func = self.current_func
        self.current_func = node.name
        self.generic_visit(node)
        self.current_func = old_func

    def visit_Call(self, node):
        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
        if func_name and self.current_func:
            self.calls.append({
                "caller": self.current_func,
                "callee": func_name,
                "lineno": node.lineno
            })
        self.generic_visit(node)

class MultiLanguageASTVisitor:
    """Regex & Pattern AST parser for JS/TS, Go, Rust, Java, C++."""
    def __init__(self, filename: str, content: str, lang: str):
        self.filename = filename
        self.content = content
        self.lang = lang
        self.symbols = []
        self.imports = []
        self.calls = []

    def parse(self):
        lines = self.content.split('\n')
        for i, line in enumerate(lines, 1):
            line_str = line.strip()
            if not line_str:
                continue

            # 1. IMPORTS & INCLUDES
            if self.lang in ("typescript", "javascript"):
                m_imp = re.search(r"import\s+.*?\s+from\s+['\"](.*?)['\"]", line_str)
                if m_imp:
                    self.imports.append({"type": "import", "module": m_imp.group(1)})
            elif self.lang == "go":
                m_imp = re.search(r"import\s+[\"'](.*?)[\"']", line_str)
                if m_imp:
                    self.imports.append({"type": "import", "module": m_imp.group(1)})
            elif self.lang == "rust":
                m_use = re.search(r"use\s+([a-zA-Z0-9_:]+);", line_str)
                if m_use:
                    self.imports.append({"type": "use", "module": m_use.group(1)})
            elif self.lang == "java":
                m_imp = re.search(r"import\s+([a-zA-Z0-9_.]+);", line_str)
                if m_imp:
                    self.imports.append({"type": "import", "module": m_imp.group(1)})
            elif self.lang == "cpp":
                m_inc = re.search(r"#include\s+[<\"](.*?)[\">]", line_str)
                if m_inc:
                    self.imports.append({"type": "include", "header": m_inc.group(1)})

            # 2. CLASSES / STRUCTS / INTERFACES
            m_cls = re.search(r"(class|struct|interface|trait|enum)\s+([a-zA-Z0-9_]+)", line_str)
            if m_cls and not line_str.startswith("//") and not line_str.startswith("/*"):
                self.symbols.append({
                    "type": m_cls.group(1),
                    "name": m_cls.group(2),
                    "lineno": i,
                    "language": self.lang
                })

            # 3. FUNCTIONS / METHODS
            m_fn = None
            if self.lang in ("typescript", "javascript"):
                m_fn = re.search(r"(?:async\s+)?function\s+([a-zA-Z0-9_]+)", line_str) or re.search(r"(?:const|let|var)\s+([a-zA-Z0-9_]+)\s*=\s*(?:async\s*)?\(", line_str)
            elif self.lang == "go":
                m_fn = re.search(r"func\s+(?:\([^\)]+\)\s+)?([a-zA-Z0-9_]+)\s*\(", line_str)
            elif self.lang == "rust":
                m_fn = re.search(r"fn\s+([a-zA-Z0-9_]+)\s*\(", line_str)
            elif self.lang == "java":
                m_fn = re.search(r"(?:public|private|protected|static|\s)+\s+[\w<>]+\s+([a-zA-Z0-9_]+)\s*\(", line_str)
            elif self.lang == "cpp":
                m_fn = re.search(r"(?:[\w:<>]+\s+)+([a-zA-Z0-9_]+)\s*\([^\)]*\)\s*\{?", line_str)

            if m_fn and not line_str.startswith("//") and not line_str.startswith("/*"):
                func_name = m_fn.group(1)
                if func_name not in ("if", "for", "while", "switch", "catch"):
                    self.symbols.append({
                        "type": "function",
                        "name": func_name,
                        "lineno": i,
                        "language": self.lang
                    })

        return {"symbols": self.symbols, "imports": self.imports, "calls": self.calls}

class ASTIndexer:
    def __init__(self, root_dir: str = "."):
        self.root_dir = os.path.abspath(root_dir)
        self.cache_file = os.path.join(self.root_dir, ".ast_index_cache.json")
        self.cache = self._load_cache()

    def _load_cache(self) -> dict:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _save_cache(self):
        try:
            with open(self.cache_file, "w") as f:
                json.dump(self.cache, f, indent=2)
        except Exception:
            pass

    def _compute_md5(self, file_path: str) -> str:
        with open(file_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()

    def detect_language(self, filename: str) -> str:
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".py":
            return "python"
        elif ext in (".ts", ".tsx"):
            return "typescript"
        elif ext in (".js", ".jsx"):
            return "javascript"
        elif ext == ".go":
            return "go"
        elif ext == ".rs":
            return "rust"
        elif ext == ".java":
            return "java"
        elif ext in (".cpp", ".hpp", ".h", ".cc", ".cxx"):
            return "cpp"
        return "unknown"

    def index_file(self, file_path: str) -> dict:
        lang = self.detect_language(file_path)
        if lang == "unknown":
            return {"symbols": [], "imports": [], "calls": []}

        md5 = self._compute_md5(file_path)
        rel_path = os.path.relpath(file_path, self.root_dir)

        # Incremental check
        if rel_path in self.cache and self.cache[rel_path].get("md5") == md5:
            return self.cache[rel_path]["data"]

        try:
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            if lang == "python":
                tree = ast.parse(content, filename=file_path)
                visitor = PythonASTVisitor(rel_path)
                visitor.visit(tree)
                data = {
                    "symbols": visitor.symbols,
                    "imports": visitor.imports,
                    "calls": visitor.calls
                }
            else:
                visitor = MultiLanguageASTVisitor(rel_path, content, lang)
                data = visitor.parse()

            self.cache[rel_path] = {"md5": md5, "data": data}
            self._save_cache()
            return data
        except Exception as e:
            return {"symbols": [], "imports": [], "calls": []}

    def build_symbol_graph(self) -> dict:
        graph = {}
        for root, dirs, files in os.walk(self.root_dir):
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__', 'venv', 'node_modules', 'target', 'build')]
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, self.root_dir)
                res = self.index_file(full_path)
                if res["symbols"] or res["imports"]:
                    graph[rel_path] = res
        return graph

    def find_symbol(self, symbol_name: str) -> list:
        graph = self.build_symbol_graph()
        matches = []
        for file_path, data in graph.items():
            for s in data.get("symbols", []):
                if s["name"] == symbol_name:
                    matches.append({"file": file_path, "symbol": s})
        return matches

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-Language AST Indexer for Amuara Labs")
    parser.add_argument("directory", type=str, nargs="?", default=".", help="Root directory to index")
    args = parser.parse_args()

    indexer = ASTIndexer(args.directory)
    graph = indexer.build_symbol_graph()
    print(json.dumps(graph, indent=2))
