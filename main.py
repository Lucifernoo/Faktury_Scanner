"""Точка входу: веб-інтерфейс на Eel."""

from __future__ import annotations

import os
import queue
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Any, Final

import eel
import gevent

from core.analytics_chart import build_vendors_chart_png_base64
from core.config_manager import (
    DEFAULT_SETTINGS,
    ConfigManager,
    parse_export_columns_value,
    parse_lines_from_settings_value,
)
from core.exporter import ExcelExporter
from core.parser import InvoiceParseSkipError, InvoiceParser

APP_DISPLAY_NAME: Final[str] = "Faktury Scanner PRO"
APP_VERSION: Final[str] = "1.1.1"


def _project_root() -> str:
    """Корінь проєкту (тека, де лежить ``main.py``) — для ``web/``, ``tesseract_bin/`` у режимі розробки."""
    return os.path.dirname(os.path.abspath(__file__))


def _resource_root() -> str:
    """
    Ресурси, упаковані в onefile: ``web/``, ``tesseract_bin/`` у ``sys._MEIPASS``.
    У режимі розробки — той самий корінь, що й ``_project_root``.
    """
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return meipass
    return _project_root()


def _configure_tesseract_bundle_paths() -> None:
    """``PATH`` / ``TESSDATA_PREFIX`` для бінарників з ``tesseract_bin`` у бандлі."""
    root = _resource_root()
    tess_dir = os.path.join(root, "tesseract_bin")
    if not os.path.isdir(tess_dir):
        return
    exe_tess = os.path.join(tess_dir, "tesseract.exe")
    if os.path.isfile(exe_tess):
        os.environ["PATH"] = tess_dir + os.pathsep + os.environ.get("PATH", "")
    tessdata = os.path.join(tess_dir, "tessdata")
    if os.path.isdir(tessdata):
        os.environ["TESSDATA_PREFIX"] = os.path.abspath(tessdata)


_configure_tesseract_bundle_paths()
_web_dir = os.path.join(_resource_root(), "web")
eel.init(_web_dir)


@eel.expose
def get_app_meta() -> dict[str, str]:
    """Метадані застосунку для UI (єдине джерело версії з бекенду)."""
    return {
        "version": APP_VERSION,
        "display_name": APP_DISPLAY_NAME,
    }


_status_queue: queue.Queue[tuple[str, str]] = queue.Queue()
_progress_queue: queue.Queue[float] = queue.Queue()
_current_data: list[dict[str, Any]] = []
_current_data_lock = threading.Lock()


def _notify_progress(pct: float) -> None:
    """``pct`` у діапазоні 0..100 або ``-1`` для скидання (неактивна смуга)."""
    _progress_queue.put(float(pct))


def _pump_ui_updates() -> None:
    """Greenlet: передає статуси та прогрес з фонових потоків у JS без блокування gevent-loop."""
    while True:
        gevent.sleep(0.05)
        progress_batch: list[float] = []
        try:
            while True:
                progress_batch.append(_progress_queue.get_nowait())
        except queue.Empty:
            pass
        for p in progress_batch:
            try:
                eel.update_progress(p)(lambda _ret=None: None)
            except Exception:
                pass
        batch: list[tuple[str, str]] = []
        try:
            while True:
                batch.append(_status_queue.get_nowait())
        except queue.Empty:
            pass
        for state, filename in batch:
            try:
                eel.update_ui_status(state, filename)(lambda _ret=None: None)
            except Exception:
                pass


def _notify_export_state(enabled: bool) -> None:
    try:
        eel.set_export_enabled(bool(enabled))(lambda _ret=None: None)
    except Exception:
        pass


def _process_folder_worker(folder_path: str) -> None:
    root = Path(folder_path)
    if not root.is_dir():
        _status_queue.put(("Error", str(root)))
        _notify_progress(-1.0)
        return

    pdfs = sorted(root.glob("*.pdf"))
    if not pdfs:
        _status_queue.put(("Error", "(немає PDF у папці)"))
        with _current_data_lock:
            _current_data.clear()
        _notify_export_state(False)
        _notify_progress(-1.0)
        return

    with _current_data_lock:
        _current_data.clear()
    _notify_export_state(False)

    parser = InvoiceParser()
    rows = parser.process_directory(
        str(root),
        ignore_company_edrpou="",
        status_sink=lambda s, f: _status_queue.put((s, f)),
    )

    with _current_data_lock:
        _current_data.clear()
        _current_data.extend(rows)

    _notify_export_state(len(rows) > 0)
    _notify_progress(-1.0)


