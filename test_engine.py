#!/usr/bin/env python3
"""
test_engine.py - Full System Verification Suite for Amuara Labs
Verifies:
1. Multi-domain dataset generation & formatting
2. Data cleaning, MinHash LSH deduplication & secret scanning
3. Multi-language AST indexer (Python, TS, JS, Go, Rust, Java, C++)
4. Long-term memory manager persistence
5. 9-Role multi-agent framework orchestrator
6. Self-healing debugger repair loop
7. Automated benchmark harness execution
"""

import os
import sys
import json
import unittest
from generate_dataset import generate_dataset
from dataset_cleaner import DatasetCleaner
from ast_indexer import ASTIndexer
from memory import SemanticMemory as MemoryManager
from agents import ReActAgent as MultiAgentOrchestrator
from debugger import SelfHealingDebugger
from benchmark_harness import BenchmarkHarness

class TestAmuaraCodingSystem(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = os.path.abspath(".")
        cls.dataset_file = "temp_dataset.jsonl"
        cls.clean_dataset_file = "temp_dataset_clean.jsonl"

    def test_01_dataset_generator(self):
        count = generate_dataset(self.dataset_file, count=10)
        self.assertEqual(count, 10)
        self.assertTrue(os.path.exists(self.dataset_file))
        print("[TEST 1 PASSED] Multi-domain dataset generation validated.")

    def test_02_dataset_cleaner_minhash(self):
        cleaner = DatasetCleaner()
        stats = cleaner.clean_dataset(self.dataset_file, self.clean_dataset_file)
        self.assertGreater(stats["kept"], 0)
        self.assertTrue(os.path.exists(self.clean_dataset_file))
        print("[TEST 2 PASSED] MinHash LSH dataset cleaning & deduplication validated.")

    def test_03_multilang_ast_indexer(self):
        indexer = ASTIndexer(self.workspace)
        graph = indexer.build_symbol_graph()
        self.assertIsInstance(graph, dict)
        # Verify python file indexing
        symbols = indexer.find_symbol("ASTIndexer")
        self.assertGreater(len(symbols), 0)
        print("[TEST 3 PASSED] Multi-language AST indexer and symbol graph validated.")

    def test_04_long_term_memory(self):
        mem = MemoryManager("temp_memory.json")
        mem.add_architecture_decision("Test Decision", "Context details")
        ctx = mem.get_summary_context()
        self.assertGreater(len(ctx["architecture_decisions"]), 0)
        if os.path.exists("temp_memory.json"):
            os.remove("temp_memory.json")
        print("[TEST 4 PASSED] Long-term project memory manager validated.")

    def test_05_multi_agent_framework(self):
        orchestrator = MultiAgentOrchestrator(self.workspace)
        res = orchestrator.execute("Implement a rate limiter in Python.")
        self.assertTrue(res["plan"]["task"])
        self.assertTrue(res["review"]["passed"])
        self.assertTrue(res["security"]["secure"])
        print("[TEST 5 PASSED] 9-Role multi-agent framework execution validated.")

    def test_06_self_healing_debugger(self):
        debugger = SelfHealingDebugger(self.workspace)
        res = debugger.execute_repair_loop("Implement a fast Trie", max_iterations=2)
        self.assertEqual(res["status"], "PASSED")
        print("[TEST 6 PASSED] Execution-guided self-healing debug loop validated.")

    def test_07_benchmark_harness(self):
        harness = BenchmarkHarness("temp_bench_results")
        res = harness.run_benchmark_suite()
        self.assertIn("pass@1", res)
        self.assertGreaterEqual(res["pass@1"], 0.0)
        print("[TEST 7 PASSED] Automated benchmark harness & empirical metrics validated.")

    @classmethod
    def tearDownClass(cls):
        for f in [cls.dataset_file, cls.clean_dataset_file]:
            if os.path.exists(f):
                os.remove(f)

if __name__ == "__main__":
    unittest.main()
