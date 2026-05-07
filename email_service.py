import os
from flask_mail import Mail, Message
from flask import url_for

mail = Mail()

def send_approval_email(user):
    """
    Sends an official welcome email to the approved user with their setup link.
    """
    try:
        msg = Message(
            subject=f"Welcome to IAMSTECH LIBERIA - Your {user.role} Credentials",
            sender=os.getenv("MAIL_USERNAME"),
            recipients=[user.email]
        )
        
        setup_link = url_for('setup_account', token=user.setup_token, _external=True)
        
        # Professional formatting for the email body
        msg.body = f"""
Dear {user.name},

Congratulations! Your application to the Institute of Advanced Management Science & Technology (IAMSTECH) LIBERIA has been approved for the role of {user.role}.

Your official institutional credentials have been generated.

--------------------------------------------------
INSTITUTIONAL ID: {user.student_id}
INSTITUTIONAL EMAIL: {user.school_email}
--------------------------------------------------

To complete your registration, please set up your secure password using the link below:
{setup_link}

This link is valid for 72 hours. Do not share this link with anyone.

Welcome to the future of technology and management.

Best Regards,
IAMSTECH LIBERIA Administration
"Shaping Tomorrow’s Leaders Through Technology"
        """
        
        msg.html = render_approval_html(user, setup_link)
        
        mail.send(msg)
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

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
                <p style="margin: 0 0 10px;"><strong>Institutional ID:</strong> <span style="color: #ff6f00;">{user.student_id}</span></p>
                <p style="margin: 0 0 10px;"><strong>Institutional Email:</strong> {user.school_email}</p>
            </div>
            
            <p style="text-align: center; margin-top: 30px;">
                <a href="{setup_link}" style="background: #ff6f00; color: white; padding: 15px 35px; text-decoration: none; border-radius: 8px; font-weight: bold; display: inline-block;">Setup Secure Account</a>
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
