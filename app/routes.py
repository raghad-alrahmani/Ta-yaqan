from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from werkzeug.utils import secure_filename
from app import db
from app.models import VerifierUser

from flask_mail import Message
from . import mail

import os, subprocess, uuid

main = Blueprint("main", __name__)

@main.route("/")
def home():
    # ✅ لو مسجل دخول: الرئيسية تكون لوحة المستخدم (/upload)
    if session.get("user_id"):
        return redirect(url_for("main.upload"))
    # ✅ لو مو مسجل: landing
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

            flash("تم إرسال رسالتك بنجاح ✅", "success")
            return redirect(url_for("main.contact"))

        except Exception as e:
            flash(f"تعذر إرسال الرسالة ❌ — {str(e)}", "error")
            return redirect(url_for("main.contact"))

    return render_template("contact.html")

@main.route("/about")
def about():
    return render_template("about.html")


@main.route("/upload", methods=["GET"])
def upload():
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))
    return render_template("upload.html")

# =========================
# ✅ (A) يوتيوب: زي ما هو عندك
# =========================
@main.route("/upload/youtube", methods=["POST"])
def youtube_verify():
    # 🔐 حماية: لازم يكون مسجل دخول
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

    youtube_url = request.form.get("youtube_url", "").strip()
    if not youtube_url:
        flash("الرجاء إدخال رابط يوتيوب", "error")
        return redirect(url_for("main.upload"))

    downloads_dir = os.path.join(current_app.root_path, "static", "uploads", "youtube")
    os.makedirs(downloads_dir, exist_ok=True)

    file_id = str(uuid.uuid4())
    output_template = os.path.join(downloads_dir, f"{file_id}.%(ext)s")

    try:
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

    flash("تم تحميل الصوت من اليوتيوب بنجاح ✅", "success")
    return redirect(url_for("main.upload"))

# =========================
# ✅ (B) رفع ملف + تحويله MP3 باستخدام ffmpeg (الجديد)
# =========================
@main.route("/upload/file", methods=["POST"])
def file_verify():
    # 🔐 حماية: لازم يكون مسجل دخول
    if not session.get("user_id"):
        return redirect(url_for("auth.login"))

    f = request.files.get("recitation_file")
    if not f or f.filename.strip() == "":
        flash("رجاءً اختاري ملف أولاً ❌", "error")
        return redirect(url_for("main.upload"))

    uploads_dir = os.path.join(current_app.root_path, "static", "uploads", "files")
    os.makedirs(uploads_dir, exist_ok=True)

    file_id = str(uuid.uuid4())
    original_name = secure_filename(f.filename)
    ext = os.path.splitext(original_name)[1].lower()

    saved_path = os.path.join(uploads_dir, f"{file_id}{ext}")
    f.save(saved_path)

    mp3_path = os.path.join(uploads_dir, f"{file_id}.mp3")

    try:
        if ext == ".mp3":
            if saved_path != mp3_path:
                with open(saved_path, "rb") as src, open(mp3_path, "wb") as dst:
                    dst.write(src.read())
        else:
            cmd = [
                "ffmpeg",
                "-y",
                "-i", saved_path,
                "-vn",
                "-q:a", "2",
                mp3_path
            ]
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    except subprocess.CalledProcessError:
        flash("فشل تحويل الملف باستخدام ffmpeg ❌ تأكدي أن ffmpeg مثبت ومساره مضبوط.", "error")
        return redirect(url_for("main.upload"))

    flash("تم رفع الملف وتحويله إلى MP3 بنجاح ✅", "success")
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