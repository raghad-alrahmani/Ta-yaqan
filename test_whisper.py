import time
import wave
import contextlib
import subprocess
import tempfile
import os
import re

from faster_whisper import WhisperModel
from rapidfuzz import fuzz

# ✅ عدّلي الاستيراد حسب مشروعكم (لازم DB تكون جاهزة)
from app import create_app
from app.models import QuranAyah  # QuranAyah: surahid, ayahnumber, ayahtext


# ----------------------------
# Settings
# ----------------------------
VAD_THRESHOLD = 90               # ثواني: أقل من كذا -> VAD OFF غالبًا أفضل
SURAH_CANDIDATES = range(1, 115) # 1..114
DETECT_SAMPLE_WORDS = 45         # من نص Whisper (أول كم كلمة) للاكتشاف
DETECT_DB_PREFIX_WORDS = 80      # أول كم كلمة من كل سورة في DB للمقارنة

MAX_EDIT_DISTANCE = 2            # نصحح أخطاء بسيطة فقط
AUDIO_MARGIN = 10                # لازم expected يفوز بفارق واضح عشان نصحح
CLIP_LEFT = 1.0                  # ثواني قبل الكلمة
CLIP_RIGHT = 1.5                 # ثواني بعد الكلمة

MAX_WORDS_PER_LINE = 10          # عشان ما تطلع جملة طويلة جدًا


# ----------------------------
# Normalization (DB + Whisper)
# ----------------------------
AR_DIACRITICS = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0670\u0640]")

def normalize_ar(text: str) -> str:
    text = (text or "").strip()
    text = AR_DIACRITICS.sub("", text)  # إزالة التشكيل + التطويل
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = re.sub(r"\s+", " ", text).strip()
    return text

def tokenize(text: str):
    text = re.sub(r"[^\u0600-\u06FF\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return [w for w in text.split(" ") if w]


# ----------------------------
# Audio duration
# ----------------------------
def get_audio_duration(path: str) -> float:
    # WAV
    try:
        with contextlib.closing(wave.open(path, "rb")) as wf:
            return wf.getnframes() / float(wf.getframerate())
    except Exception:
        pass

    # ffprobe لأي صيغة ثانية
    try:
        out = subprocess.check_output(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path
            ],
            text=True
        ).strip()
        return float(out)
    except Exception:
        return 0.0


# ----------------------------
# ffmpeg cut (clip)
# ----------------------------
def cut_audio(in_path, start_s, end_s, out_wav):
    cmd = [
        "ffmpeg", "-y", "-i", in_path,
        "-ss", str(max(0, start_s)), "-to", str(max(0, end_s)),
        "-ar", "16000", "-ac", "1",
        out_wav
    ]
    subprocess.check_output(cmd, stderr=subprocess.STDOUT, text=True)


# ----------------------------
# DB helpers
# ----------------------------
def get_surah_ayat_from_db(surah_no: int):
    ayat = (
        QuranAyah.query
        .filter(QuranAyah.surahid == surah_no)
        .order_by(QuranAyah.ayahnumber.asc())
        .all()
    )
    return [(a.ayahnumber, (a.ayahtext or "").strip()) for a in ayat if (a.ayahtext or "").strip()]

def get_surah_words_from_db(surah_no: int):
    ayat = get_surah_ayat_from_db(surah_no)
    if not ayat:
        return []
    full = " ".join([t for _, t in ayat])
    return tokenize(normalize_ar(full))

def detect_surah_from_text(app, hyp_text: str):
    hyp_tokens = tokenize(normalize_ar(hyp_text))
    sample = " ".join(hyp_tokens[:DETECT_SAMPLE_WORDS])
    if not sample:
        return None, 0.0

    best_surah = None
    best_score = -1.0

    with app.app_context():
        for s in SURAH_CANDIDATES:
            ref_words = get_surah_words_from_db(s)
            if not ref_words:
                continue
            ref_prefix = " ".join(ref_words[:DETECT_DB_PREFIX_WORDS])
            score = fuzz.token_set_ratio(sample, ref_prefix)
            if score > best_score:
                best_score = score
                best_surah = s

    return best_surah, float(best_score)


