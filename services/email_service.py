import smtplib
from email.message import EmailMessage
from flask import current_app


def send_otp_email(recipient, code, purpose):
    config = current_app.config
    host = config.get('SMTP_HOST')
    username = config.get('SMTP_USERNAME')
    password = config.get('SMTP_PASSWORD')
    sender = config.get('SMTP_FROM') or username
    if not all([host, username, password, sender]):
        return False, 'Email delivery is not configured. Ask the hostel administrator to configure SMTP.'

    message = EmailMessage()
    message['Subject'] = 'Your Abode verification code'
    message['From'] = sender
    message['To'] = recipient
    message.set_content(
        f'Your Abode {purpose.replace("_", " ")} verification code is {code}. '
        'It expires in 10 minutes and can be used only once.'
    )

    try:
        port = int(config.get('SMTP_PORT', 587))
        with smtplib.SMTP(host, port, timeout=15) as client:
            if config.get('SMTP_USE_TLS', True):
                client.starttls()
            client.login(username, password)
            client.send_message(message)
        return True, None
    except (OSError, smtplib.SMTPException) as error:
        current_app.logger.exception('Unable to send OTP email')
        return False, f'Unable to send the email: {error}'
