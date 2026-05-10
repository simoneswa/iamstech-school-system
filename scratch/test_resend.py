import os
import sys

# Add the project directory to the path so we can import the modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import app
from email_service import send_email_wrapper

def run_test():
    with app.app_context():
        # Override the API key for testing if needed, but it should pick it up from the environment
        test_email = "test@example.com" # Replace with a real email if you want to test delivery to a real inbox
        
        print(f"Testing Resend integration...")
        print(f"RESEND_API_KEY is {'SET' if os.environ.get('RESEND_API_KEY') else 'NOT SET'}")
        
        success = send_email_wrapper(
            subject="Test Resend Integration",
            recipients=[test_email],
            text_body="This is a test email sent via Resend from IAMSTECH.",
            html_body="<h1>This is a test email sent via Resend from IAMSTECH.</h1><p>If you see this, the integration works!</p>",
            otp_code="123456"
        )
        
        if success:
            print("Test email dispatched successfully. Check your console logs for actual delivery status.")
        else:
            print("Test email failed to dispatch.")

if __name__ == "__main__":
    run_test()