# ----------------------------
# Alignment (word-level Levenshtein ops)
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
            i -= 1; j -= 1
        elif kind == "delete":
            i -= 1
        else:
            j -= 1
    ops.reverse()
    return ops

def edit_distance(a: str, b: str) -> int:
    a, b = a or "", b or ""
    n, m = len(a), len(b)
    dp = list(range(m+1))
    for i in range(1, n+1):
        prev = dp[0]
        dp[0] = i
        for j in range(1, m+1):
            cur = dp[j]
            cost = 0 if a[i-1] == b[j-1] else 1
            dp[j] = min(dp[j] + 1, dp[j-1] + 1, prev + cost)
            prev = cur
    return dp[m]


# ----------------------------
# Audio check (محافظ) لمنع تغطية خطأ القارئ
# ----------------------------
def clip_text(model: WhisperModel, clip_path: str, prompt: str | None):
    segs, _ = model.transcribe(
        clip_path,
        language="ar",
        beam_size=8,
        temperature=0.0,
        best_of=1,
        vad_filter=False,
        condition_on_previous_text=False,
        initial_prompt=prompt
    )
    txt = " ".join([s.text.strip() for s in segs]).strip()
    return normalize_ar(txt)

def should_fix_by_audio(model, audio_path, t, actual, expected, context_prompt):
    start_s = t - CLIP_LEFT
    end_s   = t + CLIP_RIGHT

    with tempfile.TemporaryDirectory() as td:
        clip = os.path.join(td, "clip.wav")
        cut_audio(audio_path, start_s, end_s, clip)

        neutral = clip_text(model, clip, prompt=None)
        guided  = clip_text(model, clip, prompt=context_prompt)

        actual_n = normalize_ar(actual)
        expected_n = normalize_ar(expected)

        n_exp = fuzz.token_set_ratio(neutral, expected_n)
        n_act = fuzz.token_set_ratio(neutral, actual_n)

        g_exp = fuzz.token_set_ratio(guided, expected_n)
        g_act = fuzz.token_set_ratio(guided, actual_n)

        return (n_exp - n_act >= AUDIO_MARGIN) and (g_exp - g_act >= AUDIO_MARGIN)


# ----------------------------
# Printing: منع السطور الطويلة (بناءً على words)
# ----------------------------
def print_segment_words(s):
    if not getattr(s, "words", None) or len(s.words) == 0:
        print(f"[{s.start:.2f} - {s.end:.2f}] {s.text.strip()}")
        return

    words = []
    for w in s.words:
        ww = (w.word or "").strip()
        if ww:
            words.append((ww, w.start, w.end))

    if not words:
        print(f"[{s.start:.2f} - {s.end:.2f}] {s.text.strip()}")
        return

    chunk = []
    chunk_start = None
    chunk_end = None

    for ww, ws, we in words:
        if chunk_start is None:
            chunk_start = float(ws) if ws is not None else float(s.start)
        chunk_end = float(we) if we is not None else float(s.end)

        chunk.append(ww)

        if len(chunk) >= MAX_WORDS_PER_LINE:
            print(f"[{chunk_start:.2f} - {chunk_end:.2f}] {' '.join(chunk)}")
            chunk = []
            chunk_start = None
            chunk_end = None

    if chunk:
        cs = chunk_start if chunk_start is not None else float(s.start)
        ce = chunk_end if chunk_end is not None else float(s.end)
        print(f"[{cs:.2f} - {ce:.2f}] {' '.join(chunk)}")


