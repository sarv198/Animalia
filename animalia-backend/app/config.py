import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.environ["DATABASE_URL"]

# Sites allowed to call the API from a browser, comma-separated. In production
# set it to the deployed frontend, e.g. https://reptilia.vercel.app
CORS_ORIGINS = [
    origin.strip().rstrip("/")
    for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(",")
    if origin.strip()
]

# Vercel sets VERCEL=1 in its functions; each function instance is short-lived,
# so it should not keep a pool of open database connections.
SERVERLESS = bool(os.getenv("VERCEL"))
