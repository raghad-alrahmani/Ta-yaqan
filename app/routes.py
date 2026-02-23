from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from app import db
from app.models import VerifierUser

from flask_mail import Message
from . import mail

import os, subprocess, uuid

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


@main.route("/about")
def about():
    return render_template("about.html")

@main.route("/upload")
def upload():
    return render_template("upload.html")

@main.route("/upload", methods=["GET"])
def upload():
    return render_template("upload.html")

@main.route("/upload/youtube", methods=["POST"])
def youtube_verify():
    youtube_url = request.form.get("youtube_url", "").strip()
    if not youtube_url:
        flash("الرجاء إدخال رابط يوتيوب", "error")
        return redirect(url_for("main.upload"))

    # فولدر حفظ الملفات داخل المشروع
    downloads_dir = os.path.join(current_app.root_path, "static", "uploads", "youtube")
    os.makedirs(downloads_dir, exist_ok=True)

    # اسم ملف فريد
    file_id = str(uuid.uuid4())
    output_template = os.path.join(downloads_dir, f"{file_id}.%(ext)s")
    output_mp3 = os.path.join(downloads_dir, f"{file_id}.mp3")

    try:
        # أهم شيء: yt-dlp + ffmpeg
        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", output_template,
            youtube_url
        ]
        subprocess.run(cmd, check=True)

    except subprocess.CalledProcessError:
        flash("صار خطأ أثناء تحميل/تحويل اليوتيوب. تأكدي من ffmpeg و yt-dlp.", "error")
        return redirect(url_for("main.upload"))

    # هنا: output_mp3 صار موجود
    # ✅ الخطوة الجاية: نحفظ مساره بالـDB (بنفس جدول recitations عندكم)
    # مثال (عدليه حسب موديلكم):
    # rec = Recitation(user_id=session["user_id"], source="youtube", file_path=f"uploads/youtube/{file_id}.mp3")
    # db.session.add(rec); db.session.commit()

    flash("تم تحميل الصوت من اليوتيوب بنجاح ✅", "success")
    return redirect(url_for("main.upload"))

@main.route("/add-test")
def add_test():
    email = "test@tayaqan.com"

    existing = VerifierUser.query.filter_by(verifieremail=email).first()
    if existing:
        return "Already exists ✅"

    user = VerifierUser(
        verifiername="Test User",
        verifieremail=email,
        verifierpassword="123"
    )
    db.session.add(user)
    db.session.commit()
    return "Inserted ✅"