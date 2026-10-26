#!/usr/bin/env python3
"""Интерактивная генерация PDF-чеков из HTML-шаблона и CSV (WeasyPrint)."""

from __future__ import annotations

import csv
import html
import os
import re
import subprocess
import sys
import webbrowser
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIRS = (BASE_DIR / "templates", BASE_DIR)
DATA_DIRS = (BASE_DIR / "data", BASE_DIR)
OUTPUT_DIR = BASE_DIR / "output"

KEY_FIELD_HINTS = (
    "фио",
    "fio",
    "full_name",
    "fullname",
    "name",
    "имя",
    "заказ",
    "номер заказа",
    "order",
    "order_id",
    "номер",
    "id",
)

INJECTED_CSS = """
@import url("https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap");

html, body {
    font-family: "Roboto", "Liberation Sans", "DejaVu Sans", sans-serif;
}

table {
    border: 1px solid black;
    border-collapse: collapse;
    margin: 0 auto;
    text-align: center;
    word-wrap: break-word;
    max-width: 100%;
}

th, td {
    border: 1px solid black;
    padding: 6px 10px;
    text-align: center;
    word-wrap: break-word;
    max-width: 100%;
}
"""


def main() -> int:
    print("Генератор PDF-чеков")
    print(f"Рабочая папка: {BASE_DIR}\n")

    templates = collect_files(TEMPLATE_DIRS, ".html")
    csv_files = collect_files(DATA_DIRS, ".csv")

    template_path = choose_from_list(templates, "HTML-шаблон")
    if template_path is None:
        return 1

    csv_path = choose_from_list(csv_files, "CSV-файл с данными")
    if csv_path is None:
        return 1

    rows, fieldnames = read_csv_rows(csv_path)
    if not rows:
        print("В выбранном CSV нет записей.")
        return 1

    selected_rows = choose_records(rows, fieldnames)
    if selected_rows is None:
        return 1

    template_html = template_path.read_text(encoding="utf-8")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    generated: list[Path] = []
    for row_number, row in selected_rows:
        pdf_path = unique_output_path(row_number)
        html_doc = render_html(template_html, row)
        write_pdf(html_doc, pdf_path, base_url=template_path.parent)
        generated.append(pdf_path)
        print(f"Создан файл: {pdf_path}")

    if len(generated) == 1:
        open_generated_file(generated[0])
        print("PDF открыт в программе просмотра по умолчанию.")
    else:
        open_generated_file(OUTPUT_DIR)
        print(f"Сгенерировано файлов: {len(generated)}. Открыта папка {OUTPUT_DIR}")

    return 0


def collect_files(directories: tuple[Path, ...], suffix: str) -> list[Path]:
    found: list[Path] = []
    seen: set[Path] = set()
    for directory in directories:
        if not directory.is_dir():
            continue
        for path in sorted(directory.iterdir()):
            if not path.is_file():
                continue
            if path.suffix.lower() != suffix:
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            found.append(resolved)
    return found


def choose_from_list(paths: list[Path], title: str) -> Path | None:
    if not paths:
        print(f"Не найдены файлы для выбора: {title}.")
        print("Положите .html в ./templates (или текущую папку) и .csv в ./data (или текущую папку).")
        return None

    print(f"Доступные файлы ({title}):")
    for index, path in enumerate(paths, start=1):
        try:
            display = path.relative_to(BASE_DIR)
        except ValueError:
            display = path
        print(f"  {index}. {display}")

    choice = prompt_index(len(paths), f"Выберите {title}")
    if choice is None:
        return None
    return paths[choice - 1]


