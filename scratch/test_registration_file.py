import requests

url = 'https://web-production-bcc4d.up.railway.app/register'
data = {
    'name': 'File Upload Agent',
    'email': 'file.agent@example.com',
    'phone': '0987654321',
    'department': 'Computer Hardware'
}
files = {
    'profile_photo': ('test_image.jpg', b'fake image data', 'image/jpeg')
}

response = requests.post(url, data=data, files=files)
print("Status Code:", response.status_code)
with open('response_file.html', 'w', encoding='utf-8') as f:
    f.write(response.text)
print("Wrote response to response_file.html")