@eel.expose
def select_folder() -> str:
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askdirectory()
    root.destroy()
    return path if path else ""


@eel.expose
def select_file() -> str:
    """Лише діалог вибору одного PDF — без парсингу."""
    root = tk.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        title="Оберіть рахунок (PDF)",
        filetypes=[("PDF", "*.pdf")],
        defaultextension=".pdf",
    )
    root.destroy()
    return path if path else ""


def _process_single_file_worker(file_path: str) -> None:
    """Парсинг одного PDF у буфер для Excel."""
    path = (file_path or "").strip()
    if not path or not os.path.isfile(path):
        _status_queue.put(("Error", path or "(файл не знайдено)"))
        _notify_progress(-1.0)
        return

    basename = os.path.basename(path)
    with _current_data_lock:
        _current_data.clear()
    _notify_export_state(False)
    _notify_progress(0.0)
    _status_queue.put(("Parsing", basename))

    try:
        parser = InvoiceParser()
        result = parser.process_pdf(path, ignore_company_edrpou="")
        row = dict(result)
        row["_source_file"] = basename
        with _current_data_lock:
            _current_data.append(row)
        _notify_export_state(True)
        _status_queue.put(("Success", basename))
        _notify_progress(100.0)
        _notify_progress(-1.0)
    except InvoiceParseSkipError:
        _status_queue.put(("Error", f"{basename} (немає валідної суми)"))
        _notify_progress(-1.0)
    except Exception:
        _status_queue.put(("Error", basename))
        _notify_progress(-1.0)


@eel.expose
def run_task(path: str, task_type: str) -> None:
    """
    Універсальний запуск обробки: ``task_type`` — ``folder`` або ``file``.
    """
    p = (path or "").strip()
    tt = (task_type or "").strip().lower()
    if not p:
        _status_queue.put(("Error", "(нічого не обрано)"))
        return
    if tt == "file":
        thread = threading.Thread(target=_process_single_file_worker, args=(p,), daemon=True)
    elif tt == "folder":
        thread = threading.Thread(target=_process_folder_worker, args=(p,), daemon=True)
    else:
        _status_queue.put(("Error", f"(невідомий тип задачі: {task_type})"))
        return
    thread.start()


@eel.expose
def start_processing(folder_path: str) -> None:
    """Зворотна сумісність: те саме, що ``run_task(folder_path, \"folder\")``."""
    run_task(folder_path, "folder")


def _export_worker() -> None:
    with _current_data_lock:
        snapshot = [dict(r) for r in _current_data]
    if not snapshot:
        _status_queue.put(("Error", "(немає даних для експорту)"))
        return

    cfg = ConfigManager().load()
    cols = list(cfg.get("export_columns") or DEFAULT_SETTINGS["export_columns"])
    exporter = ExcelExporter(ConfigManager())

    try:
        for item in snapshot:
            data = {k: v for k, v in item.items() if not str(k).startswith("_")}
            exporter.append_to_excel(data, export_columns=cols)
        n = len(snapshot)
        with _current_data_lock:
            _current_data.clear()
        _notify_export_state(False)
        try:
            eel.on_registry_saved(int(n))(lambda _ret=None: None)
        except Exception:
            pass
    except PermissionError as e:
        _status_queue.put(("Error", str(e)))
    except OSError:
        _status_queue.put(("Error", "Не вдалося зберегти Excel (доступ або диск)."))
    except Exception as e:
        _status_queue.put(("Error", f"Помилка збереження: {e}"))


@eel.expose
def export_to_excel() -> None:
    thread = threading.Thread(target=_export_worker, daemon=True)
    thread.start()


@eel.expose
def get_current_parsed_data() -> list[dict[str, Any]]:
    """Знімок рядків для експорту (те саме, що у внутрішньому буфері після парсингу)."""
    with _current_data_lock:
        return [dict(r) for r in _current_data]


def _ask_save_excel_path_worker(result_q: queue.Queue[tuple[str, str | None]]) -> None:
    """
    Tk «Зберегти як…» у окремому потоці: callback Eel працює під gevent,
    інакше діалог часто не з’являється або ховається за вікном Chrome.
    """
    root: tk.Tk | None = None
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            root.update_idletasks()
            root.lift()
            root.focus_force()
        except tk.TclError:
            pass

        docs = os.path.join(os.path.expanduser("~"), "Documents")
        initialdir = docs if os.path.isdir(docs) else os.path.expanduser("~")

        path = filedialog.asksaveasfilename(
            parent=root,
            initialdir=initialdir,
            initialfile="Реєстр_рахунків.xlsx",
            title="Зберегти реєстр як...",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx")],
        )
        if path:
            result_q.put(("ok", str(path)))
        else:
            result_q.put(("cancel", None))
    except Exception as exc:
        result_q.put(("error", str(exc)))
    finally:
        if root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass


