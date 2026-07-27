from constraint_checker import ConstraintExtractor
from pipeline import CeilingNode

ceiling = CeilingNode(provider="manual")
ext = ConstraintExtractor(ceiling)
prompt = '''URGENT: production is down. the healthcheck endpoint in src/app.js is returning 500 because the db variable is undefined. wrap it in a try catch and return 200 with status: 'degraded' if it fails.'''

res = ext.extract(prompt)
print(res)
