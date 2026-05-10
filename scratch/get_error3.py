import re
with open('out3.html', 'r', encoding='utf-8') as f:
    html = f.read()
m = re.search(r'<div class="alert alert-danger">(.*?)</div>', html)
print(m.group(1) if m else 'not found')
