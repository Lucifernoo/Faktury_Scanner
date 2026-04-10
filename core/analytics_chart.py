"""Побудова графіка витрат за контрагентами без Tkinter (PNG base64 для Eel)."""

from __future__ import annotations

import base64
import io
import os
from typing import Any

import pandas as pd
from matplotlib.figure import Figure

from core.config_manager import DEFAULT_SETTINGS, ConfigManager
from core.exporter import get_registry_path


def _cell_to_hashable_label(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, float) and pd.isna(val):
        return ""
    if isinstance(val, (list, tuple, set)):
        return ", ".join(str(x) for x in val)
    if isinstance(val, dict):
        return ", ".join(f"{k}: {v}" for k, v in val.items())
    return str(val).strip()


def build_vendors_chart_png_base64() -> tuple[str | None, str | None]:
    """
    Читає реєстр Excel, будує стовпчикову діаграму як у ``AnalyticsWindow``.
    Повертає (base64_png, error_message). При успіху error_message is None.
    """
    excel_path = get_registry_path()

    if not os.path.isfile(excel_path):
        return None, "Файл Excel ще не створено. Збережіть хоча б один рахунок."

    try:
        df = pd.read_excel(excel_path, engine="openpyxl")
    except PermissionError:
        return None, "Файл реєстру відкритий в Excel. Закрийте «Реєстр_рахунків.xlsx» і спробуйте знову."
    except OSError as e:
        return None, f"Помилка читання Excel: {e}"

    config = ConfigManager().load()
    try:
        cols = list(config.get("export_columns") or DEFAULT_SETTINGS["export_columns"])
        vendor_col_name = cols[1] if len(cols) > 1 else "Контрагент (Назва)"
        amount_col_name = cols[4] if len(cols) > 4 else "Сума до сплати"

        if vendor_col_name not in df.columns or amount_col_name not in df.columns:
            return (
                None,
                f"У файлі немає колонок «{vendor_col_name}» або «{amount_col_name}». Перевірте export_columns у налаштуваннях.",
            )

        vendor_series = df[vendor_col_name]
        if isinstance(vendor_series, pd.DataFrame):
            vendor_series = vendor_series.iloc[:, 0]
        amount_series = df[amount_col_name]
        if isinstance(amount_series, pd.DataFrame):
            amount_series = amount_series.iloc[:, 0]

        v_norm = vendor_series.map(_cell_to_hashable_label)
        amounts = pd.to_numeric(amount_series, errors="coerce").fillna(0.0)

        clean_df = pd.DataFrame({"Vendor": v_norm, "Amount": amounts})
        clean_df = clean_df[
            (clean_df["Vendor"] != "") & (clean_df["Vendor"].str.lower() != "nan") & clean_df["Vendor"].notna()
        ]

        if clean_df["Vendor"].dtype == object:
            clean_df["Vendor"] = clean_df["Vendor"].astype(str)

        summary = clean_df.groupby("Vendor", dropna=True)["Amount"].sum().sort_values(ascending=False)

        if summary.empty or float(summary.sum()) == 0.0:
            return None, "Немає числових даних для побудови графіка."

        fig = Figure(figsize=(8, 5), dpi=100, facecolor="#2b2b2b")
        ax = fig.add_subplot(111)
        ax.set_facecolor("#2b2b2b")
        ax.tick_params(colors="white", labelsize=10)
        for spine in ("top", "right"):
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color("#555555")
        ax.spines["left"].set_color("#555555")

        bars = ax.bar(summary.index.astype(str), summary.values, color="#1f6aa5", edgecolor="none")

        for bar in bars:
            yval = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                yval + (yval * 0.02) if yval else 0.02,
                f"{yval:,.2f}",
                ha="center",
                va="bottom",
                color="white",
                fontsize=10,
                fontweight="bold",
            )

        fig.autofmt_xdate(rotation=15)
        fig.tight_layout()

        buf = io.BytesIO()
        fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight")
        buf.seek(0)
        b64 = base64.b64encode(buf.read()).decode("ascii")
        return b64, None

    except Exception as e:
        return None, f"Помилка побудови графіка: {e}"
