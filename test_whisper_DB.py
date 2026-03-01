import time, json, re, wave, contextlib, subprocess
from faster_whisper import WhisperModel

# ✅ غيّري الاستيراد حسب مشروعكم (أهم سطرين)
from app import create_app, db
from app.models import QuranAyah


# ----------------------------
# Audio duration
# ----------------------------
def get_audio_duration(path: str) -> float:
    try:
        with contextlib.closing(wave.open(path, "rb")) as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        pass

    try:
        out = subprocess.check_output(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            text=True
        ).strip()
        return float(out)
    except Exception:
        return 0.0


# ----------------------------
# Normalization (خفيف - لا نخفي أخطاء مثل طغى/طغ)
# ----------------------------
AR_DIACRITICS = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0670\u0640]")

def normalize_ar(text: str) -> str:
    text = (text or "").strip()
    text = AR_DIACRITICS.sub("", text)  # إزالة التشكيل + التطويل
    # توحيد الهمزات فقط
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    # لا نحول ى→ي ولا ة→ه حتى لا نضيع أخطاء حقيقية
    text = re.sub(r"\s+", " ", text).strip()
    return text

def tokenize(text: str):
    # إبقاء العربية + مسافات فقط
    text = re.sub(r"[^\u0600-\u06FF\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return [w for w in text.split(" ") if w]


# ----------------------------
# Levenshtein ops (word-level)
# ----------------------------
def levenshtein_ops(ref_words, hyp_words):
    n, m = len(ref_words), len(hyp_words)
    dp = [[0]*(m+1) for _ in range(n+1)]
    bt = [[None]*(m+1) for _ in range(n+1)]

    for i in range(1, n+1):
        dp[i][0] = i
        bt[i][0] = ("delete", i-1, None)
    for j in range(1, m+1):
        dp[0][j] = j
        bt[0][j] = ("insert", None, j-1)

    for i in range(1, n+1):
        for j in range(1, m+1):
            if ref_words[i-1] == hyp_words[j-1]:
                dp[i][j] = dp[i-1][j-1]
                bt[i][j] = ("equal", i-1, j-1)
            else:
                choices = [
                    (dp[i-1][j] + 1, ("delete", i-1, None)),
                    (dp[i][j-1] + 1, ("insert", None, j-1)),
                    (dp[i-1][j-1] + 1, ("replace", i-1, j-1)),
                ]
                dp[i][j], bt[i][j] = min(choices, key=lambda x: x[0])

    ops = []
    i, j = n, m
    while i > 0 or j > 0:
        kind, ri, hj = bt[i][j]
        ops.append((kind, ri, hj))
        if kind in ("equal", "replace"):
            i -= 1
            j -= 1
        elif kind == "delete":
            i -= 1
        else:  # insert
            j -= 1
    ops.reverse()
    return ops


# ----------------------------
# ✅ DB: جلب الآيات من قاعدة البيانات (مضبوط على موديلكم)
# QuranAyah: surahid, ayahnumber, ayahtext
# ----------------------------
def get_surah_ayat_from_db(surah_no: int):
    ayat = (
        QuranAyah.query
        .filter(QuranAyah.surahid == surah_no)
        .order_by(QuranAyah.ayahnumber.asc())
        .all()
    )
    if not ayat:
        raise ValueError(f"No ayat found in DB for surah={surah_no}")
    return ayat


def build_ref_word_to_ayah_map(ayat):
    """
    يرجّع:
      ref_tokens: كل كلمات السورة (مقسمة word-level)
      ref_to_ayah: نفس الطول، كل كلمة معها رقم الآية
    """
    ref_tokens = []
    ref_to_ayah = []

    for a in ayat:
        toks = tokenize(normalize_ar(a.ayahtext))
        for t in toks:
            ref_tokens.append(t)
            ref_to_ayah.append(int(a.ayahnumber))

    return ref_tokens, ref_to_ayah


# ----------------------------
# Build report (with ayah_number + indexes)
# ----------------------------
def build_report(ref_tokens, ref_to_ayah, whisper_words_with_time):
    # hypothesis tokens + times (متوافقة مع normalize/tokenize)
    hyp_tokens = []
    hyp_times = []

    for w in whisper_words_with_time:
        nw = normalize_ar(w["word"])
        toks = tokenize(nw)
        if not toks:
            continue
        for t in toks:
            hyp_tokens.append(t)
            hyp_times.append(w["start"])

    ops = levenshtein_ops(ref_tokens, hyp_tokens)

    def hyp_time(idx):
        if idx is None:
            return None
        if idx < 0 or idx >= len(hyp_times):
            return None
        return hyp_times[idx]

    def ayah_of_ref(ri):
        if ri is None:
            return None
        if ri < 0 or ri >= len(ref_to_ayah):
            return None
        return ref_to_ayah[ri]

    rows = []
    correct = add = delete = sub = 0

    for kind, ri, hj in ops:
        if kind == "equal":
            correct += 1
            rows.append({
                "status": "correct",
                "type": None,
                "expected": ref_tokens[ri],
                "actual": hyp_tokens[hj],
                "time": hyp_time(hj),
                "ayah_number": ayah_of_ref(ri),
                "ref_index": ri,
                "hyp_index": hj
            })

        elif kind == "insert":
            add += 1
            # insertion ما لها آية مؤكدة، نخليها None
            rows.append({
                "status": "error",
                "type": "addition",
                "expected": None,
                "actual": hyp_tokens[hj],
                "time": hyp_time(hj),
                "ayah_number": None,
                "ref_index": ri,
                "hyp_index": hj
            })

        elif kind == "delete":
            delete += 1
            # وقت الحذف: أقرب كلمة قبلها في hyp (إن وجدت)
            anchor_time = hyp_time(hj-1) if hj is not None else None
            rows.append({
                "status": "error",
                "type": "deletion",
                "expected": ref_tokens[ri],
                "actual": None,
                "time": anchor_time,
                "ayah_number": ayah_of_ref(ri),
                "ref_index": ri,
                "hyp_index": hj
            })

        elif kind == "replace":
            sub += 1
            rows.append({
                "status": "error",
                "type": "substitution",
                "expected": ref_tokens[ri],
                "actual": hyp_tokens[hj],
                "time": hyp_time(hj),
                "ayah_number": ayah_of_ref(ri),
                "ref_index": ri,
                "hyp_index": hj
            })

    return {
        "summary": {
            "total_words": len(ref_tokens),
            "correct": correct,
            "addition": add,
            "deletion": delete,
            "substitution": sub,
            "is_valid": (add + delete + sub) == 0
        },
        "rows": rows
    }


def main():
    # ✅ عدّلي حسب اختبارك
    audio_path = "downloads/audio0_pad.wav"
    surah_no = 1  # الفاتحة (حسب DB: surahid)

    app = create_app()
    with app.app_context():
        ayat = get_surah_ayat_from_db(surah_no)
        reference_text = " ".join([(a.ayahtext or "").strip() for a in ayat]).strip()
        ref_tokens, ref_to_ayah = build_ref_word_to_ayah_map(ayat)

    model = WhisperModel("medium", device="cpu", compute_type="int8")

    duration = get_audio_duration(audio_path)
    use_vad = duration >= 120  # اتفقنا: الطويل فقط

    kwargs = dict(
        language="ar",
        beam_size=8,
        temperature=0.0,
        best_of=1,
        condition_on_previous_text=True,
        word_timestamps=True,
    )

    if use_vad:
        kwargs.update(dict(
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=200, speech_pad_ms=500),
            condition_on_previous_text=False,
        ))
        print(f"[INFO] duration={duration:.2f}s -> VAD=ON")
    else:
        kwargs.update(dict(vad_filter=False))
        print(f"[INFO] duration={duration:.2f}s -> VAD=OFF")

    t0 = time.time()
    segments, info = model.transcribe(audio_path, **kwargs)
    segments = list(segments)
    elapsed = round(time.time() - t0, 2)

    print("TRANSCRIBE_TIME:", elapsed)
    print("-" * 50)

    whisper_words = []

    for s in segments:
        print(f"[{s.start:.2f} - {s.end:.2f}] {s.text.strip()}")
        if getattr(s, "words", None):
            for w in s.words:
                whisper_words.append({
                    "word": (w.word or "").strip(),
                    "start": float(w.start),
                    "end": float(w.end),
                })

    # fallback لو ما طلعت words (نادر)
    if not whisper_words:
        for s in segments:
            toks = tokenize(normalize_ar(s.text))
            if not toks:
                continue
            seg_len = max(0.001, (s.end - s.start))
            step = seg_len / len(toks)
            for i, tok in enumerate(toks):
                whisper_words.append({
                    "word": tok,
                    "start": float(s.start + i * step),
                    "end": float(s.start + (i + 1) * step),
                })

    report = build_report(ref_tokens, ref_to_ayah, whisper_words)

    payload = {
        "surah_no": surah_no,
        "audio_path": audio_path,
        "duration": duration,
        "transcribe_time": elapsed,
        "reference_text_from_db": reference_text,
        "report": report,
    }

    out_name = f"report_surah_{surah_no}.json"
    with open(out_name, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Saved: {out_name}")


if __name__ == "__main__":
    main()