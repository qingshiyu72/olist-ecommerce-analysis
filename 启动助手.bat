@echo off
title AI Analysis Assistant
cd /d "C:\Users\32493\Desktop\卿时彧\事项\数据集\olist-analysis"
echo Starting AI Analysis Assistant ... browser will open automatically
"C:\Users\32493\.workbuddy\binaries\python\envs\default\Scripts\python.exe" -m streamlit run app.py
echo.
echo Exited. Press any key to close.
pause >nul
