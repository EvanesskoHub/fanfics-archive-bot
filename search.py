from db import get_connection
from utils import normalize

def relevance_score(title_norm, author_norm, words, phrase):
    score = 0
    # Огромный бонус за точное совпадение фразы (все слова подряд)
    if phrase in title_norm:
        score += 1000
    # Бонус за все слова (в любом порядке)
    if all(word in title_norm or word in author_norm for word in words):
        score += 100
    # Бонус за каждое слово
    for word in words:
        if word in title_norm or word in author_norm:
            score += 10
    # Бонус за начало названия
    if title_norm.startswith(words[0]):
        score += 50
    return score


def search_files(query):
    conn = get_connection()
    cur = conn.cursor()

    norm_query = normalize(query)
    words = norm_query.split()

    if not words:
        return []

    # FTS запрос по title_normalized
    fts_query = f'"{norm_query}" OR ' + " ".join(words)

    cur.execute("""
        SELECT f.file_path, f.author, f.title, f.format, f.original_filename, f.title_normalized
        FROM fanfics_fts
        JOIN fanfics f ON f.id = fanfics_fts.rowid
        WHERE fanfics_fts MATCH ?
        LIMIT 300
    """, (fts_query,))

    rows = cur.fetchall()
    conn.close()

    results = []

    for file_path, author, title, fmt, orig_name, title_norm in rows:
        author_norm = normalize(author)
        score = relevance_score(title_norm, author_norm, words, norm_query)
        results.append((score, file_path, author, title, fmt, orig_name))

    results.sort(key=lambda x: x[0], reverse=True)

    return [(r[1], r[2], r[3], r[4], r[5]) for r in results[:200]]