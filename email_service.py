import threading
import os
import socket
from flask import current_app, request as flask_request
from flask_mail import Mail, Message
from flask import url_for

import resend

# Set a global timeout for socket operations to prevent SMTP hangs
socket.setdefaulttimeout(15)

mail = Mail()

# Initialize Resend
resend.api_key = os.environ.get("RESEND_API_KEY")

def send_async_email(app, msg, user_id=None, otp_code=None):
    with app.app_context():
        try:
            # 1. Immediate Log for Admin Visibility (Visible in Railway)
            print("\n" + "="*50)
            print(f"[EMAIL SYSTEM] Dispatching to: {msg.recipients}")
            if otp_code:
                print(f"[OTP STATUS]\nApplicant: {msg.recipients[0]}\nOTP: {otp_code}\nDelivery Method: ATTEMPTING")
            print("="*50 + "\n")

            email_sent_successfully = False
            
            # 2. Try Resend First (Production Preferred)
            if resend.api_key:
                try:
                    params = {
                        "from": msg.sender or "IamsTech <noreply@iamstech.com>",
                        "to": msg.recipients,
                        "subject": msg.subject,
                        "html": msg.html,
                        "text": msg.body
                    }
                    resend.Emails.send(params)
                    print(f"INFO: [RESEND] Delivery SUCCESS for {msg.recipients}")
                    email_sent_successfully = True
                except Exception as resend_error:
                    print(f"WARNING: [RESEND] Failed, falling back to SMTP. Error: {resend_error}")

            # 3. Fallback to SMTP (Flask-Mail)
            if not email_sent_successfully:
                mail.send(msg)
                print(f"INFO: [SMTP] Delivery SUCCESS for {msg.recipients}")
                email_sent_successfully = True
            
            if user_id and email_sent_successfully:
                from models import db, User
                user = db.session.get(User, user_id)
                if user and hasattr(user, 'otp_email_status'):
                    user.otp_email_status = 'sent'
                    db.session.commit()
        except Exception as e:
            print("\n" + "!"*50)
            print(f"[EMAIL FAILURE]\nApplicant: {msg.recipients[0]}\nOTP: {otp_code if otp_code else 'N/A'}\nReason: {str(e)}")
            print("!"*50 + "\n")
            
            if user_id:
                from models import db, User
                user = db.session.get(User, user_id)
                if user:
                    user.otp_email_status = 'failed'
                    db.session.commit()

def build_external_url(endpoint, **values):
    """
    Build an absolute URL for the given endpoint.
    Priority: live request host > IAMSTECH_BASE_URL env var > SERVER_NAME config.
    Using the live request host ensures links always point to the correct
    Railway domain even after renames or custom domain changes.
    """
    app = current_app._get_current_object()

    # 1. Best source: the actual host from the current HTTP request
    try:
        req = flask_request._get_current_object()
        scheme = req.scheme if req.scheme else 'https'
        # Honour X-Forwarded-Proto from Railway's proxy
        scheme = req.headers.get('X-Forwarded-Proto', scheme)
        host = req.headers.get('X-Forwarded-Host', req.host)
        path = url_for(endpoint, _external=False, **values)
        return f"{scheme}://{host}{path}"
    except RuntimeError:
        pass  # No active request context (e.g. background thread)

    # 2. Fallback: configured BASE_URL / IAMSTECH_BASE_URL env var
    base_url = app.config.get('BASE_URL') or os.environ.get('IAMSTECH_BASE_URL', '').strip()
    if base_url:
        base_url = base_url.strip().rstrip('/')
        if not base_url.startswith('http'):
            base_url = 'https://' + base_url
        path = url_for(endpoint, _external=False, **values)
        return base_url + path

    # 3. Last resort: Flask's built-in external URL (requires SERVER_NAME)
    return url_for(endpoint, _external=True, **values)


def send_email_wrapper(subject, recipients, text_body, html_body, user_id=None, otp_code=None):
    """
    Core wrapper for sending emails asynchronously.
    """
    try:
        app = current_app._get_current_object()
        
        # Respect SAFE_MODE globally
        is_safe_mode = os.environ.get('IAMSTECH_REG_SAFE_MODE', '').lower() == 'true'
        if is_safe_mode:
            print(f"INFO: [SAFE_MODE] Skipping email dispatch to {recipients} (OTP: {otp_code})")
            return True

        sender_email = app.config.get("MAIL_DEFAULT_SENDER") or app.config.get("MAIL_USERNAME") or os.environ.get('MAIL_DEFAULT_SENDER')
        msg = Message(subject=subject, sender=sender_email, recipients=recipients)
        msg.body = text_body
        msg.html = html_body
        
        # Start background thread
        threading.Thread(target=send_async_email, args=(app, msg, user_id, otp_code)).start()
        return True
    except Exception as e:
        print(f"ERROR: Failed to initiate async email: {e}")
        return False

