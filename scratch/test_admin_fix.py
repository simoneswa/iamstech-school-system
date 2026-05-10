"""
Targeted test: Admin approval lifecycle + leaderboard exclusion
Tests ONLY Admin login path without touching SuperAdmin or Student flows.
"""
import sys, json, uuid
sys.path.insert(0, '.')

from app import app, db, User
from werkzeug.security import generate_password_hash

app.config['TESTING'] = True
app.secret_key = 'test'

PASS = '\033[92mPASS\033[0m'
FAIL = '\033[91mFAIL\033[0m'
results = []

def check(label, condition, detail=''):
    status = PASS if condition else FAIL
    print(f'  [{("PASS" if condition else "FAIL")}] {label}')
    if not condition and detail:
        print(f'         Detail: {detail}')
    results.append(condition)

print('\n=== TARGETED ADMIN LOGIN + LEADERBOARD FIX TEST ===\n')

# --- Setup: create a fresh Admin user in approved state (simulating post-setup_account) ---
with app.app_context():
    # Clean up any previous test admin
    existing = User.query.filter_by(email='fix_test_admin@test.com').first()
    if existing:
        db.session.delete(existing)
        db.session.commit()

    # Create Admin exactly as approve_user + setup_account would leave them
    admin = User(
        name='Fix Test Admin',
        email='fix_test_admin@test.com',
        password=generate_password_hash('AdminPass123'),
        role='Admin',
        registration_state='approved',
        is_email_verified=True,   # This is what the fix adds
        must_change_password=False,
        setup_token=None,
        status='Approved',
        is_superadmin=False
    )
    db.session.add(admin)

    # Create a student with points
    existing_s = User.query.filter_by(email='fix_test_student@test.com').first()
    if existing_s:
        db.session.delete(existing_s)
    student = User(
        name='Fix Test Student',
        email='fix_test_student@test.com',
        password=generate_password_hash('pass'),
        role='Student',
        registration_state='approved',
        is_email_verified=True,
        must_change_password=False,
        status='Approved',
        is_superadmin=False,
        points=500
    )
    db.session.add(student)
    db.session.commit()
    admin_email = admin.email

print('--- Test 1: Admin Login Flow ---')
with app.test_client() as client:
    resp = client.post('/login',
        data={'email': 'fix_test_admin@test.com', 'password': 'AdminPass123'},
        follow_redirects=True)
    body = resp.data.decode('utf-8')
    check('Admin login returns HTTP 200', resp.status_code == 200,
          f'Got HTTP {resp.status_code}')
    check('Admin Control Center dashboard loads', 'Admin Control Center' in body,
          body[:300] if 'Admin Control Center' not in body else '')
    check('No 500 error page shown', 'System Error' not in body and 'Internal Server Error' not in body)
    check('No verify_email redirect', 'verify_email' not in resp.headers.get('Location', ''))

print('\n--- Test 2: Leaderboard Exclusion ---')
with app.test_client() as client:
    # Login as student to see their dashboard/leaderboard
    resp = client.post('/login',
        data={'email': 'fix_test_student@test.com', 'password': 'pass'},
        follow_redirects=True)
    body = resp.data.decode('utf-8')
    check('Student login succeeds', resp.status_code == 200)
    check('Student dashboard loads', 'leaderboard' in body.lower() or 'rank' in body.lower() or 'xp' in body.lower())
    # Admin name should NOT appear in leaderboard section
    check('Admin NOT in leaderboard', 'Fix Test Admin' not in body)

print('\n--- Test 3: SuperAdmin + Student flows untouched ---')
with app.test_client() as client:
    resp = client.post('/login',
        data={'email': 'simoneswaraykeepitup@founder', 'password': '2026Capt132005@'},
        follow_redirects=True)
    check('SuperAdmin login still works', 'SuperAdmin Enterprise Control' in resp.data.decode())

print()
passed = sum(results)
total = len(results)
print(f'=== RESULT: {passed}/{total} tests passed {"✓ ALL CLEAR" if passed == total else "✗ FAILURES DETECTED"} ===\n')

# Cleanup
with app.app_context():
    for email in ['fix_test_admin@test.com', 'fix_test_student@test.com']:
        u = User.query.filter_by(email=email).first()
        if u:
            db.session.delete(u)
    db.session.commit()
print('Test data cleaned up.')
