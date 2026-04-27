import os
from dotenv import load_dotenv
load_dotenv()

DB_PATH = os.getenv("DB_PATH", "fanfics.db")
FANFICS_DIR = os.getenv("FANFICS_DIR", "fanfics_storage/main")
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "fanfics_storage/uploads")

RESULTS_PER_PAGE = 10
SEARCH_TTL = 300
FILE_CACHE_SIZE = 20