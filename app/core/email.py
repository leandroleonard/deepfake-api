import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings

logger = logging.getLogger(__name__)


def send_reset_email(to_email: str, reset_link: str) -> None:
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Recuperação de senha — Deepfake Detector"
    msg["From"]    = settings.SMTP_FROM
    msg["To"]      = to_email

    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; background: #f4f4f4; padding: 30px;">
        <div style="max-width: 480px; margin: auto; background: white; border-radius: 8px; padding: 32px;">
          <h2 style="color: #111;">Recuperação de senha</h2>
          <p>Recebemos um pedido para redefinir a senha da sua conta.</p>
          <p>Clique no botão abaixo para criar uma nova senha. O link expira em <strong>30 minutos</strong>.</p>
          <a href="{reset_link}"
             style="display:inline-block; margin-top:16px; padding:12px 24px;
                    background:#2563eb; color:white; border-radius:6px;
                    text-decoration:none; font-weight:bold;">
            Redefinir senha
          </a>
          <p style="margin-top:24px; color:#888; font-size:12px;">
            Se não solicitaste esta recuperação, ignora este email.
          </p>
        </div>
      </body>
    </html>
    """

    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_FROM, to_email, msg.as_string())
        logger.info(f"[Email] Reset email enviado para {to_email}")
    except Exception as e:
        logger.error(f"[Email] Falha ao enviar email: {e}")
        raise