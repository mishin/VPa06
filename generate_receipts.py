#!/usr/bin/env python3
"""Интерактивный генератор PDF-чеков из CSV/JSON данных и HTML-шаблонов через WeasyPrint."""

from __future__ import annotations

import csv
import html
import json
import os
import re
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Any


# Базовые директории проекта
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"

# Поддерживаемые расширения файлов
SUPPORTED_DATA_EXTENSIONS = {".csv", ".json"}
SUPPORTED_TEMPLATE_EXTENSIONS = {".html", ".htm"}

# Приоритетные названия полей для идентификатора чека (Invoice ID) и клиента
INVOICE_ID_HINTS = (
    "invoice_id",
    "invoice id",
    "invoice",
    "номер заказа",
    "номер чека",
    "order_id",
    "order id",
    "order",
    "id",
    "номер",
)

CUSTOMER_NAME_HINTS = (
    "фио",
    "покупатель",
    "клиент",
    "customer",
    "client",
    "fio",
    "full_name",
    "fullname",
    "name",
    "имя",
)

# Стили для гарантированной поддержки кириллицы (Roboto / DejaVu Sans) и аккуратной верстки
INJECTED_CSS = """
@import url("https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap");

@page {
    size: A4;
    margin: 20mm;
}

html, body {
    font-family: "Roboto", "DejaVu Sans", "Liberation Sans", "Arial", sans-serif;
    -webkit-font-smoothing: antialiased;
    color: #111111;
}

table {
    border-collapse: collapse;
    margin: 16px auto;
    text-align: center;
    width: 90%;
    max-width: 100%;
    table-layout: fixed;
}

th, td {
    border: 1px solid #333333;
    padding: 8px 12px;
    text-align: center;
    vertical-align: middle;
    word-wrap: break-word;
    overflow-wrap: anywhere;
    word-break: break-word;
}

th {
    background-color: #f2f2f2;
    font-weight: 700;
}
"""


def main() -> int:
    """Основной сценарий работы CLI-генератора чеков."""
    print("=" * 64)
    print("           ГЕНЕРАТОР PDF-ЧЕКОВ (WeasyPrint)")
    print("=" * 64)

    # 1. Сканирование директорий /data и /templates
    data_files = list_directory_files(DATA_DIR, SUPPORTED_DATA_EXTENSIONS)
    template_files = list_directory_files(TEMPLATES_DIR, SUPPORTED_TEMPLATE_EXTENSIONS)

    # 2. Вывод доступных файлов данных и шаблонов при запуске
    print_available_resources(data_files, template_files)

    if not data_files:
        print(f"\n[Ошибка] В директории '{DATA_DIR}' не найдено файлов CSV или JSON.")
        return 1

    if not template_files:
        print(f"\n[Ошибка] В директории '{TEMPLATES_DIR}' не найдено HTML-шаблонов.")
        return 1

    # 3. Выбор файла данных и HTML-шаблона пользователем
    selected_data_path = prompt_file_selection(
        files=data_files,
        prompt_label="Выберите файл с данными (введите номер)",
    )
    if selected_data_path is None:
        return 1

    selected_template_path = prompt_file_selection(
        files=template_files,
        prompt_label="Выберите HTML-шаблон (введите номер)",
    )
    if selected_template_path is None:
        return 1

    # 4. Чтение и парсинг выбранного файла данных (CSV или JSON)
    try:
        records, fieldnames = load_data_file(selected_data_path)
    except Exception as exc:
        print(f"\n[Ошибка] Не удалось прочитать файл '{selected_data_path.name}': {exc}")
        return 1

    if not records:
        print(f"\n[Ошибка] Файл '{selected_data_path.name}' пуст или не содержит корректных записей.")
        return 1

    # 5. Вывод списка доступных чеков по Invoice ID и выбор конкретного чека
    selected_record, invoice_id = prompt_invoice_selection(records, fieldnames)
    if selected_record is None:
        return 1

    # 6. Генерация PDF-документа в директорию /output
    try:
        template_html = selected_template_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"\n[Ошибка] Не удалось прочитать шаблон '{selected_template_path.name}': {exc}")
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_filename = build_pdf_filename(selected_record, invoice_id)
    output_pdf_path = resolve_unique_path(OUTPUT_DIR / output_filename)

    rendered_html = render_template(template_html, selected_record)

    print(f"\nГенерация PDF для чека '{invoice_id}'...")
    generate_pdf_file(
        html_content=rendered_html,
        output_path=output_pdf_path,
        base_url=selected_template_path.parent,
    )
    print(f"[+] PDF успешно сохранен: {output_pdf_path.relative_to(BASE_DIR)}")

    # 7. Автоматическое открытие PDF в системной программе
    open_file_in_viewer(output_pdf_path)
    return 0


