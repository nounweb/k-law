FROM python:3.12-slim

WORKDIR /app

# 의존성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 복사
COPY . .

# 데이터 디렉터리 생성
RUN mkdir -p /app/data

# 포트 노출
EXPOSE 8443

# 실행
CMD ["python", "main.py"]
