from flask import Flask, render_template_string
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader('templates'))
template = env.get_template('dashboards/student.html')

class DummyUser:
    name = "John Doe"
    role = "Student"
    student_id = "STU123"
    department = "CS"
    school_email = "john@iamstech.com"
    email = "john@gmail.com"
    points = 100

try:
    print(template.render(
        current_user=DummyUser(),
        user_role="Student",
        brand_logo_path="img/logo.png",
        enrollments=[],
        att_percent=0.0,
        assignments=[],
        notifications=[],
        my_rank=1,
        announcements=[],
        meetings=[],
        url_for=lambda endpoint, **kwargs: f"/{endpoint}",
        media_url=lambda path, default: path or default,
        get_flashed_messages=lambda with_categories=False: []
    ))
    print("Render successful with all variables!")
except Exception as e:
    print("Render failed:", e)

# Now test what happens if 'notifications' is omitted
try:
    print(template.render(
        current_user=DummyUser(),
        user_role="Student",
        brand_logo_path="img/logo.png",
        enrollments=[],
        att_percent=0.0,
        assignments=[],
        # omit notifications
        my_rank=1,
        announcements=[],
        meetings=[],
        url_for=lambda endpoint, **kwargs: f"/{endpoint}",
        media_url=lambda path, default: path or default,
        get_flashed_messages=lambda with_categories=False: []
    ))
    print("Render successful without notifications!")
except Exception as e:
    print("Render failed without notifications:", type(e), e)
