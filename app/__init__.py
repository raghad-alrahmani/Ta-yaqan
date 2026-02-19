import os
from flask import Flask
from dotenv import load_dotenv
from flask_mail import Mail

mail = Mail()   # ← لازم يكون هنا خارج الدالة

def create_app():
    load_dotenv()

    app = Flask(__name__)

    # ✅ مهم عشان flash/session
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-key-change-me")

    # Mail Config
    app.config["MAIL_SERVER"] = os.getenv("MAIL_SERVER")
    app.config["MAIL_PORT"] = int(os.getenv("MAIL_PORT", "587"))
    app.config["MAIL_USE_TLS"] = os.getenv("MAIL_USE_TLS", "1") == "1"
    app.config["MAIL_USERNAME"] = os.getenv("MAIL_USERNAME")
    app.config["MAIL_PASSWORD"] = os.getenv("MAIL_PASSWORD")
    app.config["MAIL_DEFAULT_SENDER"] = os.getenv("MAIL_DEFAULT_SENDER")

    mail.init_app(app)

    from .routes import main
    app.register_blueprint(main)

    return app