def send_approval_email(user):
    """
    Sends an official welcome email to the approved user with their setup link.
    """
    setup_link = build_external_url('setup_account', token=user.setup_token)
    subject = f"Welcome to IAMSTECH LIBERIA - Your {user.role} Credentials"
    
    text_body = f"""
Dear {user.name},

Congratulations! Your application to the Institute of Advanced Management Science & Technology (IAMSTECH) LIBERIA has been approved for the role of {user.role}.

Your official institutional credentials have been generated.

--------------------------------------------------
APPROVAL STATUS: CONFIRMED
INSTITUTIONAL ID: {user.student_id}
INSTITUTIONAL EMAIL: {user.school_email}
--------------------------------------------------

To complete your registration, please set up your secure password using the link below:
{setup_link}

Once your password is set, you can log in using either your Institutional ID or Institutional Email.
This setup link is valid for 72 hours. Do not share this link with anyone.

Welcome to the future of technology and management.

Best Regards,
IAMSTECH LIBERIA Administration
"Shaping Tomorrow’s Leaders Through Technology"
    """
    
    html_body = render_approval_html(user, setup_link)
    return send_email_wrapper(subject, [user.email], text_body, html_body)

def render_approval_html(user, setup_link):
    return f"""
    <div style="font-family: 'Inter', sans-serif; max-width: 600px; margin: auto; border: 1px solid #eee; border-radius: 10px; overflow: hidden; box-shadow: 0 5px 15px rgba(0,0,0,0.05);">
        <div style="background: #0d1b3e; color: white; padding: 30px; text-align: center;">
            <h1 style="margin: 0; font-size: 24px;">Welcome to IAMSTECH</h1>
            <p style="margin: 5px 0 0; opacity: 0.8;">Shaping Tomorrow’s Leaders Through Technology</p>
        </div>
        <div style="padding: 40px; color: #333; line-height: 1.6;">
            <p>Dear <strong>{user.name}</strong>,</p>
            <p>Congratulations! Your application has been <strong>Approved</strong>. You are now officially recognized as a <strong>{user.role}</strong> at IAMSTECH LIBERIA.</p>
            
            <div style="background: #fdfbf7; border-left: 5px solid #ff6f00; padding: 20px; margin: 25px 0;">
                <p style="margin: 0 0 10px;"><strong>Approval Status:</strong> <span style="color: green; font-weight: bold;">CONFIRMED</span></p>
                <p style="margin: 0 0 10px;"><strong>Institutional ID:</strong> <span style="color: #ff6f00; font-weight: bold;">{user.student_id}</span></p>
                <p style="margin: 0 0 10px;"><strong>Institutional Email:</strong> <span style="font-weight: bold;">{user.school_email}</span></p>
            </div>
            
            <p style="text-align: center; margin-top: 30px;">
                <a href="{setup_link}" style="background: #ff6f00; color: white; padding: 15px 35px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">Setup Secure Account</a>
            </p>
            
            <p style="text-align: center; margin-top: 15px;">
                <small>Once setup is complete, you can <a href="{build_external_url('login')}">log in to the portal here</a>.</small>
            </p>
            
            <p style="font-size: 12px; color: #888; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px;">
                * This setup link is valid for 72 hours. Do not share this link with anyone for your own security.
            </p>
        </div>
        <div style="background: #f8f9fa; padding: 20px; text-align: center; font-size: 11px; color: #999;">
            &copy; 2026 IAMSTECH LIBERIA. Hotel Africa Road, Monrovia.
        </div>
    </div>
    """

