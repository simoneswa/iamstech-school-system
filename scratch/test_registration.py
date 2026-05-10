import requests

data = {
    'name': 'Test Registration Agent',
    'email': 'test.agent.500@example.com',
    'phone': '1234567890',
    'department': 'Computer Science'
}

response = requests.post('https://web-production-bcc4d.up.railway.app/register', data=data)
print("Status Code:", response.status_code)
print("Headers:", response.headers)
with open('response.html', 'w', encoding='utf-8') as f:
    f.write(response.text)
print("Wrote response to response.html")
