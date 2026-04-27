import os
import sys
sys.path.insert(0, os.path.dirname(__file__))
import indexer
from config import FANFICS_DIR

count = 0
for root, dirs, files in os.walk(FANFICS_DIR):
    for f in files:
        path = os.path.join(root, f)
        if indexer.index_file(path):
            count += 1

print(f"Переиндексировано: {count}")