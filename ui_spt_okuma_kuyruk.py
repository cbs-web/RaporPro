# Dosya: RaporPro/ui_spt_okuma_kuyruk.py
import os

from spt_gorsel import dogal_siralama_anahtari
from ui_spt_okuma_yardimci import (
    collect_image_paths,
    source_content_key,
    source_unique_key,
)


class SPTFotografKuyrugu:
    """SPT fotograf yollarini ve tekrar kontrolunu UI'dan bagimsiz yonetir."""

    def __init__(self, recursive=True):
        self.recursive = bool(recursive)
        self.paths = []
        self._content_cache = {}

    @staticmethod
    def _file_signature(path):
        try:
            stat = os.stat(path)
        except OSError:
            return None
        return stat.st_size, getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000))

    def content_key(self, path):
        absolute = os.path.abspath(path)
        path_key = source_unique_key(absolute)
        signature = self._file_signature(absolute)
        cached = self._content_cache.get(path_key)
        if signature is not None and cached and cached[0] == signature:
            return cached[1]
        content_key = source_content_key(absolute) if signature is not None else ""
        if signature is None:
            self._content_cache.pop(path_key, None)
        else:
            self._content_cache[path_key] = (signature, content_key)
        return content_key

    def add_sources(self, sources):
        found_paths = collect_image_paths(sources, recursive=self.recursive)
        existing_paths = {source_unique_key(path) for path in self.paths}
        existing_content = set()
        for path in self.paths:
            content_key = self.content_key(path)
            if content_key:
                existing_content.add(content_key)
        added_paths = []
        skipped_duplicate = 0
        for path in found_paths:
            absolute = os.path.abspath(path)
            path_key = source_unique_key(absolute)
            if path_key in existing_paths:
                skipped_duplicate += 1
                continue
            content_key = self.content_key(absolute)
            if content_key and content_key in existing_content:
                skipped_duplicate += 1
                continue
            self.paths.append(absolute)
            added_paths.append(absolute)
            existing_paths.add(path_key)
            if content_key:
                existing_content.add(content_key)
        self.paths.sort(key=dogal_siralama_anahtari)
        return added_paths, skipped_duplicate, len(found_paths)

    def remove(self, path):
        key = source_unique_key(path)
        self.paths[:] = [item for item in self.paths if source_unique_key(item) != key]
        self._content_cache.pop(key, None)

    def clear(self):
        self.paths.clear()
        self._content_cache.clear()

    def deduplicated_paths(self):
        paths = []
        seen_paths = set()
        seen_content = set()
        for path in self.paths:
            path_key = source_unique_key(path)
            content_key = self.content_key(path)
            if path_key in seen_paths or (content_key and content_key in seen_content):
                continue
            seen_paths.add(path_key)
            if content_key:
                seen_content.add(content_key)
            paths.append(path)
        if len(paths) != len(self.paths):
            self.paths[:] = paths
        return list(paths)
