#!/usr/bin/env python3
"""Quick-launch script — run NexusAI without installing."""
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from nexus.cli import main
main()
