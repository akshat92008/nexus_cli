import re
import sys

for filename in sys.argv[1:]:
    with open(filename) as f:
        lines = f.readlines()
    
    out = []
    for i, line in enumerate(lines):
        # We know we deleted try: which was at 4 spaces.
        # The body was at 8 spaces, and we want to change it to 4 spaces.
        # Anything at 12 spaces goes to 8 spaces, etc.
        # But wait! A test might have other blocks at 8 spaces!
        # Let's just catch IndentationError using compile() and fix it iteratively?
        pass

