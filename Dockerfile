# 1. 가벼운 파이썬 3.9 버전으로 시작
FROM python:3.9-slim

# 2. 작업 폴더 설정
WORKDIR /app

# 3. 필수 시스템 패키지 설치 (혹시 모를 에러 방지)
RUN apt-get update && apt-get install -y \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 4. 라이브러리 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. 폰트 파일 복사 (중요!)
# 로컬의 fonts 폴더를 컨테이너 내부로 복사합니다.
COPY fonts/ ./fonts/

# 6. 소스 코드 복사
COPY . .

# 7. 포트 노출 (Streamlit 기본 포트)
EXPOSE 8501

# 8. 실행 명령어 (서버 주소 바인딩 중요)
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]