def list_directory_files(directory: Path, allowed_extensions: set[str]) -> list[Path]:
    """Возвращает отсортированный список файлов с нужными расширениями из указанной папки."""
    if not directory.exists() or not directory.is_dir():
        return []

    matched_files = [
        item.resolve()
        for item in directory.iterdir()
        if item.is_file() and item.suffix.lower() in allowed_extensions
    ]
    return sorted(matched_files, key=lambda p: p.name.lower())


def print_available_resources(data_files: list[Path], template_files: list[Path]) -> None:
    """Форматированный вывод списков доступных файлов данных и шаблонов при старте."""
    print("\n📂 Доступные файлы с данными (/data):")
    if data_files:
        for idx, path in enumerate(data_files, start=1):
            file_type = path.suffix.upper().lstrip(".")
            print(f"  {idx}. {path.name} [{file_type}]")
    else:
        print("  (нет доступных файлов)")

    print("\n📄 Доступные HTML-шаблоны (/templates):")
    if template_files:
        for idx, path in enumerate(template_files, start=1):
            print(f"  {idx}. {path.name}")
    else:
        print("  (нет доступных шаблонов)")
    print("-" * 64)


def prompt_file_selection(files: list[Path], prompt_label: str) -> Path | None:
    """Запрашивает у пользователя выбор файла по его порядковому номеру."""
    choice = request_numeric_choice(maximum=len(files), message=prompt_label)
    if choice is None:
        return None
    selected = files[choice - 1]
    print(f"  -> Выбран: {selected.name}")
    return selected