def send_reset_email(user):
    """
    Sends a password reset email with OTP or link.
    """
    if len(user.reset_token) == 6:
        # OTP mode
        subject = "IAMSTECH LIBERIA - Password Reset OTP"
        text_body = f"""
Dear {user.name},

Your password reset OTP is: {user.reset_token}

This OTP is valid for 15 minutes.

Please use it to reset your password on the website.

Best Regards,
IAMSTECH Technical Support
        """
        html_body = f"""
    <div style="font-family: 'Inter', sans-serif; max-width: 600px; margin: auto; border: 1px solid #eee; border-radius: 10px; overflow: hidden; box-shadow: 0 5px 15px rgba(0,0,0,0.05);">
        <div style="background: #0d1b3e; color: white; padding: 30px; text-align: center;">
            <h1 style="margin: 0; font-size: 24px;">Password Reset OTP</h1>
        </div>
        <div style="padding: 40px; color: #333; line-height: 1.6;">
            <p>Dear <strong>{user.name}</strong>,</p>
            <p>You requested to reset your password for your IAMSTECH <strong>{user.role}</strong> account.</p>
            <p style="text-align: center; margin: 30px 0; font-size: 24px; font-weight: bold; color: #ff6f00;">{user.reset_token}</p>
            <p>This OTP is valid for 15 minutes.</p>
            <p style="font-size: 12px; color: #888; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px;">
                * If you did not make this request, you can safely ignore this email.
            </p>
        </div>
        <div style="background: #f8f9fa; padding: 20px; text-align: center; font-size: 11px; color: #999;">
            &copy; 2026 IAMSTECH LIBERIA. Hotel Africa Road, Monrovia.
        </div>
    </div>
        """
    else:
        # Link mode
        reset_link = build_external_url('reset_password', token=user.reset_token)
        subject = "IAMSTECH LIBERIA - Password Reset Request"
        text_body = f"""
Dear {user.name},

You recently requested to reset your password for your IAMSTECH account.

Please use the link below to securely reset your password:
{reset_link}

This link is valid for 1 hour. If you did not request this, please ignore this email.

Best Regards,
IAMSTECH Technical Support
        """
        html_body = f"""
    <div style="font-family: 'Inter', sans-serif; max-width: 600px; margin: auto; border: 1px solid #eee; border-radius: 10px; overflow: hidden; box-shadow: 0 5px 15px rgba(0,0,0,0.05);">
        <div style="background: #0d1b3e; color: white; padding: 30px; text-align: center;">
            <h1 style="margin: 0; font-size: 24px;">Password Reset Request</h1>
        </div>
        <div style="padding: 40px; color: #333; line-height: 1.6;">
            <p>Dear <strong>{user.name}</strong>,</p>
            <p>You requested to reset your password for your IAMSTECH <strong>{user.role}</strong> account.</p>
            <p style="text-align: center; margin-top: 30px;">
                <a href="{reset_link}" style="background: #ff6f00; color: white; padding: 15px 35px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">Reset Password</a>
            </p>
            <p style="font-size: 12px; color: #888; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px;">
                * This link is valid for 1 hour. If you did not make this request, you can safely ignore this email.
            </p>
        </div>
        <div style="background: #f8f9fa; padding: 20px; text-align: center; font-size: 11px; color: #999;">
            &copy; 2026 IAMSTECH LIBERIA. Hotel Africa Road, Monrovia.
        </div>
    </div>
        """
    return send_email_wrapper(subject, [user.email], text_body, html_body)

def send_verification_otp(user, code):
    """
    Sends a 6-digit verification code to the user's personal email.
    """
    if os.environ.get('IAMSTECH_REG_SAFE_MODE', '').lower() == 'true':
        print(f"INFO: [SAFE_MODE] Skipping OTP email dispatch for {user.email}")
        return True

    subject = "Verify Your IAMSTECH Account"
    text_body = f"""
Dear {user.name},

Thank you for applying to IAMSTECH LIBERIA.

To verify your personal email address and proceed with your application, please enter the following 6-digit code on the verification screen:

--------------------------------------------------
VERIFICATION CODE: {code}
--------------------------------------------------

This code is valid for 15 minutes. 

If you did not request this, please ignore this email.

Best Regards,
IAMSTECH Admissions Team
    """
    
    html_body = f"""
    <div style="font-family: 'Inter', sans-serif; max-width: 600px; margin: auto; border: 1px solid #eee; border-radius: 10px; overflow: hidden; box-shadow: 0 5px 15px rgba(0,0,0,0.05);">
        <div style="background: #0d1b3e; color: white; padding: 30px; text-align: center;">
            <h1 style="margin: 0; font-size: 24px;">Verify Your Identity</h1>
        </div>
        <div style="padding: 40px; color: #333; line-height: 1.6; text-align: center;">
            <p>Dear <strong>{user.name}</strong>,</p>
            <p>Use the code below to verify your personal email and continue your enrollment.</p>
            <div style="background: #fdfbf7; border: 2px dashed #ff6f00; padding: 20px; margin: 25px 0; font-size: 32px; font-weight: bold; letter-spacing: 5px; color: #ff6f00;">
                {code}
            </div>
            <p style="font-size: 12px; color: #888; margin-top: 40px; border-top: 1px solid #eee; padding-top: 20px;">
                * This code is valid for 15 minutes. If you did not make this request, you can safely ignore this email.
            </p>
        </div>
        <div style="background: #f8f9fa; padding: 20px; text-align: center; font-size: 11px; color: #999;">
            &copy; 2026 IAMSTECH LIBERIA. Hotel Africa Road, Monrovia.
        </div>
    </div>
    """
    return send_email_wrapper(subject, [user.email], text_body, html_body, user_id=user.id, otp_code=code)
