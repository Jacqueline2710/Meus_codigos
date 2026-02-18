@echo off
cd /d "%~dp0"
echo Instalando dependencias...
python -m pip install -r "%~dp0..\requirements.txt" -q
echo.
echo Iniciando interface web...
python -m streamlit run app_streamlit.py
pause
