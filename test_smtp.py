import smtplib
import os
import sys
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def test_smtp_config(server_addr, port, username, password, use_ssl=False):
    print(f"\n--- Testing {'SSL (465)' if use_ssl else 'TLS (587)'} ---")
    print(f"Target: {server_addr}:{port}")
    
    msg = MIMEMultipart()
    msg['From'] = username
    msg['To'] = username
    msg['Subject'] = f"SMTP Test ({'SSL' if use_ssl else 'TLS'})"
    msg.attach(MIMEText("Diagnostic test.", 'plain'))

    try:
        if use_ssl:
            server = smtplib.SMTP_SSL(server_addr, port, timeout=10)
        else:
            server = smtplib.SMTP(server_addr, port, timeout=10)
            server.starttls()
            
        server.login(username, password)
        server.send_message(msg)
        server.quit()
        print(f"SUCCESS: Authentication and sending worked on port {port}!")
        return True
    except smtplib.SMTPAuthenticationError:
        print(f"FAILED: Authentication rejected. The password or email is incorrect.")
    except Exception as e:
        print(f"FAILED: Error: {e}")
    return False

if __name__ == "__main__":
    username = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    
    if not username or not password:
        print("ERROR: Set MAIL_USERNAME and MAIL_PASSWORD env vars.")
        sys.exit(1)

    # Test 1: Port 465 (SSL) - Now our primary recommendation
    success = test_smtp_config('smtp.gmail.com', 465, username, password, use_ssl=True)
    
    # Test 2: Port 587 (TLS) - Fallback
    if not success:
        test_smtp_config('smtp.gmail.com', 587, username, password, use_ssl=False)
