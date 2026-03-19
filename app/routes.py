from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session, send_file
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

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import arabic_reshaper
from bidi.algorithm import get_display
import io, datetime

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


@main.route("/results/<int:input_id>/download-pdf")
def download_pdf(input_id):
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    rec = RecitationInput.query.filter_by(inputid=input_id, verifierid=user_id).first_or_404()

    word_details = (
        RecitationWordDetails.query
        .filter_by(inputid=rec.inputid)
        .order_by(
            RecitationWordDetails.ayahnumber.asc().nullslast(),
            RecitationWordDetails.word_index.asc().nullslast(),
        )
        .all()
    )

    correct_count = sum(1 for w in word_details if w.status == "صحيح")
    missing_count = sum(1 for w in word_details if w.status == "ناقص")
    extra_count   = sum(1 for w in word_details if w.status == "زائد")
    wrong_count   = sum(1 for w in word_details if w.status == "تحريف")
    errors_count  = missing_count + extra_count + wrong_count
    is_ok         = errors_count == 0

    font_path = os.path.join(current_app.root_path, "static", "fonts", "Amiri-Regular.ttf")
    if "Amiri" not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont("Amiri", font_path))

    def ar(text):
        reshaped = arabic_reshaper.reshape(str(text))
        return get_display(reshaped)

    PURPLE  = colors.HexColor("#64449a")
    GREEN   = colors.HexColor("#22c55e")
    RED     = colors.HexColor("#ef4444")
    ORANGE  = colors.HexColor("#f59e0b")
    GRAY_BG = colors.HexColor("#f9fafb")
    BORDER  = colors.HexColor("#e5e7eb")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm,
        topMargin=2*cm, bottomMargin=2*cm,
    )

    def s(size=11, color=colors.black, align="RIGHT"):
        return ParagraphStyle(
            name=f"s{size}{color}{align}",
            fontName="Amiri", fontSize=size,
            textColor=color,
            alignment={"RIGHT":2,"CENTER":1,"LEFT":0}[align],
            leading=size*1.6,
        )

    story = []

    story.append(Paragraph(ar("تقرير نتيجة التحقق"), s(20, PURPLE, "CENTER")))
    story.append(Spacer(1, 0.3*cm))

    surah_name = rec.surah.surahname if hasattr(rec, 'surah') and rec.surah else str(rec.surahid)
    story.append(Paragraph(ar(f"سورة {surah_name}"), s(13, colors.HexColor("#6b7280"), "CENTER")))
    story.append(Spacer(1, 0.2*cm))

    now = datetime.datetime.now().strftime("%Y-%m-%d  %H:%M")
    story.append(Paragraph(ar(f"التاريخ: {now}"), s(10, colors.HexColor("#9ca3af"), "CENTER")))
    story.append(Spacer(1, 0.6*cm))

    result_color = GREEN if is_ok else RED
    result_bg    = colors.HexColor("#f0fdf4") if is_ok else colors.HexColor("#fff1f2")
    result_text  = ar("سليمة") if is_ok else ar("غير سليمة")
    sub_text     = ar("التلاوة صحيحة دون اي اخطاء") if is_ok else ar(f"تم رصد {errors_count} خطا في التلاوة")

    rt = Table(
        [[Paragraph(result_text, s(22, result_color, "CENTER"))],
         [Paragraph(sub_text,    s(11, result_color, "CENTER"))]],
        colWidths=[17*cm],
    )
    rt.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,-1), result_bg),
        ("BOX",          (0,0),(-1,-1), 1.5, result_color),
        ("TOPPADDING",   (0,0),(-1,-1), 14),
        ("BOTTOMPADDING",(0,0),(-1,-1), 14),
    ]))
    story.append(rt)
    story.append(Spacer(1, 0.6*cm))

    stats = [
        (ar("صحيح"), correct_count, colors.HexColor("#eefbf2"), GREEN),
        (ar("خطا"),  wrong_count,   colors.HexColor("#fdeff0"), RED),
        (ar("زائد"), extra_count,   colors.HexColor("#fff6e8"), ORANGE),
        (ar("ناقص"), missing_count, colors.HexColor("#fff6e8"), ORANGE),
    ]

    stats_row = [[
        Table(
            [[Paragraph(label, s(12, col, "CENTER"))],
             [Paragraph(str(val), s(24, col, "CENTER"))]],
            colWidths=[3.8*cm],
            style=TableStyle([
                ("BACKGROUND",   (0,0),(-1,-1), bg),
                ("BOX",          (0,0),(-1,-1), 1, col),
                ("TOPPADDING",   (0,0),(-1,-1), 10),
                ("BOTTOMPADDING",(0,0),(-1,-1), 10),
            ])
        )
        for label, val, bg, col in stats
    ]]
    st = Table(stats_row, colWidths=[4.1*cm]*4, hAlign="CENTER")
    st.setStyle(TableStyle([("ALIGN",(0,0),(-1,-1),"CENTER")]))
    story.append(st)
    story.append(Spacer(1, 0.8*cm))

    story.append(Paragraph(ar("تفاصيل الكلمات"), s(14, PURPLE)))
    story.append(Spacer(1, 0.3*cm))

    STATUS_COLORS = {
        "صحيح":  (colors.HexColor("#ecfdf3"), colors.HexColor("#166534")),
        "تحريف": (colors.HexColor("#fff1f2"), RED),
        "زائد":  (colors.HexColor("#fff6e8"), ORANGE),
        "ناقص":  (colors.HexColor("#fefce8"), colors.HexColor("#854d0e")),
    }

    header = [
        Paragraph(ar("ملاحظات"), s(10, colors.white, "CENTER")),
        Paragraph(ar("الوقت"),   s(10, colors.white, "CENTER")),
        Paragraph(ar("الحالة"), s(10, colors.white, "CENTER")),
        Paragraph(ar("الكلمة"), s(10, colors.white, "CENTER")),
        Paragraph(ar("اية"),    s(10, colors.white, "CENTER")),
    ]
    table_data = [header]

    def fmt_time(sec):
        if sec is None: return "--"
        t = int(float(sec))
        return f"{t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d}"

    for w in word_details:
        if w.status == "ناقص":   word = w.expected_word or "---"
        elif w.status == "زائد": word = w.spoken_word or "---"
        else:                     word = w.expected_word or w.spoken_word or "---"
        note = w.notes if w.notes and str(w.notes).strip() else "لا يوجد"
        row = [
            Paragraph(ar(note),               s(9,  colors.HexColor("#6b7280"), "CENTER")),
            Paragraph(ar(fmt_time(w.starttime)), s(9, colors.black, "CENTER")),
            Paragraph(ar(w.status),           s(9,  colors.black, "CENTER")),
            Paragraph(ar(word),               s(10, colors.black, "CENTER")),
            Paragraph(str(w.ayahnumber or "-"), s(10, colors.black, "CENTER")),
        ]
        table_data.append(row)

    wt = Table(table_data, colWidths=[4.5*cm, 3*cm, 3*cm, 4*cm, 2.5*cm], repeatRows=1)
    ts = TableStyle([
        ("BACKGROUND",    (0,0),(-1,0),  PURPLE),
        ("TEXTCOLOR",     (0,0),(-1,0),  colors.white),
        ("ROWBACKGROUNDS",(0,1),(-1,-1), [colors.white, GRAY_BG]),
        ("BOX",           (0,0),(-1,-1), 0.5, BORDER),
        ("INNERGRID",     (0,0),(-1,-1), 0.3, BORDER),
        ("TOPPADDING",    (0,0),(-1,-1), 7),
        ("BOTTOMPADDING", (0,0),(-1,-1), 7),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("VALIGN",        (0,0),(-1,-1), "MIDDLE"),
    ])
    for i, w in enumerate(word_details, start=1):
        bg, fc = STATUS_COLORS.get(w.status, (colors.white, colors.black))
        ts.add("BACKGROUND", (0,i), (-1,i), bg)
        ts.add("TEXTCOLOR",  (2,i), (2,i),  fc)
    wt.setStyle(ts)
    story.append(wt)

    story.append(Spacer(1, 1*cm))
    story.append(Paragraph(ar("Ta'yaqan - منصة التحقق من التلاوة"), s(9, colors.HexColor("#9ca3af"), "CENTER")))

    doc.build(story)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"report_surah_{rec.surahid}.pdf",
        mimetype="application/pdf"
    )