def _ask_save_excel_path_blocking() -> tuple[str, str | None]:
    """Повертає (\"ok\", шлях) | (\"cancel\", None) | (\"error\", текст)."""
    result_q: queue.Queue[tuple[str, str | None]] = queue.Queue(maxsize=1)
    th = threading.Thread(target=_ask_save_excel_path_worker, args=(result_q,), daemon=True)
    th.start()
    th.join(timeout=300)
    if th.is_alive():
        return (
            "error",
            "Діалог збереження не відповів учасно. Закрийте зайві вікна та спробуйте ще раз.",
        )
    try:
        return result_q.get_nowait()
    except queue.Empty:
        return ("error", "Не вдалося отримати результат діалогу збереження.")


@eel.expose
def save_to_excel_with_dialog(parsed_data: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Діалог «Зберегти як…», запис через ``ExcelExporter(..., file_path=...)``.
    ``parsed_data`` — список словників (як із ``get_current_parsed_data``).
    """
    if not isinstance(parsed_data, list) or not parsed_data:
        return {"ok": False, "error": "no_data"}

    kind, payload = _ask_save_excel_path_blocking()
    if kind == "cancel":
        return {"ok": False, "error": "user_canceled"}
    if kind == "error":
        return {"ok": False, "error": payload or "dialog_error"}
    if kind != "ok" or not payload:
        return {"ok": False, "error": "user_canceled"}

    file_path = payload

    cfg = ConfigManager().load()
    cols = list(cfg.get("export_columns") or DEFAULT_SETTINGS["export_columns"])
    exporter = ExcelExporter(ConfigManager(), file_path=file_path)

    try:
        for item in parsed_data:
            data = {k: v for k, v in dict(item).items() if not str(k).startswith("_")}
            exporter.append_to_excel(data, export_columns=cols)
        with _current_data_lock:
            _current_data.clear()
        _notify_export_state(False)
        return {"ok": True, "path": file_path}
    except PermissionError as e:
        return {"ok": False, "error": str(e)}
    except OSError:
        return {"ok": False, "error": "Не вдалося зберегти Excel (доступ або диск)."}
    except Exception as e:
        return {"ok": False, "error": f"Помилка збереження: {e}"}


@eel.expose
def get_settings() -> dict[str, Any]:
    """Поточний конфіг для веб-форми (те саме, що ``ConfigManager().load()``)."""
    return ConfigManager().load()


@eel.expose
def open_settings() -> dict[str, Any]:
    """Зворотна сумісність з JS; еквівалент ``get_settings()``."""
    return get_settings()


@eel.expose
def save_settings(payload: dict[str, Any]) -> dict[str, Any]:
    """Збереження з форми: пробіли та порожні рядки очищаються у ``parse_*``."""
    try:
        cm = ConfigManager()
        cur = cm.load()
        if "my_edrpou_list" in payload:
            cur["my_edrpou_list"] = parse_lines_from_settings_value(payload.get("my_edrpou_list"))
        if "my_names_list" in payload:
            cur["my_names_list"] = parse_lines_from_settings_value(payload.get("my_names_list"))
        if "export_columns" in payload:
            cur["export_columns"] = parse_export_columns_value(payload.get("export_columns"))
        cm.save(cur)
        return {"ok": True}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@eel.expose
def show_analytics() -> dict[str, Any]:
    """PNG графіка base64 для відображення у веб-модалці."""
    b64, err = build_vendors_chart_png_base64()
    if err:
        return {"ok": False, "error": err}
    return {"ok": True, "image_base64": b64}


if __name__ == "__main__":
    ConfigManager().load()
    eel.spawn(_pump_ui_updates)
    # У режимі Chrome favicon задається через <link rel="icon"> у web/index.html
    # та файл web/favicon.ico (статика з каталогу eel.init); окремого параметра icon у Eel немає.
    # port=0 — вільний порт від ОС (інакше WinError 10048, якщо 8000 зайнятий).
    eel.start(
        "index.html",
        mode="chrome",
        cmdline_args=["--disable-http-cache"],
        app_mode=True,
        port=0,
    )