# ----------------------------
# Main: RAW / CLEAN (بدون طباعة DB)
# ----------------------------
def main():
    audio_path = "downloads/naziat1_pad.wav"  # ✅ غيري الملف هنا فقط

    app = create_app()
    model = WhisperModel("medium", device="cpu", compute_type="int8")

    duration = get_audio_duration(audio_path)
    use_vad = (duration > VAD_THRESHOLD)

    # ✅ أهم تعديل: نخلي condition_on_previous_text=False (أثبت للقرآن)
    kwargs = dict(
        language="ar",
        beam_size=8,
        temperature=0.0,
        best_of=1,
        condition_on_previous_text=False,
        word_timestamps=True,
        initial_prompt="تلاوة قرآن كريم باللغة العربية الفصحى، الكلمات كاملة بدون اختصار.",
    )

    # ✅ VAD يشتغل فعليًا فقط إذا use_vad=True
    if use_vad:
        kwargs.update(dict(
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=400, speech_pad_ms=900),
        ))
        print(f"[INFO] duration={duration:.2f}s -> VAD=ON")
    else:
        kwargs.update(dict(vad_filter=False))
        print(f"[INFO] duration={duration:.2f}s -> VAD=OFF")

    # (1) Whisper RAW
    t0 = time.time()
    segments, _ = model.transcribe(audio_path, **kwargs)
    segments = list(segments)
    transcribe_time = round(time.time() - t0, 2)

    raw_text = " ".join([s.text.strip() for s in segments]).strip()

    # (2) Detect surah automatically
    detected_surah, score = detect_surah_from_text(app, raw_text)
    if not detected_surah:
        print("\n[DETECT] Could not detect surah.")
        return

    probe = " ".join(tokenize(normalize_ar(raw_text))[:80])
    print(f"\n[DETECT] surah_id={detected_surah}  score={score:.2f}")
    print(f"[DETECT] probe_text: {probe}\n")

    # (3) DB reference words (normalized) — نستخدمها للتصحيح فقط بدون طباعة
    with app.app_context():
        ref_words = get_surah_words_from_db(detected_surah)

    if not ref_words:
        print("[WARN] DB reference not found for detected surah.")
        return

    # (4) Build hyp_words + hyp_times من Whisper words
    whisper_word_objs = []
    for s in segments:
        if getattr(s, "words", None):
            for w in s.words:
                ww = (w.word or "").strip()
                if ww:
                    whisper_word_objs.append(w)

    if not whisper_word_objs:
        print("[WARN] word_timestamps ما طلعت كلمات.")
        return

    hyp_words = []
    hyp_times = []
    for w in whisper_word_objs:
        toks = tokenize(normalize_ar((w.word or "").strip()))
        for tok in toks:
            hyp_words.append(tok)
            hyp_times.append(float(w.start) if w.start is not None else 0.0)

    # (5) Align + Decide Whisper-only fixes
    ops = levenshtein_ops(ref_words, hyp_words)

    token_fix_map = {}  # hyp_token_index -> corrected token
    fixes = []

    for kind, ri, hj in ops:
        if kind != "replace" or ri is None or hj is None:
            continue

        expected = ref_words[ri]
        actual = hyp_words[hj]

        if edit_distance(actual, expected) > MAX_EDIT_DISTANCE:
            continue

        t = hyp_times[hj] if hj < len(hyp_times) else None
        if t is None:
            continue

        left = ref_words[max(0, ri-2):ri]
        right = ref_words[ri+1:ri+3]
        prompt_context = " ".join(["تلاوة قرآن:", *left, expected, *right])

        if should_fix_by_audio(model, audio_path, t, actual, expected, prompt_context):
            token_fix_map[hj] = expected
            fixes.append((t, actual, expected))

    # (6) Apply fixes داخل segments
    token_idx = 0
    for w in whisper_word_objs:
        raw = (w.word or "").strip()
        toks = tokenize(normalize_ar(raw))

        if len(toks) != 1:
            token_idx += len(toks)
            continue

        if token_idx in token_fix_map:
            w.word = token_fix_map[token_idx]

        token_idx += 1

    # -------- Outputs --------
    print("TRANSCRIBE_TIME:", transcribe_time)
    print("-" * 50)
    print("[WHISPER RAW]")
    print(raw_text)

    print("\n" + "-" * 50)
    print("[WHISPER CLEAN - SEGMENTS]")
    for s in segments:
        print_segment_words(s)

    clean_text = " ".join([
        " ".join([(w.word or "").strip() for w in s.words]) if getattr(s, "words", None) else s.text.strip()
        for s in segments
    ])
    clean_text = re.sub(r"\s+", " ", clean_text).strip()

    print("\n" + "-" * 50)
    print("[WHISPER CLEAN - FULL]")
    print(clean_text)

    print("\n" + "-" * 50)
    print(f"[RESULT] Detected surah: {detected_surah}")
    print("[FIXES APPLIED]:")
    if fixes:
        for t, a, e in fixes:
            print(f"- t={t:.2f}: {a} -> {e}")
    else:
        print("none")


if __name__ == "__main__":
    main()