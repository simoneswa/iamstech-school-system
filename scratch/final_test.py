import json, sys
from app import app, db, User
from werkzeug.security import generate_password_hash

app.config['TESTING'] = True
app.secret_key = 'test'

print('=== IAMSTECH SYSTEM DIAGNOSTICS ===')
print()

with app.test_client() as client:

    # TEST 1: SuperAdmin Login
    r = client.post('/login', data={'email': 'simoneswaraykeepitup@founder', 'password': '2026Capt132005@'}, follow_redirects=True)
    sa_ok = 'SuperAdmin Enterprise Control' in r.data.decode()
    print('[1] SuperAdmin Login:     {} (HTTP {})'.format('PASS' if sa_ok else 'FAIL', r.status_code))

    # TEST 2: Admin Login (the bug that was crashing with 500 error)
    r = client.post('/login', data={'email': 'admin@test.com', 'password': 'password'}, follow_redirects=True)
    body = r.data.decode()
    admin_ok = 'Admin Control Center' in body
    print('[2] Admin Login:          {} (HTTP {})'.format('PASS' if admin_ok else 'FAIL', r.status_code))
    if not admin_ok:
        print('   ERROR details:', body[:300])

    # TEST 3: Chatbot endpoint with greeting
    r = client.post('/chatbot', data=json.dumps({'message': 'hello'}), content_type='application/json')
    chat_data = json.loads(r.data) if r.status_code == 200 else {}
    chat_ok = r.status_code == 200 and 'response' in chat_data
    chat_resp = chat_data.get('response', 'N/A')
    print('[3] Chatbot (greeting):   {} (HTTP {})'.format('PASS' if chat_ok else 'FAIL', r.status_code))
    print('    Bot says: "{}"'.format(chat_resp))

    # TEST 4: Chatbot with program question
    r = client.post('/chatbot', data=json.dumps({'message': 'what programs do you offer?'}), content_type='application/json')
    chat2_data = json.loads(r.data) if r.status_code == 200 else {}
    chat2_ok = r.status_code == 200
    print('[4] Chatbot (programs):   {} (HTTP {})'.format('PASS' if chat2_ok else 'FAIL', r.status_code))
    if chat2_ok:
        print('    Bot says: "{}"'.format(chat2_data.get('response', '')))

    # TEST 5: Chatbot with location question
    r = client.post('/chatbot', data=json.dumps({'message': 'where are you located?'}), content_type='application/json')
    chat3_ok = r.status_code == 200
    chat3_data = json.loads(r.data) if chat3_ok else {}
    print('[5] Chatbot (location):   {} (HTTP {})'.format('PASS' if chat3_ok else 'FAIL', r.status_code))
    if chat3_ok:
        print('    Bot says: "{}"'.format(chat3_data.get('response', '')))

    # TEST 6: Login page GET
    r = client.get('/login')
    login_ok = r.status_code == 200
    print('[6] Login Page GET:        {} (HTTP {})'.format('PASS' if login_ok else 'FAIL', r.status_code))

    print()
    all_pass = sa_ok and admin_ok and chat_ok and chat2_ok and chat3_ok and login_ok
    print('=== RESULT: {} ==='.format('ALL TESTS PASSED' if all_pass else 'SOME TESTS FAILED'))
