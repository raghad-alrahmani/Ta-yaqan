import whisper

model = whisper.load_model("base")

result = model.transcribe("downloads/pUb9EW770d0.mp3", language="ar")

print("النص الكامل:\n")
print(result["text"])

print("\nالمقاطع مع التوقيت:\n")

for segment in result["segments"]:
    print(f"[{segment['start']:.2f} - {segment['end']:.2f}] {segment['text']}")