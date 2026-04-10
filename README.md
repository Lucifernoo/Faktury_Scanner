# Faktury Scanner PRO

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Eel](https://img.shields.io/badge/Eel-Desktop%20Web%20UI-4B8BBE?style=for-the-badge&logo=javascript&logoColor=white)
![HTML/CSS/JS](https://img.shields.io/badge/HTML%20%7C%20CSS%20%7C%20JS-Frontend-E34F26?style=for-the-badge&logo=html5&logoColor=white)
![Pandas](https://img.shields.io/badge/Pandas-Data-150458?style=for-the-badge&logo=pandas&logoColor=white)
![Matplotlib](https://img.shields.io/badge/Matplotlib-Charts-11557c?style=for-the-badge)
![pdfplumber](https://img.shields.io/badge/pdfplumber-PDF-CC0000?style=for-the-badge&logo=adobeacrobatreader&logoColor=white)
![PyInstaller](https://img.shields.io/badge/PyInstaller-.exe-FFC832?style=for-the-badge&logo=windows&logoColor=black)
![PyArmor](https://img.shields.io/badge/PyArmor-Protection-2C3E50?style=for-the-badge&logo=shield&logoColor=white)

---

## 📋 Description

**Faktury Scanner PRO** is a modern **desktop** application with a **web-based UI** that automates extraction of structured data from **Ukrainian invoice PDFs**. It pulls **ЄДРПОУ**, **IBAN**, **amounts**, and **counterparty names** from messy document text, applying heuristics and filters to drop boilerplate and “noise” (banks, your own company as buyer, known telecom shortcuts, and similar clutter) so you get clean rows ready for accounting workflows.

---

## ✨ Key Features

- **Beautiful web-based desktop UI** — Chrome app mode via [Eel](https://github.com/python-eel/Eel); responsive layout with HTML/CSS/JS.
- **Bulk PDF processing** — queue multiple files with **real-time** status and progress pushed from Python to the UI.
- **Smart regex & heuristics** — vendor detection (including special handling for cases like Kyivstar / Lifecell), **own-company filter** (ЄДРПОУ and keyword lists from settings), and EDRPOU/IBAN extraction tuned for Ukrainian invoices.
- **Dynamic Excel export** — configurable column order and labels (OpenPyXL), suited for import into tools such as **Finmap** and other accounting stacks.
- **Visual analytics** — vendor charts rendered with **Matplotlib**, delivered to the browser as **Base64** for a lightweight dashboard.
- **Secure & standalone** — ship as a **Windows `.exe`** folder bundle with **PyInstaller**; optional **PyArmor** obfuscation for release builds (`build_app.py`).

---

## ⚙️ How It Works

1. **PDF text** is read with **pdfplumber** (and bundled **Tesseract** paths when packaged). The parser merges pages, normalizes text, and runs layered rules: fixed shortcuts, ТОВ-style vendor candidates, regex for codes and IBAN, and filters that remove your organization’s ЄДРПОУ / name fragments so the **supplier** is identified, not your firm on the invoice.
2. **Frontend ↔ backend** — [Eel](https://github.com/python-eel/Eel) serves the `web/` static assets locally and bridges JavaScript and Python. Functions exposed with **`@eel.expose`** in `main.py` (e.g. folder pick, parse batch, settings, Excel export, analytics) are callable from `web/js/main.js`; the UI receives updates through **`eel.update_ui_status`**, **`eel.update_progress`**, and similar calls from worker threads coordinated with **gevent**.

```text
Browser (HTML/JS)  ←→  Eel WebSocket / HTTP  ←→  Python (main.py + core/)
                                                      ├── core/parser.py
                                                      ├── core/exporter.py
                                                      ├── core/analytics_chart.py
                                                      └── core/config_manager.py
```

---

## 🚀 Installation & Usage

### Run from source

```bash
# Clone the repository
git clone https://github.com/<your-org>/faktury-scanner-pro.git
cd faktury-scanner-pro

# Create and activate a virtual environment (recommended)
python -m venv .venv
.\.venv\Scripts\activate          # Windows
# source .venv/bin/activate       # macOS / Linux

# Install dependencies
pip install -r requirements.txt

# Launch the app
python main.py
```

> **Note:** Settings are stored under `%USERPROFILE%\Documents\FakturyScanner\settings.json` (created on first run / save).

### Windows executable (releases)

Pre-built **protected** Windows binaries are published under **GitHub → Releases** — download the latest **`FakturyScanner`** package or installer, run it, and use the app without installing Python.

Developers can reproduce builds locally:

| Script | Purpose |
|--------|---------|
| `python build_clean.py` | **PyInstaller** `onedir` build + `installer_config.iss` for [Inno Setup](https://jrsoftware.org/isinfo.php) |
| `python build_app.py` | **PyArmor** + PyInstaller (obfuscated) + `setup_script.iss` |

Building requires **PyInstaller** (install separately, e.g. `pip install pyinstaller`) and optionally **Inno Setup** to compile `.iss` files into installers.

---

## 📁 Project Structure

```text
Faktury_Scanner/
├── main.py                 # Application entry: Eel init, @eel.expose API, UI pump
├── requirements.txt      # Python dependencies
├── logo.ico                # App / installer icon
│
├── core/                   # Backend logic
│   ├── __init__.py
│   ├── parser.py           # PDF parsing, ЄДРПОУ / IBAN / vendor heuristics
│   ├── exporter.py         # Excel export (OpenPyXL, configurable columns)
│   ├── analytics_chart.py  # Matplotlib → Base64 for the UI
│   └── config_manager.py   # settings.json load/save, defaults
│
├── web/                    # Frontend (served by Eel)
│   ├── index.html
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── main.js         # Calls into Python via eel.*
│
├── tesseract_bin/          # Bundled OCR binaries (included in PyInstaller datas)
├── build_clean.py          # Plain PyInstaller build + Inno `installer_config.iss`
├── build_app.py            # PyArmor + PyInstaller + Inno `setup_script.iss`
├── installer_config.iss    # Generated by build_clean.py (optional installer)
├── setup_script.iss        # Generated by build_app.py (optional installer)
│
├── anonymize.py            # Utility script (PDF anonymization) — optional tooling
└── README.md
```

Generated artifacts (not committed in a clean repo): `dist/`, `build/`, `FakturyScanner.spec`, `installer_output/`.

---

## 📄 License

Specify your license here (e.g. MIT, proprietary).

---

<p align="center">
  Built with ❤️ for Ukrainian invoice automation
</p>
