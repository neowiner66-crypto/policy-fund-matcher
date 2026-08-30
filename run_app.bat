@echo off
title 정책자금 매칭 어시스턴트
cd /d "%~dp0"
echo 정책자금 매칭 어시스턴트를 시작합니다...
echo 브라우저가 자동으로 열립니다 (열리지 않으면 http://localhost:8501 로 직접 접속하세요).
echo 종료하려면 이 창에서 Ctrl+C 를 누르세요.
echo.
streamlit run app.py
pause
