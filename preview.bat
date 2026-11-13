@echo off
rem Starts a tiny local web server for this folder and opens the model viewer in your browser.
rem Close this window to stop the server.
cd /d "%~dp0"
start "" http://localhost:8123/preview.html
python -m http.server 8123
