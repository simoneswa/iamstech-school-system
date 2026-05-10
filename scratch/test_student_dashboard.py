from app import app, db
from models import User
from flask import url_for

with app.app_context():
    # Find a student or applicant to test
    student = User.query.filter(User.role.in_(['Student', 'Applicant'])).first()
    if student:
        print(f"Testing dashboard for {student.name} (Role: {student.role})")
        with app.test_client(user=student) as client:
            with client.session_transaction() as sess:
                sess['_user_id'] = str(student.id)
                sess['_fresh'] = True
            
            response = client.get('/dashboard')
            print(f"Status Code: {response.status_code}")
            if response.status_code == 500:
                print("500 Error occurred. Check the Flask logs.")
            else:
                print("Success! No 500 error.")
    else:
        print("No student or applicant found to test.")
