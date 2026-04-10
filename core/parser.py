from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, Final

import pdfplumber

from core.config_manager import ConfigManager

# Відомі контрагенти за ЄДРПОУ / РНОКПП (повні або довгі коди у тексті PDF)
_EDRPOU_TO_VENDOR: Final[dict[str, str]] = {
    "216738326059": 'ПрАТ "Київстар"',
}

# Службові ролі в рахунку — не є назвою контрагента
_VENDOR_STOP_WORDS: Final[tuple[str, ...]] = (
    "Одержувач",
    "Отримувач",
    "Постачальник",
    "Продавець",
)


class InvoiceParseSkipError(ValueError):
    """Рахунок без валідної суми (> 0) — не додавати до реєстру."""


class InvoiceParser:
    """
    Парсинг українського рахунку з PDF через pdfplumber: контрагент, ЄДРПОУ, IBAN, сума.
    ЄДРПОУ та назва «своєї» компанії (settings.json) виключаються — лишається контрагент-продавець.
    """

    KNOWN_VENDORS_REQUISITES: Final[dict[str, dict[str, str]]] = {
        'ПрАТ "Київстар"': {
            "edrpou": "21673832",
            "iban": "UA963003350000000260002183425",
        },
    }

    # «Платіжні реквізити» / «п/р» — вікно 300 символів для IBAN та ЄДРПОУ
    _PAYMENT_REQ_ANCHOR = re.compile(r"(?iu)(?:Платіжні\s+реквізити|п/р)")

    # Без гілки «Товариство … текст до коми» — її замінює _extract_vendor_tov_priority (кавички / наступний рядок)
    _VENDOR_NAME = re.compile(
        r"(?:"
        r"Товариство\s+з\s+обмеженою\s+відповідальністю\s*[«""](?P<q1>[^»""\n]+)[»""]"
        r"|Фізична\s+особа[-–]?\s*підприємець\s*[«""](?P<q2>[^»""\n]+)[»""]"
        r"|Фізична\s+особа[-–]?\s*підприємець\s+(?P<fop>[^\n,]{3,80}?)(?=\s*[,\n]|$)"
        r"|(?:\bТОВ\b\.?)\s*[«""](?P<q3>[^»""\n]+)[»""]"
        r"|\b(?:ПрАТ|АТ|ФОП)\s*[«""](?P<q4>[^»""\n]+)[»""]"
        r"|(?:\bТОВ\b\.?|\bПрАТ\b|\bАТ\b|\bФОП\b)\s+(?P<raw>[A-ZА-ЯІЇЄҐA-Za-zа-яіїєґ0-9«»\-\.\s\u2013\u2014]{3,100}?)(?=\s*[,\n]|\s{2,}|$)"
        r")",
        re.IGNORECASE | re.UNICODE | re.VERBOSE,
    )

    _EDRPOU_DIGITS = re.compile(r"(?<!\d)(?:\d{8}|\d{10})(?!\d)")
    _KW_EDRPOU = re.compile(r"єдрпоу", re.IGNORECASE)
    _KW_IPN = re.compile(r"іпн", re.IGNORECASE)
    _KW_KOD = re.compile(r"\bкод\b", re.IGNORECASE)

    _KYIVSTAR = re.compile(r"київстар", re.IGNORECASE)
    _KYIVSTAR_EN = re.compile(r"kyivstar", re.IGNORECASE)
    _LIFECELL = re.compile(r"lifecell|лайфселл|лайф\s*селл", re.IGNORECASE)

    # Київстар: будь-які \s між словами якоря та перед сумою; «Розом» — типова помилка в розкладці/OCR
    _KYIVSTAR_SUM = re.compile(
        r"(?:Разом|Розом)\s*замовлено\s*та\s*надано\s*послуг\s*за\s*період\s*на\s*суму\s*([\d\s\u00a0\u202f,.]+)",
        re.IGNORECASE | re.DOTALL,
    )
    _LIFECELL_VAT_PF = re.compile(
        r"Враховуючи\s+ПДВ\s+та\s+ПФ\s*[^\d\n]{0,16}?((?:\d{1,3}(?:\s\d{3})+|\d+)(?:[,.]\d{1,2}))",
        re.IGNORECASE,
    )

    @staticmethod
    def _page_is_detail_breakdown(page_text: str) -> bool:
        """Сторінки з деталізацією / відомістю не беремо в текст рахунку."""
        low = (page_text or "").casefold()
        return "деталізація" in low or "відомість вартості за номером" in low

    @staticmethod
    def _merge_pdf_text(
        pdf: Any,
        *,
        start_index: int = 0,
        end_index: int | None = None,
    ) -> str:
        """Склеює ``extract_text`` сторінок ``[start_index, end_index)``, пропускаючи деталізацію."""
        pages = pdf.pages
        if end_index is None:
            end_index = len(pages)
        parts: list[str] = []
        for i in range(max(0, start_index), min(end_index, len(pages))):
            raw = pages[i].extract_text() or ""
            if InvoiceParser._page_is_detail_breakdown(raw):
                continue
            parts.append(raw)
        return "\n".join(parts)

    @staticmethod
    def _normalize_soft_hyphens_and_zw(s: str) -> str:
        """Прибирає м'які переноси та zero-width — вони рвуть слова в extract_text."""
        return (
            (s or "")
            .replace("\u00ad", "")
            .replace("\u200b", "")
            .replace("\ufeff", "")
        )

    @staticmethod
    def _parse_kyivstar_anchor_total(text: str, *, log_context: str = "") -> float | None:
        """Київстар: якорь + сума; при невдачі — діагностика в stdout."""
        raw = InvoiceParser._normalize_soft_hyphens_and_zw(text or "")
        m = InvoiceParser._KYIVSTAR_SUM.search(raw)
        if not m:
            snippet = raw[:100]
            ctx = f" [{log_context}]" if log_context else ""
            print(f"[InvoiceParser] Kyivstar: якір суми не знайдено{ctx}. Перші 100 символів тексту стор.1: {snippet!r}")
            return None
        val = InvoiceParser.parse_total_amount_to_float(m.group(1))
        if val <= 0:
            ctx = f" [{log_context}]" if log_context else ""
            print(
                f"[InvoiceParser] Kyivstar: якір знайдено, але сума не розпарсена{ctx}. "
                f"Захоплено: {m.group(1)!r}; snippet: {raw[:100]!r}"
            )
            return None
        return val

    @staticmethod
    def _parse_lifecell_vat_pf_total(text: str) -> float | None:
        """Lifecell: одразу після «Враховуючи ПДВ та ПФ» — сума."""
        m = InvoiceParser._LIFECELL_VAT_PF.search(text or "")
        if not m:
            return None
        return InvoiceParser.parse_total_amount_to_float(m.group(1))

    @staticmethod
    def _edrpou_keyword_before_digits(before_15: str) -> bool:
        if InvoiceParser._KW_EDRPOU.search(before_15):
            return True
        if InvoiceParser._KW_IPN.search(before_15):
            return True
        if InvoiceParser._KW_KOD.search(before_15):
            return True
        return False

    def __init__(self) -> None:
        self._config_mgr = ConfigManager()

    @staticmethod
    def _normalize_vendor_label(name: str) -> str:
        s = (name or "").strip()
        s = re.sub(r"[\r\n]+", " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @staticmethod
    def _remove_vendor_stop_words(name: str) -> str:
        s = name or ""
        for w in _VENDOR_STOP_WORDS:
            s = re.sub(rf"(?iu)\b{re.escape(w)}\b", "", s)
        s = re.sub(r"\s+", " ", s).strip()
        return s

    @staticmethod
    def _prefer_quoted_core(name: str) -> str:
        """Якщо у фрагменті є текст у лапках — повертаємо його як ядро назви."""
        s = (name or "").strip()
        if not s:
            return s
        for pat in (
            r"[«]([^»]+)[»]",
            r"[„]([^\"”]+)[\"”]",
            r"\"([^\"]+)\"",
            r"“([^”]+)”",
        ):
            m = re.search(pat, s)
            if m:
                inner = (m.group(1) or "").strip()
                if len(inner) >= 2:
                    return inner
        return s

    @staticmethod
    def _strip_boundary_punctuation(name: str) -> str:
        """Знімає розділові знаки з країв; лапки навколо слова залишаємо через _prefer_quoted_core."""
        s = (name or "").strip()
        if not s:
            return s
        edge = ".,;:!?…\\-—–·•"
        changed = True
        while changed:
            changed = False
            while s and s[0] in edge:
                s = s[1:].strip()
                changed = True
            while s and s[-1] in edge:
                s = s[:-1].strip()
                changed = True
        return s

    @staticmethod
    def _format_tov_brand(core: str) -> str:
        c = (core or "").strip()
        if not c:
            return c
        return f'ТОВ "{c}"'

    @staticmethod
    def _line_is_only_stop_words(line: str) -> bool:
        t = InvoiceParser._remove_vendor_stop_words(line)
        return len(t.strip()) < 2

    def _polish_vendor_fragment(self, line: str) -> str:
        s = self._remove_vendor_stop_words(line)
        s = self._prefer_quoted_core(s)
        s = self._strip_boundary_punctuation(s)
        s = self._normalize_vendor_label(s)
        return s

    def _collect_tov_vendor_candidates(self, text: str) -> list[str]:
        """
        Усі варіанти назви з блоку ТОВ / Товариство з ОВ (лапки, наступні рядки, скорочення ТОВ).
        Далі ``find_vendor_name`` відкидає ті, де збігається ``my_names_list``.
        """
        raw = text or ""
        out: list[str] = []

        m = re.search(
            r"Товариство\s+з\s+обмеженою\s+відповідальністю\s*"
            r"(?:[«]([^»]+)[»]|\"([^\"]+)\"|„([^\"”]+)[\"”])",
            raw,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            core = next((g for g in m.groups() if g and str(g).strip()), None)
            if core and len(str(core).strip()) >= 2:
                out.append(self._format_tov_brand(str(core).strip()))

        m0 = re.search(r"Товариство\s+з\s+обмеженою\s+відповідальністю", raw, re.IGNORECASE)
        if m0:
            tail = raw[m0.end() : m0.end() + 2500]
            for line in re.split(r"\r?\n", tail):
                line = line.strip()
                if not line:
                    continue
                frag = self._polish_vendor_fragment(line)
                if len(frag) < 2:
                    continue
                if self._line_is_only_stop_words(line):
                    continue
                low = frag.casefold()
                if low.startswith("товариство"):
                    continue
                out.append(self._format_tov_brand(frag))

        m_tov = re.search(
            r"\bТОВ\b\s*(?:[«]([^»]+)[»]|\"([^\"]+)\")",
            raw,
            re.IGNORECASE,
        )
        if m_tov:
            core = (m_tov.group(1) or m_tov.group(2) or "").strip()
            if len(core) >= 2:
                out.append(self._format_tov_brand(core))

        seen: set[str] = set()
        uniq: list[str] = []
        for x in out:
            if x not in seen:
                seen.add(x)
                uniq.append(x)
        return uniq

    def _finalize_vendor_display(self, name: str) -> str:
        """Стоп-слова, кавички як ядро, розділові з країв — перед поверненням з find_vendor_name."""
        s = self._remove_vendor_stop_words(name or "")
        s = s.strip()
        if re.match(r'(?i)^ТОВ\s+[«""„]', s):
            s = self._strip_boundary_punctuation(s)
            return self._normalize_vendor_label(s)
        s = self._prefer_quoted_core(s)
        s = self._strip_boundary_punctuation(s)
        return self._normalize_vendor_label(s)

    @staticmethod
    def _company_needles(my_company_name: str | list[str] | None) -> list[str]:
        if isinstance(my_company_name, list):
            return [str(x).strip().lower() for x in my_company_name if str(x).strip()]
        if my_company_name:
            return [str(my_company_name).strip().lower()]
        return []

    def find_vendor_name(self, text: str, my_company_name: str | list[str] | None = None) -> str:
        """
        Жорсткі ключові слова (Київстар / Lifecell), далі кандидати ТОВ, далі regex.

        Для кожного кандидата перевіряємо **усі** рядки з ``my_names_list``: якщо назва з PDF
        **містить** хоча б одне з цих слів (наша компанія) — кандидат ігнорується, шукаємо далі.
        """
        raw = text or ""
        low = raw.casefold()

        if "київстар" in low or InvoiceParser._KYIVSTAR_EN.search(raw):
            return self._normalize_vendor_label('ПрАТ "Київстар"')
        if "лайфселл" in low or "lifecell" in low:
            return self._normalize_vendor_label('ТОВ "лайфселл"')

        if not raw.strip():
            return "Невідомий контрагент"

        needles = self._company_needles(my_company_name)

        def _is_our_company_name(name_lower: str) -> bool:
            """True, якщо знайдена назва стосується «своєї» компанії (будь-який рядок з конфігу)."""
            if not needles:
                return False
            for needle in needles:
                if needle and needle in name_lower:
                    return True
            return False

        for tov_cand in self._collect_tov_vendor_candidates(raw):
            name_short = self._finalize_vendor_display(tov_cand)
            if len(name_short) < 4:
                continue
            name_lower = name_short.casefold()
            if _is_our_company_name(name_lower):
                continue
            if "банк" in name_lower:
                continue
            return name_short

        for m in InvoiceParser._VENDOR_NAME.finditer(raw):
            name = m.group(0).strip()
            name = re.sub(r"[\r\n]+", " ", name)
            name = re.sub(r"\s+", " ", name).strip()
            if len(name) < 4:
                continue
            name_short = self._finalize_vendor_display(name[:300])
            if len(name_short) < 4:
                continue
            name_lower = name_short.casefold()
            if _is_our_company_name(name_lower):
                continue
            if "банк" in name_lower:
                continue
            return name_short

        return "Невідомий контрагент"

    @staticmethod
    def _payment_requisites_windows_flat(text: str) -> list[str]:
        """Фрагменти до 300 символів після «Платіжні реквізити» / «п/р», без переносів рядків."""
        if not (text or "").strip():
            return []
        out: list[str] = []
        for m in InvoiceParser._PAYMENT_REQ_ANCHOR.finditer(text):
            chunk = text[m.end() : m.end() + 300]
            flat = chunk.replace("\n", "").replace("\r", "")
            out.append(flat)
        return out

    @staticmethod
    def find_edrpou(text: str) -> list[str]:
        seen: set[str] = set()
        unique: list[str] = []
        for m in InvoiceParser._EDRPOU_DIGITS.finditer(text):
            start = m.start()
            window_start = max(0, start - 15)
            before = text[window_start:start]
            if not InvoiceParser._edrpou_keyword_before_digits(before):
                continue
            code = m.group(0)
            if code not in seen:
                seen.add(code)
                unique.append(code)

        for flat in InvoiceParser._payment_requisites_windows_flat(text):
            n = len(flat)
            if not n:
                continue
            for m in InvoiceParser._EDRPOU_DIGITS.finditer(flat):
                code = m.group(0)
                if code in seen:
                    continue
                start = m.start()
                before = flat[max(0, start - 40) : start]
                near_end = start >= max(0, n - 80)
                if InvoiceParser._edrpou_keyword_before_digits(before) or near_end:
                    seen.add(code)
                    unique.append(code)

        return unique

    @staticmethod
    def _find_iban_ua_in_blob(blob: str) -> list[str]:
        """UA + 27 символів; допускаються пробіли — перед перевіркою довжини прибираються."""
        if not blob:
            return []
        seen: set[str] = set()
        result: list[str] = []

        def _add_from_normalized(raw: str) -> None:
            normalized = re.sub(r"\s+", "", raw).upper()
            if len(normalized) != 29 or not normalized.startswith("UA"):
                return
            if not re.fullmatch(r"UA[0-9A-Z]{27}", normalized):
                return
            if normalized not in seen:
                seen.add(normalized)
                result.append(normalized)

        for hit in re.findall(r"\bUA[A-Z0-9]{27}\b", blob, flags=re.IGNORECASE):
            _add_from_normalized(hit)

        for m in re.finditer(r"(?i)\bUA\b", blob):
            slice_ = blob[m.start() : m.start() + 45]
            compact = re.sub(r"[^0-9A-Za-z]", "", slice_).upper()
            if len(compact) < 29:
                continue
            if not compact.startswith("UA"):
                continue
            _add_from_normalized(compact[:29])

        return result

    @staticmethod
    def find_iban_ua(text: str) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        blobs = [text]
        blobs.extend(InvoiceParser._payment_requisites_windows_flat(text))
        for blob in blobs:
            for ib in InvoiceParser._find_iban_ua_in_blob(blob):
                if ib not in seen:
                    seen.add(ib)
                    result.append(ib)
        return result

    @staticmethod
    def find_total_amount_strings(text: str) -> list[str]:
        amount_pattern = (
            r"(?<![\d,.])"
            r"(?:\d{1,3}(?:\s\d{3})+|\d+)"
            r"(?:[,.]\d{1,2})"
            r"(?![\d,.])"
        )
        return re.findall(amount_pattern, text)

    @staticmethod
    def parse_total_amount_to_float(amount_str: str) -> float:
        s = (amount_str or "").strip()
        s = s.replace("\xa0", " ").replace("\u202f", " ")
        compact = re.sub(r"\s+", "", s)
        compact = compact.replace(",", ".")
        try:
            return float(compact)
        except ValueError:
            return 0.0

    @staticmethod
    def get_invoice_total(amounts_float: list[float]) -> float:
        if not amounts_float:
            return 0.0
        return max(amounts_float)

    @staticmethod
    def _digits_only(s: str) -> str:
        return re.sub(r"\D", "", (s or "").strip())

    @staticmethod
    def filter_company_edrpou(
        codes: list[str],
        *,
        my_edrpou_list: list[str] | None = None,
        extra_edrpou: str = "",
    ) -> list[str]:
        """
        Прибирає зі списку знайдених у PDF **усі** коди, що збігаються з будь-яким ЄДРПОУ
        з ``my_edrpou_list`` (кілька компаній). Опційно додається ``extra_edrpou`` (перевизначення з виклику).
        """
        to_drop: set[str] = set()
        for raw in list(my_edrpou_list or []):
            d = InvoiceParser._digits_only(str(raw))
            if d:
                to_drop.add(d)
        d_extra = InvoiceParser._digits_only(str(extra_edrpou or ""))
        if d_extra:
            to_drop.add(d_extra)
        if not to_drop:
            return list(codes)
        out: list[str] = []
        for c in codes:
            if InvoiceParser._digits_only(c) in to_drop:
                continue
            out.append(c)
        return out

    @staticmethod
    def _vendor_from_known_edrpou(codes: list[str], *haystacks: str) -> str | None:
        """Зіставлення назви за відомими ЄДРПОУ зі словника (після фільтрації свого коду)."""
        digits_concat = "".join(InvoiceParser._digits_only(h) for h in haystacks if h)
        for c in codes:
            d = InvoiceParser._digits_only(c)
            if d in _EDRPOU_TO_VENDOR:
                return _EDRPOU_TO_VENDOR[d]
        for key, label in _EDRPOU_TO_VENDOR.items():
            if key and key in digits_concat:
                return label
        return None

    @staticmethod
    def _prioritize_first_eight_digit_edrpou(codes: list[str]) -> None:
        """Після ``filter_company_edrpou``: перший 8-значний код (наприклад, Київстар) — на початку списку."""
        for i, c in enumerate(codes):
            if len(InvoiceParser._digits_only(c)) == 8:
                if i > 0:
                    codes.insert(0, codes.pop(i))
                return

    def _maybe_fill_known_vendor_requisites(
        self,
        vendor_name: str,
        edrpou: list[str],
        iban: list[str],
    ) -> bool:
        vn = self._normalize_vendor_label(vendor_name)
        data = InvoiceParser.KNOWN_VENDORS_REQUISITES.get(vn)
        if not data:
            return False
        need_e = not [x for x in edrpou if str(x).strip()]
        need_i = not [x for x in iban if str(x).strip()]
        if not need_e and not need_i:
            return False
        changed = False
        if need_e:
            edrpou[:] = [data["edrpou"]]
            changed = True
        if need_i:
            iban[:] = [data["iban"]]
            changed = True
        return changed

    @staticmethod
    def _log_kyivstar_requisites_from_kb() -> None:
        try:
            import eel

            eel.update_ui_status("[i]", "Реквізити Київстар додано з бази знань")(lambda _=None: None)
        except Exception:
            pass

    def process_pdf(self, file_path: str, *, ignore_company_edrpou: str = "") -> dict[str, Any]:
        with pdfplumber.open(file_path) as pdf:
            # Сира стор. 1 — єдине джерело суми для Київстар (без наступних сторінок)
            page0_raw = (pdf.pages[0].extract_text() or "") if pdf.pages else ""
            kyivstar = bool(self._KYIVSTAR.search(page0_raw) or self._KYIVSTAR_EN.search(page0_raw))
            if kyivstar:
                # Мета-дані (контрагент, ІБАН, коди) — лише з 1‑ї сторінки без деталізаційних блоків
                text = self._merge_pdf_text(pdf, start_index=0, end_index=1)
            else:
                text = self._merge_pdf_text(pdf, start_index=0, end_index=len(pdf.pages))

        cfg = self._config_mgr.load()
        edrpou_cfg = cfg.get("my_edrpou_list")
        if not isinstance(edrpou_cfg, list):
            edrpou_cfg = []
        edrpou_list_cfg = [str(x).strip() for x in edrpou_cfg if str(x).strip()]
        names_cfg = cfg.get("my_names_list")
        if not isinstance(names_cfg, list):
            names_cfg = []
        names_list_cfg = [str(x).strip() for x in names_cfg if str(x).strip()]

        passed_own = (ignore_company_edrpou or "").strip()

        # Для ключових слів (Київстар / Lifecell) дивимось і перші сирі дані стор.1
        vendor_haystack = "\n".join(x for x in (text, page0_raw) if (x or "").strip())

        vendor_name = self.find_vendor_name(vendor_haystack, names_list_cfg)
        vendor_name = self._normalize_vendor_label(vendor_name)

        edrpou = self.find_edrpou(text)
        edrpou = self.filter_company_edrpou(
            edrpou,
            my_edrpou_list=edrpou_list_cfg,
            extra_edrpou=passed_own,
        )
        if vendor_name == "Невідомий контрагент":
            guessed = self._vendor_from_known_edrpou(edrpou, text, page0_raw, vendor_haystack)
            if guessed:
                vendor_name = self._normalize_vendor_label(guessed)

        if (
            vendor_name in InvoiceParser.KNOWN_VENDORS_REQUISITES
            or "київстар" in vendor_name.casefold()
        ):
            InvoiceParser._prioritize_first_eight_digit_edrpou(edrpou)

        iban = self.find_iban_ua(text)

        if self._maybe_fill_known_vendor_requisites(vendor_name, edrpou, iban):
            InvoiceParser._log_kyivstar_requisites_from_kb()

        hay_for_flags = vendor_haystack.casefold()
        lifecell = bool(self._LIFECELL.search(text) or ("лайфселл" in hay_for_flags) or ("lifecell" in hay_for_flags))

        total_amount: float
        if kyivstar:
            # Сума — тільки з pdf.pages[0], щоб не змішувати з дробовими сумами з інших сторінок
            page0_for_sum = self._normalize_soft_hyphens_and_zw(page0_raw)
            anchored = self._parse_kyivstar_anchor_total(
                page0_for_sum,
                log_context=os.path.basename(file_path),
            )
            if anchored is not None and anchored > 0:
                total_amount = anchored
            else:
                amount_strings = self.find_total_amount_strings(page0_for_sum)
                amounts_float = [self.parse_total_amount_to_float(s) for s in amount_strings]
                total_amount = self.get_invoice_total(amounts_float)
                if total_amount <= 0:
                    print(
                        "[InvoiceParser] Kyivstar: fallback за сумами не дав результату. "
                        f"Перші 100 символів стор.1: {(page0_for_sum or '')[:100]!r}"
                    )
        elif lifecell:
            lf = self._parse_lifecell_vat_pf_total(text)
            if lf is not None and lf > 0:
                total_amount = lf
            else:
                amount_strings = self.find_total_amount_strings(text)
                amounts_float = [self.parse_total_amount_to_float(s) for s in amount_strings]
                total_amount = self.get_invoice_total(amounts_float)
        else:
            amount_strings = self.find_total_amount_strings(text)
            amounts_float = [self.parse_total_amount_to_float(s) for s in amount_strings]
            total_amount = self.get_invoice_total(amounts_float)

        if total_amount <= 0:
            raise InvoiceParseSkipError("Сума рахунку не визначена або дорівнює нулю — запис до реєстру не додається.")

        if total_amount > 0 and not edrpou:
            print(
                "[InvoiceParser] Увага: контрагента не знайдено, перевірте реквізити "
                f"({os.path.basename(file_path)})"
            )

        return {
            "vendor_name": vendor_name,
            "edrpou": edrpou,
            "iban": iban,
            "total_amount": total_amount,
        }

    @staticmethod
    def _emit_ui_progress(percent: float) -> None:
        """Оновлення смуги прогресу у веб-UI; ``eel.sleep`` дає час WebSocket на відправку."""
        try:
            import eel

            eel.update_progress(float(percent))(lambda _r=None: None)
        except Exception:
            pass
        try:
            import eel

            eel.sleep(0.01)
        except Exception:
            time.sleep(0.01)

    def process_directory(
        self,
        folder_path: str,
        *,
        ignore_company_edrpou: str = "",
        status_sink: Callable[[str, str], None] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Парсить усі ``*.pdf`` у каталозі; на кожній ітерації оновлює прогрес
        ``(current_index + 1) / total * 100`` через ``eel.update_progress``.
        """
        root = Path(folder_path)
        if not root.is_dir():
            return []
        pdfs = sorted(root.glob("*.pdf"))
        total = len(pdfs)
        if total == 0:
            return []

        InvoiceParser._emit_ui_progress(0.0)
        rows: list[dict[str, Any]] = []

        for i, pdf in enumerate(pdfs):
            name = pdf.name
            if status_sink:
                status_sink("Parsing", name)
            try:
                result = self.process_pdf(str(pdf), ignore_company_edrpou=ignore_company_edrpou)
                row = dict(result)
                row["_source_file"] = name
                rows.append(row)
                if status_sink:
                    status_sink("Success", name)
            except InvoiceParseSkipError:
                if status_sink:
                    status_sink("Error", f"{name} (немає валідної суми)")
            except Exception:
                if status_sink:
                    status_sink("Error", name)

            pct = (i + 1) / total * 100.0
            InvoiceParser._emit_ui_progress(pct)

        return rows
