import re

patch = """<<<<<<<
router.post('/payment', (req, res) => {
=======
router.post('/payment', (req, res) => {
>>>>>>>"""

pattern = re.compile(r'<+\n(.*?)\n=+\n(.*?)\n>+', re.DOTALL)
matches = pattern.findall(patch)
print(matches)
