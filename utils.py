import re

def normalize(text):
    text = text.replace('_', ' ')
    text = text.replace('-', ' ')   # дефис → пробел
    text = text.lower()
    text = text.replace('ё', 'е')   # замена ё на е
    text = re.sub(r'[^\w\s]', '', text)  # удаляем всё кроме букв, цифр, пробелов
    return text.strip()