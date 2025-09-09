import os
import sys
from typing import Tuple, Iterable

EXCLUDE_DIRS = {
    "venv", ".venv", "env", ".env",
    "__pycache__", ".git", ".mypy_cache",
    ".pytest_cache", ".idea", ".github"
}
# Можно расширить при необходимости


def iter_files(root: str) -> Iterable[str]:
    script_path = os.path.abspath(__file__)
    for dirpath, dirnames, filenames in os.walk(root):
        # Фильтруем директории, чтобы не заходить внутрь исключенных
        dirnames[:] = [
            d for d in dirnames
            if d not in EXCLUDE_DIRS
        ]
        for name in filenames:
            path = os.path.join(dirpath, name)
            if os.path.abspath(path) == script_path:
                continue  # пропускаем сам скрипт
            yield path


def count_lines_in_file(path: str) -> Tuple[int, int]:
    total = non_empty = 0
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                total += 1
                if line.strip():
                    non_empty += 1
    except (OSError, UnicodeDecodeError):
        pass
    return total, non_empty


def main() -> None:
        root = sys.argv[1] if len(sys.argv) > 1 else "."
        total_all = total_non_empty = 0
        results = []  # (path, total, non_empty)
        for file_path in iter_files(root):
            t, ne = count_lines_in_file(file_path)
            total_all += t
            total_non_empty += ne
            results.append((file_path, t, ne))

        # Сортировка по числу всех строк (убывание), затем по пути
        results.sort(key=lambda x: (-x[1], x[0].lower()))

        # Выводим подробности по каждому файлу без сокращений
        print("Файлы по числу строк (убывание):")
        for path, t, ne in results:
            print(f"{t:7d}  {path}  (непустые: {ne})")

        # Итого
        print(f"Все: {total_all}")
        print(f"Непустые: {total_non_empty}")


if __name__ == "__main__":
    main()