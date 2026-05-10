import re
with open('response.html', encoding='utf-8') as f:
    html = f.read()
alerts = re.findall(r'<div[^>]*class=[\'"][^\'"]*alert[^\'"]*[\'"][^>]*>(.*?)</div>', html, re.DOTALL)
print("Alerts:")
for a in alerts:
    print(re.sub('<[^<]+?>', '', a).strip())
