
import requests
import uuid

url = "http://127.0.0.1:8080/register"
email = f"test_{uuid.uuid4().hex[:6]}@example.com"
data = {
    "name": "Test Applicant",
    "email": email,
    "phone": "123456789",
    "department": "Information Technology"
}

# Simulate file upload
files = {
    'profile_photo': ('test.jpg', b'fake-image-content', 'image/jpeg')
}

print(f"Attempting registration for {email}...")
try:
    response = requests.post(url, data=data, files=files, timeout=10)
    print(f"Status Code: {response.status_code}")
    if response.status_code == 500:
        print("FAIL: Received 500 Internal Server Error")
    else:
        print("Success or other status.")
except Exception as e:
    print(f"Error: {e}")