def load_data_file(file_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Маршрутизатор чтения файлов данных: парсит CSV или JSON в единую структуру."""
    suffix = file_path.suffix.lower()
    if suffix == ".csv":
        return read_csv_data(file_path)
    if suffix == ".json":
        return read_json_data(file_path)
    raise ValueError(f"Неподдерживаемый формат файла: {suffix}")


def read_csv_data(csv_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Парсит CSV-файл с использованием стандартной библиотеки csv (с поддержкой UTF-8 BOM)."""
    with csv_path.open("r", encoding="utf-8-sig", newline="") as stream:
        # Автоопределение разделителя (запятая или точка с запятой)
        sample = stream.read(4096)
        stream.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel

        reader = csv.DictReader(stream, dialect=dialect)
        if not reader.fieldnames:
            return [], []

        clean_fieldnames = [name.strip() for name in reader.fieldnames if name and name.strip()]
        rows: list[dict[str, str]] = []

        for raw_row in reader:
            normalized = {
                (col or "").strip(): (val or "").strip()
                for col, val in raw_row.items()
                if col is not None and col.strip()
            }
            if any(normalized.values()):
                rows.append(normalized)

        return rows, clean_fieldnames


def read_json_data(json_path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Парсит JSON-файл стандартной библиотекой json и нормализует записи."""
    raw_text = json_path.read_text(encoding="utf-8-sig")
    parsed: Any = json.loads(raw_text)

    # Поддержка разных структур JSON: список объектов или словарь с ключом верхнего уровня
    raw_items: list[Any] = []
    if isinstance(parsed, list):
        raw_items = parsed
    elif isinstance(parsed, dict):
        # Ищем первый вложенный список записей (например, {"invoices": [...]} или {"orders": [...]})
        for value in parsed.values():
            if isinstance(value, list):
                raw_items = value
                break
        else:
            # Если внутри словаря нет списков, считаем сам словарь одиночной записью
            raw_items = [parsed]
    else:
        raise ValueError("JSON должен содержать массив объектов или объект с данными.")

    rows: list[dict[str, str]] = []
    fieldnames_order: list[str] = []

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        normalized_row: dict[str, str] = {}
        for key, val in item.items():
            clean_key = str(key).strip()
            if not clean_key:
                continue
            if clean_key not in fieldnames_order:
                fieldnames_order.append(clean_key)

            # Если значение — список или словарь, сериализуем компактно для читаемости
            if isinstance(val, (list, dict)):
                clean_val = json.dumps(val, ensure_ascii=False)
            elif val is None:
                clean_val = ""
            else:
                clean_val = str(val).strip()

            normalized_row[clean_key] = clean_val

        if any(normalized_row.values()):
            rows.append(normalized_row)

    return rows, fieldnames_order


def prompt_invoice_selection(
    records: list[dict[str, str]],
    fieldnames: list[str],
) -> tuple[dict[str, str] | None, str]:
    """Выводит список доступных чеков по Invoice ID и позволяет выбрать нужный чек."""
    id_field = detect_field_by_hints(fieldnames, INVOICE_ID_HINTS)
    customer_field = detect_field_by_hints(fieldnames, CUSTOMER_NAME_HINTS)

    print("\n🧾 Доступные чеки (Invoice ID) в выбранном файле:")
    print("-" * 64)

    invoice_ids: list[str] = []
    for idx, row in enumerate(records, start=1):
        raw_id = row.get(id_field, "").strip() if id_field else ""
        inv_id = raw_id if raw_id else f"ROW-{idx}"
        invoice_ids.append(inv_id)

        customer_info = f" — {row[customer_field]}" if customer_field and row.get(customer_field) else ""
        print(f"  {idx}. Invoice ID: {inv_id}{customer_info}")

    print("-" * 64)

    while True:
        user_input = input(
            f"\nВыберите чек (введите номер [1-{len(records)}] или сам Invoice ID, q — выход): "
        ).strip()

        if user_input.lower() in {"q", "quit", "exit"}:
            print("Операция отменена пользователем.")
            return None, ""

        # 1. Сначала проверяем точное совпадение по Invoice ID (регистронезависимо)
        for idx, inv_id in enumerate(invoice_ids):
            if user_input.lower() == inv_id.lower():
                return records[idx], inv_id

        # 2. Если не совпало с Invoice ID, проверяем ввод порядкового номера пункта меню
        if user_input.isdigit():
            menu_num = int(user_input)
            if 1 <= menu_num <= len(records):
                return records[menu_num - 1], invoice_ids[menu_num - 1]

        print(
            f"Ошибка: чек '{user_input}' не найден. "
            f"Введите порядковый номер от 1 до {len(records)} или корректный Invoice ID."
        )


def detect_field_by_hints(fieldnames: list[str], hints: tuple[str, ...]) -> str | None:
    """Находит название колонки/ключа по списку приоритетных алиасов без учета регистра."""
    lookup = {name.lower(): name for name in fieldnames}
    # Точное совпадение
    for hint in hints:
        if hint in lookup:
            return lookup[hint]
    # Частичное вхождение (например, 'customer_invoice_id')
    for hint in hints:
        for lower_name, original_name in lookup.items():
            if hint in lower_name:
                return original_name
    return fieldnames[0] if fieldnames else None


def request_numeric_choice(maximum: int, message: str) -> int | None:
    """Безопасный запрос числа из диапазона [1..maximum] в консоли."""
    while True:
        user_input = input(f"\n{message} [1-{maximum}, q — выход]: ").strip().lower()
        if user_input in {"q", "quit", "exit"}:
            print("Операция отменена пользователем.")
            return None
        if not user_input.isdigit():
            print("Ошибка: введите корректный номер из списка.")
            continue

        value = int(user_input)
        if 1 <= value <= maximum:
            return value
        print(f"Ошибка: введите число от 1 до {maximum}.")


def render_template(template_content: str, record: dict[str, str]) -> str:
    """Подставляет данные чека в HTML-шаблон с экранированием спецсимволов и добавляет CSS."""
    rendered = template_content

    # Создаем также базовые алиасы, чтобы шаблоны с {{invoice_id}} или {{Номер заказа}}
    # гарантированно заполнялись при разных именах колонок
    enriched_record = dict(record)
    id_field = detect_field_by_hints(list(record.keys()), INVOICE_ID_HINTS)
    if id_field and record.get(id_field):
        enriched_record.setdefault("invoice_id", record[id_field])
        enriched_record.setdefault("Номер заказа", record[id_field])

    for key, value in enriched_record.items():
        escaped_val = html.escape(str(value))
        # Поддерживаем синтаксис {{ key }}, {{key}}, {key} в разных регистрах
        for key_variant in (key, key.lower(), key.upper()):
            patterns = (
                f"{{{{{key_variant}}}}}",
                f"{{{{ {key_variant} }}}}",
                f"{{{key_variant}}}",
            )
            for token in patterns:
                rendered = rendered.replace(token, escaped_val)

    style_block = f"<style>\n{INJECTED_CSS.strip()}\n</style>\n"
    head_match = re.search(r"(?i)<head[^>]*>", rendered)
    if head_match:
        insert_pos = head_match.end()
        return rendered[:insert_pos] + "\n" + style_block + rendered[insert_pos:]
    return f"<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'>{style_block}</head><body>{rendered}</body></html>"


def sanitize_filename(name: str) -> str:
    """Очищает строку от символов, запрещенных в файловых системах Windows и macOS."""
    cleaned = re.sub(r'[\\/*?:"<>|\r\n\t]+', "_", name).strip(" ._")
    return cleaned or "unnamed"


def build_pdf_filename(record: dict[str, str], invoice_id: str) -> str:
    """Формирует имя выходного PDF-файла на основе Invoice ID."""
    safe_id = sanitize_filename(invoice_id)
    return f"receipt_{safe_id}.pdf"


def resolve_unique_path(target_path: Path) -> Path:
    """Предотвращает перезапись существующего файла, добавляя числовой индекс при совпадении."""
    if not target_path.exists():
        return target_path

    stem = target_path.stem
    suffix = target_path.suffix
    parent = target_path.parent
    counter = 2

    while True:
        candidate = parent / f"{stem}_{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def generate_pdf_file(html_content: str, output_path: Path, base_url: Path) -> None:
    """Генерирует PDF-файл из строки HTML с помощью библиотеки WeasyPrint."""
    try:
        from weasyprint import HTML
    except ImportError:
        print("\n[Критическая ошибка] Библиотека WeasyPrint не установлена.")
        print("Установите её командой: pip install weasyprint")
        sys.exit(1)

    HTML(string=html_content, base_url=str(base_url)).write_pdf(str(output_path))


def open_file_in_viewer(file_path: Path) -> None:
    """Кроссплатформенно открывает сгенерированный PDF-документ в системной программе (Windows / macOS / Linux)."""
    resolved_path = file_path.resolve()
    print(f"Открытие документа в системной программе просмотра: {resolved_path.name}")

    try:
        if sys.platform.startswith("win"):
            os.startfile(str(resolved_path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(resolved_path)], check=False)
        else:
            subprocess.run(["xdg-open", str(resolved_path)], check=False)
    except OSError:
        webbrowser.open(resolved_path.as_uri())


if __name__ == "__main__":
    sys.exit(main())