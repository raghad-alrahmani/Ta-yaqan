from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from werkzeug.utils import secure_filename

from app import db
from sqlalchemy import func

from app.models import (
    VerifierUser,
    RecitationInput,
    QuranSurah,
    QuranAyah,
    ErrorDetails,
    RecitationWordDetails
)
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
@main.route("/history")
def history():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    # ✅ rows: تجيب السجل + اسم السورة + عدد الأخطاء من جدول الكلمات
    rows = (
        db.session.query(
            RecitationInput,
            QuranSurah.surahname.label("surahname"),
            func.count(RecitationWordDetails.wordid)
                .filter(RecitationWordDetails.status != "صحيح")
                .label("errors_count"),
        )
        .outerjoin(QuranSurah, QuranSurah.surahid == RecitationInput.surahid)
        .outerjoin(RecitationWordDetails, RecitationWordDetails.inputid == RecitationInput.inputid)
        .filter(RecitationInput.verifierid == user_id)
        .group_by(RecitationInput.inputid, QuranSurah.surahname)
        .order_by(RecitationInput.processingdate.desc().nullslast())
        .all()
    )

    input_ids = [r.RecitationInput.inputid for r in rows]

    # ✅ errors_map: تفاصيل الأخطاء من جدول الكلمات (ناقص/زائد/تحريف)
    errors_map = {}
    if input_ids:
        word_errs = (
            db.session.query(
                RecitationWordDetails.inputid,
                RecitationWordDetails.ayahnumber,
                RecitationWordDetails.status,
                RecitationWordDetails.expected_word,
                RecitationWordDetails.spoken_word,
            )
            .filter(RecitationWordDetails.inputid.in_(input_ids))
            .filter(RecitationWordDetails.status.in_(["ناقص", "زائد", "تحريف"]))
            .order_by(
                RecitationWordDetails.inputid.asc(),
                RecitationWordDetails.ayahnumber.asc().nullslast(),
                RecitationWordDetails.word_index.asc().nullslast(),
            )
            .all()
        )

        for inputid, ayahnumber, status, expected_word, spoken_word in word_errs:
            # اسم نوع الخطأ اللي تبينه في الواجهة
            if status == "ناقص":
                msg = f"نقص كلمة: {expected_word or ''}".strip()
            elif status == "زائد":
                msg = f"زيادة كلمة: {spoken_word or ''}".strip()
            else:  # تحريف
                msg = f"تحريف: المتوقع '{expected_word or ''}' — المنطوق '{spoken_word or ''}'".strip()

            errors_map.setdefault(inputid, []).append({
                "ayahnumber": ayahnumber,
                "errortype": status,          # (ناقص/زائد/تحريف)
                "mismatchedtext": msg,
            })

    return render_template("history.html", rows=rows, errors_map=errors_map)

@main.route("/results/<int:input_id>")
def results(input_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    rec = RecitationInput.query.filter_by(inputid=input_id, verifierid=user_id).first_or_404()

    # موجود عندك
    errors = (
        db.session.query(ErrorDetails, QuranAyah.ayahnumber)
        .join(QuranAyah, QuranAyah.ayahid == ErrorDetails.referenceayahid)
        .filter(ErrorDetails.inputid == rec.inputid)
        .all()
    )

    # الجديد: جدول الكلمات
    word_details = (
        RecitationWordDetails.query
        .filter_by(inputid=rec.inputid)
        .order_by(
            RecitationWordDetails.ayahnumber.asc().nullslast(),
            RecitationWordDetails.word_index.asc().nullslast(),
            RecitationWordDetails.starttime.asc().nullslast(),
            RecitationWordDetails.wordid.asc())
        .all()
    )

    # Counts من جدول الكلمات (عشان الكروت + )
    correct_count = sum(1 for w in word_details if w.status == "صحيح")
    missing_count = sum(1 for w in word_details if w.status == "ناقص")
    extra_count   = sum(1 for w in word_details if w.status == "زائد")
    wrong_count   = sum(1 for w in word_details if w.status == "تحريف")

    total_count = len(word_details)
    errors_count = missing_count + extra_count + wrong_count

    # حالة النتيجة العامة للعنوان
    errors_count = missing_count + extra_count + wrong_count
    is_ok = errors_count == 0

    return render_template(
        "results.html",
        rec=rec,
        errors=errors,                 # نخليها موجودة
        word_details=word_details,
        total_count=total_count,
        correct_count=correct_count,
        missing_count=missing_count,
        extra_count=extra_count,
        wrong_count=wrong_count,
        errors_count=errors_count,
        is_ok=is_ok
    )


@main.route("/results_stub/<int:input_id>")
def results_stub(input_id):
    # ✅ هذا بدل الدالة المكررة اللي كانت تسبب Crash
    # نخليها موجودة بدون ما تكسر Flask
    return redirect(url_for("main.results", input_id=input_id))


@main.route("/listen")
def listen():
    return render_template("listen.html")