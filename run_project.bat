@echo off
echo Starting AI Market Maker...

:: Start the Backend API in a new window
start cmd /k "venv\Scripts\activate && uvicorn api:app --reload"

:: Start the Frontend UI in a new window
start cmd /k "venv\Scripts\activate && streamlit run app.py"