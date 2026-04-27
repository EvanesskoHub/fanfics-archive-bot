import os
import sqlite3
import re
import hashlib
import shutil
from datetime import datetime
import docx
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup

from config import FANFICS_DIR, UPLOADS_DIR, DB_PATH
from utils import normalize

def get_file_hash(filepath):
    hash_sha256 = hashlib.sha256()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()


def read_first_lines(file_path, max_lines=50):
    """Извлекает первые строки текста из файла в зависимости от формата"""
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in {'.txt', '.docx', '.epub', '.fb2'}:
        return ""
    text = ""
    try:
        if ext == '.txt':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = []
                for i, line in enumerate(f):
                    if i >= max_lines:
                        break
                    lines.append(line)
                text = "\n".join(lines)
        elif ext == '.docx':
            doc = docx.Document(file_path)
            paras = doc.paragraphs[:max_lines]
            text = "\n".join([p.text for p in paras])
        elif ext == '.epub':
            book = epub.read_epub(file_path)
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    raw_text = soup.get_text()
                    lines = raw_text.split('\n')[:max_lines]
                    text = "\n".join(lines)
                    break
        elif ext == '.fb2':
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            soup = BeautifulSoup(content, 'lxml-xml')
            body = soup.find('body')
            if body:
                raw_text = body.get_text()
                lines = raw_text.split('\n')[:max_lines]
                text = "\n".join(lines)
    except Exception as e:
        print(f"Ошибка чтения {file_path}: {e}")
    return text


def parse_header(text):
    """Извлекает рейтинг, размер и метки из текста шапки и нормализует их"""
    result = {'rating': '', 'length': '', 'tags': ''}
    if not text:
        return result
    
    # Рейтинг
    rating_patterns = [
        r'Рейтинг:\s*([GgPpRrNnCc\-17]+)',
        r'Rating:\s*([GgPpRrNnCc\-17]+)',
        r'Рейтинг:\s*([A-Za-z\-0-9]+)',
    ]
    for pattern in rating_patterns:
        match = re.search(pattern, text)
        if match:
            rating = match.group(1).strip().upper()
            if rating in ('PG-13', 'PG13', 'PG-1', 'P-1', 'PG', 'PG1', 'PG-17', 'P1', 'P', '1', 'RG-1'):
                rating = 'PG-13'
            elif rating in ('NC-17', 'NC17', 'NC-', 'NC', 'N', 'NG-17', 'NC-1', 'R-NC-17', 'G-PG-R-NC17'):
                rating = 'NC-17'
            elif rating in ('R', 'R-17'):
                rating = 'R'
            elif rating in ('G', 'G-1', 'MATURE'):
                rating = 'G'
            else:
                rating = None
            result['rating'] = rating
            break
    
    # Размер
    length_patterns = [
        r'Размер:\s*(мини|миди|макси|драббл|midi|maxi|mini)',
        r'Размер:\s*(\d+\s*страниц|\d+\s*кб|\d+\s*слов)',
        r'Size:\s*(mini|midi|maxi|drabble)',
    ]
    for pattern in length_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            length = match.group(1).strip().lower()
            if length in ('drabble', 'drabb'):
                length = 'драббл'
            elif length in ('mini', 'min'):
                length = 'мини'
            elif length in ('midi', 'mid'):
                length = 'миди'
            elif length in ('maxi', 'max'):
                length = 'макси'
            result['length'] = length
            break
    
    # Метки
    tags_patterns = [
        r'Метки:\s*(.+?)(?:\n\s*\n|\n[А-ЯA-Z]|$)',
        r'Предупреждения:\s*(.+?)(?:\n\s*\n|\n[А-ЯA-Z]|$)',
        r'Tags:\s*(.+?)(?:\n\s*\n|\n[А-ЯA-Z]|$)',
        r'Warning:\s*(.+?)(?:\n\s*\n|\n[А-ЯA-Z]|$)',
    ]
    for pattern in tags_patterns:
        match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
        if match:
            raw = match.group(1).strip()
            raw = re.sub(r'\s+', ' ', raw)
            tags = [t.strip() for t in re.split(r',\s*', raw) if t.strip()]
            result['tags'] = ', '.join(tags)
            break
    
    if result['tags']:
        tags = result['tags']
        tags = tags.replace('OOC', 'ООС')
        tags = tags.replace('AU', 'АУ')
        tags = tags.replace('Hurt/Comfort', 'hurt/comfort')
        tags = tags.replace('PWP', 'pwp')
        tags = tags.replace('Underage', 'underage')
        tags = tags.replace('слэш', '')
        tags = re.sub(r',\s*,', ',', tags)
        tags = tags.strip(', ')
        result['tags'] = tags
    
    return result


def index_file(file_path, source='initial', added_by=None):
    if not os.path.isfile(file_path):
        return False

    # Очистка имени от подчёркиваний и лишних пробелов
    clean_name = re.sub(r'[_]+', ' ', os.path.basename(file_path))
    clean_name = re.sub(r'\s+', ' ', clean_name).strip()
    if not clean_name:
        clean_name = os.path.basename(file_path).replace('_', ' ').strip()
    
    if not clean_name:
        clean_name = os.path.basename(file_path)
    
    if source == 'user':
        target_path = os.path.join(FANFICS_DIR, clean_name)
        base, ext = os.path.splitext(target_path)
        counter = 1
        while os.path.exists(target_path):
            target_path = f"{base}_{counter}{ext}"
            counter += 1
        shutil.copy2(file_path, target_path)
        os.remove(file_path)
        file_path = target_path

    original_name = os.path.splitext(clean_name)[0]
    if not original_name:
        original_name = "Без названия"

    file_hash = get_file_hash(file_path)
    fmt = os.path.splitext(file_path)[1][1:] if os.path.splitext(file_path)[1] else "unknown"

    title = original_name
    author = "Неизвестный автор"
    
    header_text = read_first_lines(file_path)
    if header_text:
        parsed = parse_header(header_text)
        rating = parsed['rating'] if parsed['rating'] else None
        length = parsed['length'] if parsed['length'] else None
        tags = parsed['tags'] if parsed['tags'] else None
    else:
        rating = None
        length = None
        tags = None

    title_normalized = normalize(title)

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT id FROM fanfics WHERE file_hash = ?", (file_hash,))
    row = cur.fetchone()

    if row:
        fic_id = row[0]
        cur.execute("""
            UPDATE fanfics
            SET file_path=?, title=?, title_normalized=?, original_filename=?, rating=?, length=?, tags=?
            WHERE id=?
        """, (file_path, title, title_normalized, original_name, rating, length, tags, fic_id))
    else:
        cur.execute("""
            INSERT INTO fanfics (file_path, file_hash, author, title, title_normalized, format, added_at, source, original_filename, rating, length, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (file_path, file_hash, author, title, title_normalized, fmt, datetime.now().isoformat(), source, original_name, rating, length, tags))

    conn.commit()
    conn.close()
    return True


def index_folder(root_dir, source='initial', added_by=None):
    total = 0
    for root, dirs, files in os.walk(root_dir):
        for file in files:
            file_path = os.path.join(root, file)
            if os.path.basename(file_path).startswith('~$'):
                continue
            if index_file(file_path, source, added_by):
                total += 1
    return total


if __name__ == "__main__":
    print("Начинаю индексацию...")
    index_folder(FANFICS_DIR, source='initial')
    print("Индексация завершена!")