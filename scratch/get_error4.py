import re
try:
    text = open('out4.txt', 'rb').read().decode('utf-16le', errors='ignore')
    match_type = re.search(r'<strong>Type:</strong>(.*?)<br>', text)
    match_error = re.search(r'<strong>Error:</strong>(.*?)</div>', text, re.DOTALL)
    if match_type:
        print("TYPE:", match_type.group(1).strip())
    else:
        print("Type not found")
        
    if match_error:
        print("ERROR:", match_error.group(1).strip())
    else:
        print("Error not found")
except Exception as e:
    print('Failed:', e)
