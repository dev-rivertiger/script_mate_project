import asyncio
import edge_tts
from playsound import playsound # 재생용

TEXT = "이 목소리는 마이크로소프트 엣지 브라우저의 엔진을 사용합니다. 아주 자연스럽죠?"
VOICE = "ko-KR-SunHiNeural" # 한국어 여성 목소리
VOICE = "ko-KR-InJoonNeural" # 한국어 여성 목소리
OUTPUT_FILE = "test.mp3"

async def _main():
    communicate = edge_tts.Communicate(TEXT, VOICE)
    await communicate.save(OUTPUT_FILE)

# 실행
asyncio.run(_main())
# 재생 (저장된 파일 실행)
import os
os.system(f"afplay {OUTPUT_FILE}") # Windows