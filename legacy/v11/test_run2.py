import sys
from constraint_checker import ConstraintVerifier, ConstraintExtractor, LiteralConstraint
from output_parser import FileAction

prompt = "URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails."

class DummyNode:
    client = "manual"

extractor = ConstraintExtractor(DummyNode())
verifier = ConstraintVerifier(DummyNode())

constraints = extractor.extract(prompt)
print(f"Extracted constraints: {[c.value for c in constraints]}")

# Run 2 Output (which hallucinated 500 in catch block)
code = """
const express = require('express');
const db = require('./db'); // Import the database module

const app = express();
app.use(express.json());

app.get('/healthcheck', async (req, res) => {
  try {
    await db.authenticate(); // Attempt to authenticate with the database
    return res.status(200).json({ status: 'healthy' });
  } catch (error) {
    console.error('Database connection failed:', error);
    return res.status(500).json({ status: 'degraded', message: 'Failed to connect to the database.' });
  }
});

app.listen(process.env.PORT || 3000, () => {
  console.log(`Server is running on port ${process.env.PORT}`);
});
"""

mock = FileAction(path="app.js", action="MODIFY", content=code)

print("\nTesting Run 2 output:")
passed, reason = verifier.verify(constraints, [mock])
print(f"Passed: {passed}\nReason: {reason}")
