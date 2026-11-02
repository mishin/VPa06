# 🧾 Генератор PDF-чеков

Небольшой интерактивный CLI-инструмент на Python: выбирает CSV- или JSON-файл с заказами, подставляет данные в HTML-шаблон, создаёт PDF-чек и открывает его в программе просмотра документов.

## Возможности

- Читает данные из файлов `.csv` и `.json` в папке `data`.
- Находит HTML-шаблоны `.html` и `.htm` в папке `templates`.
- Показывает меню выбора данных, шаблона и конкретного чека.
- Подставляет значения в шаблон с экранированием HTML-символов.
- Формирует PDF с помощью [WeasyPrint](https://weasyprint.org/), добавляет стили для таблиц и шрифты с поддержкой кириллицы.
- Сохраняет результат в `output` и автоматически открывает его.

## Структура проекта

```text
receipt-generator/
├── data/
│   ├── orders.csv             # Пример заказов с русскими заголовками
│   └── products.csv           # Пример с полями invoice_id, product, price, qty
├── templates/
│   ├── receipt.html           # Шаблон чека по заказу
│   └── product_receipt.html   # Шаблон с плейсхолдерами из задания
├── output/                    # Сюда сохраняются готовые PDF
├── generate_receipts.py       # CLI-скрипт
└── requirements.txt
```

## Требования

- Python 3.10 или новее.
- WeasyPrint и его системные библиотеки. В Windows для работы WeasyPrint требуется GTK; инструкции для других ОС приведены в [официальной документации WeasyPrint](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html).

## Установка

### Windows

Откройте PowerShell в корневой папке проекта и создайте виртуальное окружение:

```powershell
py -3.12 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r .\requirements.txt
```

Чтобы установить GTK, установите [MSYS2](https://www.msys2.org/), откройте терминал **MSYS2 MINGW64** и выполните:

```bash
pacman -S mingw-w64-x86_64-gtk3
```

Затем в PowerShell добавьте библиотеки MSYS2 в `PATH` текущего окна и запустите скрипт:

```powershell
$env:PATH = "C:\msys64\mingw64\bin;$env:PATH"
python .\generate_receipts.py
```

Если MSYS2 установлен в другом месте, замените путь `C:\msys64`. Python-пакеты устанавливайте из PowerShell через Python виртуального окружения, а не через Python из MSYS2.

### macOS

Установите системную библиотеку Pango через [Homebrew](https://brew.sh/), затем создайте окружение и установите зависимости проекта:

```bash
brew install pango
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Запуск

Находясь в корневой папке проекта и активировав виртуальное окружение, выполните:

**Windows (PowerShell):**

```powershell
python .\generate_receipts.py
```

**macOS:**

```bash
python generate_receipts.py
```

Далее выберите номер CSV/JSON-файла, номер HTML-шаблона и чек из предложенного списка. Для выхода из меню введите `q`. Созданный PDF появится в папке `output`; если файл с таким именем уже существует, скрипт добавит к имени порядковый номер, чтобы не перезаписывать его.

## Данные и шаблоны

CSV должен содержать строку заголовков и записи заказов. Для примера `products.csv` используются такие поля:

```csv
invoice_id,product,price,qty
INV-001,Механическая клавиатура,6500 ₽,1
```

В HTML-шаблоне можно использовать плейсхолдеры, совпадающие с заголовками полей. Например, в `product_receipt.html`:

```html
<td>{{ product }}</td>
<td>{{ price }}</td>
<td>{{ qty }}</td>
```

Для выбора чека скрипт определяет поле идентификатора по распространённым названиям, включая `invoice_id`, `order_id`, `id` и «Номер заказа». JSON поддерживает массив объектов, одиночный объект или объект, содержащий список записей.

## Составной промпт

Промпт, использованный для постановки задачи генератору кода, сохранён в файле [«Обновленный текст промпта для генерации чеков.md»](./Обновленный%20текст%20промпта%20для%20генерации%20чеков.md).
