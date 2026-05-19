@echo off
chcp 65001 > nul
title MailBot with Watchdog
echo ========================================
echo   MailBot with Watchdog
echo   Auto-restart on freeze
echo ========================================
echo.
echo Starting watchdog...
start /B MailBot.exe
echo Bot started, watchdog active.
echo.
echo To stop, close both windows.
echo.
pause