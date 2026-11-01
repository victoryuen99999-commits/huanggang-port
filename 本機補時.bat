@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 皇崗口岸資訊站 — 本機補時（Actions 被 throttle 時補上）
echo 只會在遠端快照超過 12 分鐘時才更新，避免同 GitHub Actions 撞
echo.
python local_refresh.py
echo.
pause
