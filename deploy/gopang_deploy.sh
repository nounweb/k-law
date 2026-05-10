#!/bin/bash
# ============================================================
# 고팡(Gopang) 데모 배포 스크립트
# 실행: bash gopang_deploy.sh
# ============================================================

set -e
GOPANG_DIR="/opt/gopang"
VENV="$GOPANG_DIR/venv"
ENV_FILE="$GOPANG_DIR/.env"

echo "========================================"
echo " 고팡 데모 배포 시작"
echo "========================================"

# 1. 의존성 설치
echo "[1/5] Python 패키지 설치..."
$VENV/bin/pip install fastapi uvicorn websockets httpx PyJWT --quiet

# 2. 서버 파일 복사
echo "[2/5] 서버 파일 설치..."
cp gopang_server.py $GOPANG_DIR/gopang_server.py
cp gopang_demo.html $GOPANG_DIR/gopang_demo.html

# 3. systemd 서비스 등록
echo "[3/5] systemd 서비스 등록..."
sudo tee /etc/systemd/system/gopang.service > /dev/null << EOF
[Unit]
Description=Gopang Demo FastAPI Server
After=network.target

[Service]
User=ubuntu
WorkingDirectory=$GOPANG_DIR
ExecStart=$VENV/bin/python gopang_server.py
Restart=always
RestartSec=5
EnvironmentFile=$ENV_FILE

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable gopang

# 4. 방화벽 포트 오픈
echo "[4/5] 포트 8000 오픈 확인..."
sudo ufw allow 8000/tcp 2>/dev/null || true

# 5. 서비스 시작
echo "[5/5] 서비스 시작..."
sudo systemctl restart gopang
sleep 2
sudo systemctl status gopang --no-pager

# 결과 출력
PUBLIC_IP=$(curl -s --max-time 3 http://169.254.169.254/opc/v1/instance/metadata/ 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('clientIp',''))" 2>/dev/null || curl -s ifconfig.me)
echo ""
echo "========================================"
echo " 배포 완료!"
echo "========================================"
echo " 서버 IP    : $PUBLIC_IP"
echo " API        : http://$PUBLIC_IP:8000"
echo " API 문서   : http://$PUBLIC_IP:8000/docs"
echo " 웹 클라이언트: gopang_demo.html 를 브라우저에서 열기"
echo "   (서버 주소를 IP로 변경해야 할 경우:"
echo "    html 파일 내 location.hostname 자동 사용)"
echo ""
echo " 로그 확인  : sudo journalctl -u gopang -f"
echo " 서비스 재시작: sudo systemctl restart gopang"
echo "========================================"