@main.route("/listen")
def listen():
    return render_template("listen.html")
@main.route("/reports")
def reports():
    user_id = session.get("user_id")
    if not user_id:
        return redirect(url_for("auth.login"))

    from datetime import datetime, timedelta

    period = request.args.get("period", "month")
    now = datetime.utcnow()
    if period == "week":
        since = now - timedelta(days=7)
    elif period == "month":
        since = now - timedelta(days=30)
    elif period == "3months":
        since = now - timedelta(days=90)
    elif period == "year":
        since = now - timedelta(days=365)
    else:
        since = None

    q = RecitationInput.query.filter_by(verifierid=user_id)
    if since:
        q = q.filter(RecitationInput.processingdate >= since)
    all_recs = q.all()

    input_ids = [r.inputid for r in all_recs]
    total_files = len(all_recs)

    if input_ids:
        all_words = RecitationWordDetails.query.filter(
            RecitationWordDetails.inputid.in_(input_ids)
        ).all()
    else:
        all_words = []

    errors_per_input = {}
    for w in all_words:
        if w.status != "صحيح":
            errors_per_input[w.inputid] = errors_per_input.get(w.inputid, 0) + 1

    files_with_errors    = sum(1 for v in errors_per_input.values() if v > 0)
    files_without_errors = total_files - files_with_errors
    total_errors         = sum(errors_per_input.values())

    missing_count = sum(1 for w in all_words if w.status == "ناقص")
    extra_count   = sum(1 for w in all_words if w.status == "زائد")
    wrong_count   = sum(1 for w in all_words if w.status == "تحريف")

    surah_counter = {}
    for r in all_recs:
        sid = r.surahid
        surah_counter[sid] = surah_counter.get(sid, 0) + 1
    top_surah_id   = max(surah_counter, key=surah_counter.get) if surah_counter else None
    top_surah      = QuranSurah.query.get(top_surah_id) if top_surah_id else None
    top_surah_name = top_surah.surahname if top_surah else "—"

    error_type_counts    = {"ناقص": missing_count, "زائد": extra_count, "تحريف": wrong_count}
    most_common_error    = max(error_type_counts, key=error_type_counts.get) if any(error_type_counts.values()) else None
    most_common_error_ar = {"ناقص": "نقص كلمات", "زائد": "زيادة كلمات", "تحريف": "تحريف كلمات"}.get(most_common_error, "—")
    most_common_error_count = error_type_counts.get(most_common_error, 0)

    word_errors = []
    for w in all_words:
        if w.status != "صحيح":
            rec_obj   = RecitationInput.query.get(w.inputid)
            surah_obj = QuranSurah.query.get(rec_obj.surahid) if rec_obj and rec_obj.surahid else None
            word      = w.expected_word if w.status == "ناقص" else w.spoken_word
            if word:
                word_errors.append((word, w.status, w.inputid, surah_obj.surahname if surah_obj else "—"))

    word_agg = {}
    for word, status, inputid, surah_name in word_errors:
        key = (word, status, surah_name)
        if key not in word_agg:
            word_agg[key] = {"count": 0, "files": set()}
        word_agg[key]["count"] += 1
        word_agg[key]["files"].add(inputid)

    top_words = sorted(
        [{"word": k[0], "status": k[1], "surah": k[2],
          "count": v["count"], "files": len(v["files"])}
         for k, v in word_agg.items()],
        key=lambda x: x["count"], reverse=True
    )[:10]

    return render_template(
        "reports.html",
        period=period,
        total_files=total_files,
        files_with_errors=files_with_errors,
        files_without_errors=files_without_errors,
        total_errors=total_errors,
        top_surah_name=top_surah_name,
        missing_count=missing_count,
        extra_count=extra_count,
        wrong_count=wrong_count,
        most_common_error_ar=most_common_error_ar,
        most_common_error_count=most_common_error_count,
        top_words=top_words,
    ) 
@main.route("/reports/pdf")
def reports_pdf():
    period = request.args.get("period", "month")
    return redirect(url_for('main.reports', period=period))