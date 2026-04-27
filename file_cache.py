from collections import OrderedDict
from config import FILE_CACHE_SIZE

class FileCache:
    def __init__(self, max_size=FILE_CACHE_SIZE):
        self.cache = OrderedDict()
        self.max_size = max_size

    def get(self, path):
        if path in self.cache:
            self.cache.move_to_end(path)
            return self.cache[path]
        return None

    def put(self, path, file):
        self.cache[path] = file
        self.cache.move_to_end(path)

        if len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

file_cache = FileCache()