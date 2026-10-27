@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 啟動皇崗口岸資訊站...
python serve.py
pause
