import re
try:
    text = open('out2.txt', 'rb').read().decode('utf-16le', errors='ignore')
    match = re.search(r'<div class="alert alert-danger">(.*?)</div>', text, re.DOTALL)
    print(match.group(1).strip() if match else 'No error found')
except Exception as e:
    print('Failed:', e)
