@echo off
set VITE_API_BASE_URL=http://127.0.0.1:8011
echo BASE=[%VITE_API_BASE_URL%] >> "%LOCALAPPDATA%\omnixa-dev-tools\logs\vite-env-check.txt"
cd /d C:\Users\Admin（无密码）\Desktop\vibeCoding\my-web
npm run dev -- --host 127.0.0.1