def read_csv_rows(csv_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            return [], []
        fieldnames = [name.strip() for name in reader.fieldnames if name and name.strip()]
        rows: list[dict[str, str]] = []
        for raw in reader:
            row = {
                (key or "").strip(): (value or "").strip()
                for key, value in raw.items()
                if key is not None
            }
            if any(row.values()):
                rows.append(row)
        return rows, fieldnames


def choose_records(
    rows: list[dict[str, str]],
    fieldnames: list[str],
) -> list[tuple[int, dict[str, str]]] | None:
    key_field = detect_key_field(fieldnames)
    print("\nДоступные записи:")
    print("  0. Все записи")
    for index, row in enumerate(rows, start=1):
        label = row.get(key_field, "") if key_field else ""
        if not label:
            label = next((value for value in row.values() if value), "—")
        extra = f" ({key_field}: {label})" if key_field else f" ({label})"
        print(f"  {index}. Строка {index}{extra}")

    choice = prompt_index(len(rows), "Выберите запись (0 — все)", allow_zero=True)
    if choice is None:
        return None
    if choice == 0:
        return [(index, row) for index, row in enumerate(rows, start=1)]
    return [(choice, rows[choice - 1])]


def detect_key_field(fieldnames: list[str]) -> str | None:
    lowered = {name.lower(): name for name in fieldnames}
    for hint in KEY_FIELD_HINTS:
        if hint in lowered:
            return lowered[hint]
    return fieldnames[0] if fieldnames else None


def prompt_index(max_value: int, message: str, allow_zero: bool = False) -> int | None:
    minimum = 0 if allow_zero else 1
    while True:
        raw = input(f"\n{message} [{minimum}-{max_value}, q — выход]: ").strip().lower()
        if raw in {"q", "quit", "exit"}:
            print("Выход.")
            return None
        if not raw:
            print("Введите номер из списка.")
            continue
        if not raw.isdigit():
            print("Нужно целое число.")
            continue
        value = int(raw)
        if value < minimum or value > max_value:
            print(f"Номер должен быть от {minimum} до {max_value}.")
            continue
        return value


def render_html(template_html: str, row: dict[str, str]) -> str:
    filled = substitute_placeholders(template_html, row)
    return inject_styles(filled)


def substitute_placeholders(template_html: str, row: dict[str, str]) -> str:
    result = template_html
    for key, value in row.items():
        safe = html.escape(value)
        for token in placeholder_tokens(key):
            result = result.replace(token, safe)
    return result


def placeholder_tokens(key: str) -> tuple[str, ...]:
    return (
        f"{{{{{key}}}}}",
        f"{{{{{key.lower()}}}}}",
        f"{{{{{key.upper()}}}}}",
        f"{{{key}}}",
        f"{{{key.lower()}}}",
        f"{{{key.upper()}}}",
    )


def inject_styles(document: str) -> str:
    style_block = f"<style>\n{INJECTED_CSS.strip()}\n</style>\n"
    match = re.search(r"(?i)<head[^>]*>", document)
    if match:
        insert_at = match.end()
        return document[:insert_at] + "\n" + style_block + document[insert_at:]
    if re.search(r"(?i)<html[^>]*>", document):
        return re.sub(r"(?i)<html[^>]*>", lambda m: m.group(0) + "\n<head>\n" + style_block + "</head>\n", document, count=1)
    return (
        "<!DOCTYPE html>\n<html>\n<head>\n"
        + style_block
        + "</head>\n<body>\n"
        + document
        + "\n</body>\n</html>\n"
    )


def unique_output_path(row_number: int) -> Path:
    candidate = OUTPUT_DIR / f"receipt_{row_number}.pdf"
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        candidate = OUTPUT_DIR / f"receipt_{row_number}_{suffix}.pdf"
        if not candidate.exists():
            return candidate
        suffix += 1


def write_pdf(html_doc: str, pdf_path: Path, base_url: Path) -> None:
    try:
        from weasyprint import HTML
    except ImportError:
        print("Не установлена библиотека WeasyPrint.")
        print("Установите её командой: pip install weasyprint")
        sys.exit(1)
    HTML(string=html_doc, base_url=str(base_url)).write_pdf(str(pdf_path))


def open_generated_file(path: Path) -> None:
    target = str(path)
    try:
        if sys.platform.startswith("win"):
            os.startfile(target)  # type: ignore[attr-defined]
            return
        if sys.platform == "darwin":
            subprocess.run(["open", target], check=False)
            return
        subprocess.run(["xdg-open", target], check=False)
    except OSError:
        webbrowser.open(path.resolve().as_uri())


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nПрервано пользователем.")
        raise SystemExit(130)
