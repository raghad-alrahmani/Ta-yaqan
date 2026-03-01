import re
import time
from difflib import SequenceMatcher
from faster_whisper import WhisperModel

# ✅ إضافة: استيراد db و QuranAyah
from app import create_app
from app.models import QuranAyah

# 1) Normalize (توحيد النص)
AR_DIACRITICS = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0670\u0640]")  # تشكيل + تطويل
PUNCT = re.compile(r"[^\w\s\u0600-\u06FF]")  # يحذف علامات الترقيم (يبقي العربي/الأرقام/underscore)

def normalize_ar(text: str) -> str:
    text = (text or "").strip()
    text = AR_DIACRITICS.sub("", text)
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ة", "ه")  # اختياري: يساعد أحياناً
    text = text.replace("ؤ", "و").replace("ئ", "ي")  # اختياري
    text = PUNCT.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text

def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio()

# ✅ بدال SURAH_ALFATIHA: نجيب آيات السورة من DB
def get_surah_verses_from_db(surah_id: int) -> list[str]:
    rows = (
        QuranAyah.query
        .filter_by(surahid=surah_id)
        .order_by(QuranAyah.ayahnumber.asc())
        .all()
    )
    return [r.ayahtext for r in rows]

def best_match(segment_text: str, verses: list[str]):
    seg_n = normalize_ar(segment_text)
    best = ("", 0.0)
    for v in verses:
        s = similarity(seg_n, normalize_ar(v))
        if s > best[1]:
            best = (v, s)
    return best  # (verse_text, score)

def main():
    audio_path = r"downloads/norm_audio2.wav"  # غيّري الاسم حسب ملفك
    model_name = "medium"  # جربي small كبداية على CPU
    device = "cpu"
    compute_type = "int8"

    # ✅ هنا تختارين السورة المطلوبة (مثال: الفاتحة = 1)
    surah_id = 1

    print("Loading model...")
    model = WhisperModel(model_name, device=device, compute_type=compute_type)

    t0 = time.time()
    segments, info = model.transcribe(
        audio_path,
        language="ar",
        vad_filter=True,
        beam_size=5,
    )
    t1 = time.time()

    # ✅ جلب الآيات من DB
    verses = get_surah_verses_from_db(surah_id)

    print(f"\nTRANSCRIBE_TIME: {round(t1 - t0, 2)}s")
    print("-" * 50)

    # 3) طباعة التوقيت + (أقرب آية صحيحة)
    for seg in segments:
        verse, score = best_match(seg.text, verses)
        start = f"{seg.start:.2f}"
        end = f"{seg.end:.2f}"
        print(f"[{start} - {end}]  {verse}   (score={score:.2f})")

if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        main() 