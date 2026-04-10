"""
Анонімізація PDF для демо / уникнення комерційної таємниці та GDPR.
Замінює типові реквізити (IBAN, ЄДРПОУ-подібні коди, телефони, email) на фейкові.
Оригінали не змінюються — результат у папці anonymized_pdf/
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import fitz  # PyMuPDF

# Фейкові заміни (однакові для всіх файлів — без «реальних» даних)
FAKE_IBAN = "UA000000000000000000000000000"
FAKE_CODE_8 = "12345678"
FAKE_CODE_10 = "1234567890"
FAKE_PHONE = "000000000"
FAKE_EMAIL = "anon@example.test"

# Патерни для пошуку в тексті сторінки (суцільні рядки)
TEXT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"UA[0-9A-Z]{27}", re.IGNORECASE), FAKE_IBAN),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), FAKE_EMAIL),
    (re.compile(r"(?:\+?38)?0[0-9]{9}\b"), FAKE_PHONE),
    (re.compile(r"\b380[0-9]{9}\b"), FAKE_PHONE),
]


def _inflate_rect(r: fitz.Rect, pad: float = 1.0) -> fitz.Rect:
    return fitz.Rect(r.x0 - pad, r.y0 - pad, r.x1 + pad, r.y1 + pad)


def _fit_fontsize(rect: fitz.Rect) -> float:
    h = rect.height
    return max(5.0, min(12.0, h * 0.72))


def _paint_replace(page: fitz.Page, rect: fitz.Rect, new_text: str) -> None:
    rr = _inflate_rect(rect, 0.8)
    page.draw_rect(rr, color=(1, 1, 1), fill=(1, 1, 1))
    fs = _fit_fontsize(rr)
    try:
        page.insert_textbox(
            rr,
            new_text,
            fontsize=fs,
            color=(0, 0, 0),
            align=fitz.TEXT_ALIGN_LEFT,
        )
    except Exception:
        page.insert_text(rr.tl, new_text, fontsize=fs, color=(0, 0, 0))


def _search_variants(page: fitz.Page, s: str) -> list[fitz.Rect]:
    found: list[fitz.Rect] = []
    for candidate in (s, s.upper(), s.lower()):
        try:
            found.extend(page.search_for(candidate))
        except Exception:
            pass
    # Унікальні прямокутники (наближено)
    seen: set[tuple[float, float, float, float]] = set()
    out: list[fitz.Rect] = []
    for r in found:
        key = (round(r.x0, 1), round(r.y0, 1), round(r.x1, 1), round(r.y1, 1))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def anonymize_page(page: fitz.Page) -> None:
    # 1) Суцільні збіги в тексті сторінки → search_for (IBAN, email, телефон)
    raw_text = page.get_text("text") or ""
    seen_strings: set[str] = set()
    for rx, repl in TEXT_PATTERNS:
        for m in rx.finditer(raw_text):
            s = m.group(0).strip()
            if len(s) < 3 or s in seen_strings:
                continue
            seen_strings.add(s)
            for rect in _search_variants(page, s):
                _paint_replace(page, rect, repl)

    # 2) Покомпонентно: слова з get_text("words") — коди, телефони, email у одному токені
    words = page.get_text("words") or []
    for w in words:
        if len(w) < 5:
            continue
        x0, y0, x1, y1 = w[0], w[1], w[2], w[3]
        token = (w[4] or "").strip()
        if not token:
            continue
        rect = fitz.Rect(x0, y0, x1, y1)
        tl = token.lower().replace("\u00a0", " ").strip()

        replacement: str | None = None
        if re.fullmatch(r"UA[0-9A-Z]{27}", tl, re.I):
            replacement = FAKE_IBAN
        elif re.fullmatch(r"\d{8}", token):
            replacement = FAKE_CODE_8
        elif re.fullmatch(r"\d{10}", token):
            replacement = FAKE_CODE_10
        elif re.fullmatch(r"0[0-9]{9}", token):
            replacement = FAKE_PHONE
        elif re.fullmatch(r"380[0-9]{9}", token):
            replacement = FAKE_PHONE
        elif "@" in token and "." in token and re.fullmatch(r"\S+@\S+\.\S+", token):
            replacement = FAKE_EMAIL

        if replacement:
            _paint_replace(page, rect, replacement)


def anonymize_pdf(input_path: str, output_path: str) -> None:
    doc = fitz.open(input_path)
    try:
        for page in doc:
            anonymize_page(page)
        os.makedirs(os.path.dirname(os.path.abspath(output_path)) or ".", exist_ok=True)
        doc.save(
            output_path,
            garbage=4,
            deflate=True,
            clean=True,
        )
    finally:
        doc.close()


def collect_pdfs(root: Path) -> list[Path]:
    dirs = [root, root / "invoices"]
    out: list[Path] = []
    for d in dirs:
        if not d.is_dir():
            continue
        out.extend(sorted(d.glob("*.pdf")))
    # Унікальні шляхи
    uniq: dict[str, Path] = {}
    for p in out:
        uniq[str(p.resolve())] = p
    return list(uniq.values())


def main() -> None:
    root = Path(__file__).resolve().parent
    out_dir = root / "anonymized_pdf"
    out_dir.mkdir(parents=True, exist_ok=True)

    pdfs = collect_pdfs(root)
    if not pdfs:
        raise SystemExit(
            "Не знайдено жодного .pdf у корені проєкту або в папці invoices/"
        )

    for src in pdfs:
        # Не обробляємо вже анонімізовані копії у цій папці
        if "anonymized_pdf" in src.parts:
            continue
        stem = src.stem
        dst = out_dir / f"{stem}_anon.pdf"
        print(f"Обробка: {src.name} -> {dst.name}")
        try:
            anonymize_pdf(str(src), str(dst))
        except Exception as e:
            print(f"  Помилка: {e}")

    print(f"\nГотово. Файли збережено в: {out_dir}")


if __name__ == "__main__":
    main()
