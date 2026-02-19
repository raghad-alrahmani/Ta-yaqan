from flask import Blueprint, render_template
from app import db
from app.models import VerifierUser

import os
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_mail import Message
from . import mail


main = Blueprint("main", __name__)

@main.route("/")
def home():

return render_template("landing.html")





@main.route("/contact", methods=["GET", "POST"])
def contact():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        subject = request.form.get("subject", "").strip()
        message_text = request.form.get("message", "").strip()




try:
            receiver = os.getenv("CONTACT_RECEIVER") or os.getenv("MAIL_DEFAULT_SENDER")

            msg = Message(
                subject=f"[Ta'yaqan Contact] {subject}",
                recipients=[receiver],
                body=(
                    f"Name: {name}\n"
                    f"Email: {email}\n"
                    f"Subject: {subject}\n\n"
                    f"Message:\n{message_text}\n"
                ),
                reply_to=email if email else None
            )
            mail.send(msg)

            # ✅ نخلي النجاح يظهر مرة واحدة بعد التحويل
            flash("تم إرسال رسالتك بنجاح ✅", "success")
            return redirect(url_for("main.contact"))

except Exception as e:
            flash(f"تعذر إرسال الرسالة ❌ — {str(e)}", "error")
            return redirect(url_for("main.contact"))

    # GET
return render_template("contact.html")

