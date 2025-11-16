import os

SECRET_KEY="secretkey"

DB_CONFIG={
    "host":"localhost",
    "user":"root",
    "password":"veer@6805",
    "database":"echocircle"
}

UPLOAD_FOLDER=os.path.join(os.getcwd(),"uploads","issue_image")
ALLOWED_EXTENSIONS={"png","jpg","jpeg"}

GEMINI_API_KEY="AIzaSyA8vZSTwCCLy_onXNHqL9GJmub6hcHdrdM"
