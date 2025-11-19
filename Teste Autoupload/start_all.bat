@echo off
start "backend" cmd /c "python -m uvicorn backend.app:app --host 0.0.0.0 --port 666"
start "frontend" cmd /c "python -m http.server 8080 -d frontend"
REM aguarda 3s e abre o navegador
ping 127.0.0.1 -n 3 >nul
start "" http://127.0.0.1:8080/