"""Favoritenliste des Add-ons: Telegram-IDs in fester Reihenfolge, nur auf diesem Gerät."""
import json
import os


class Favorites:
    def __init__(self, path):
        self._path = path
        self.ids = self._load()

    def _load(self):
        try:
            with open(self._path, encoding='utf-8') as f:
                data = json.load(f)
        except (OSError, ValueError):
            return []
        if not isinstance(data, list):
            return []
        ids = []
        for item in data:
            if isinstance(item, int) and not isinstance(item, bool) and item not in ids:
                ids.append(item)
        return ids

    def add(self, user_id):
        if user_id not in self.ids:
            self.ids.append(user_id)
            self._save()

    def remove(self, user_id):
        if user_id in self.ids:
            self.ids.remove(user_id)
            self._save()

    def move(self, user_id, step):
        """Verschiebt um step Plätze (negativ = nach vorne), begrenzt auf die Liste."""
        if user_id not in self.ids:
            return
        old = self.ids.index(user_id)
        new = min(max(old + step, 0), len(self.ids) - 1)
        if new != old:
            self.ids.insert(new, self.ids.pop(old))
            self._save()

    def _save(self):
        tmp = self._path + '.tmp'
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(self.ids, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self._path)
