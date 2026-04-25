#!/usr/bin/env python3
"""
TourVsTravel — Styles Index Generator
=====================================

Purpose
-------
Generate multilingual official index pages for the travel styles layer:

    /en/styles/
    /ar/styles/
    /fr/styles/
    /es/styles/
    /de/styles/
    /zh/styles/
    /ja/styles/

The page links the existing individual experience type pages generated from
data/experience_types.yaml.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlparse

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError, select_autoescape

from scripts.loaders import load_experience_types, load_site_config


# ============================================================================
# Logging
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("generate_styles_index")


# ============================================================================
# Paths
# ============================================================================

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/styles_index.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")


# ============================================================================
# Exceptions
# ============================================================================

class GenerateStylesIndexError(Exception):
    """Raised when styles index generation fails."""


class StylesIndexConfigError(GenerateStylesIndexError):
    """Raised when configuration or source data is invalid."""


class StylesIndexRenderError(GenerateStylesIndexError):
    """Raised when template rendering fails."""


class StylesIndexWriteError(GenerateStylesIndexError):
    """Raised when output writing fails."""


# ============================================================================
# Multilingual copy
# ============================================================================

PAGE_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "styles_label": "travel styles",
        "criteria_label": "decision criteria",
        "reference_label": "reference system",
        "title": "The 17 Faces of Travel",
        "lead": (
            "Every travel style is a different operating model for moving through the world. "
            "TourVsTravel treats each style as a real decision path shaped by cost, autonomy, "
            "coordination burden, predictability, depth, and relationship to place."
        ),
        "actions_label": "Styles index actions",
        "primary_action": "Find Your Match",
        "secondary_action": "Read the Methodology",
        "system_panel_label": "Styles reference system",
        "system_label": "System role",
        "system_value": "Classify travel by decision logic, not decoration.",
        "output_label": "Reference output",
        "output_value": "A structured map of how different travel forms behave.",
        "scope_label": "Current scope",
        "scope_value": "styles connected to individual reference pages.",
        "grid_kicker": "Reference layer",
        "grid_title": "Explore every travel style",
        "grid_lead": (
            "These are not content categories. They are distinct patterns of cost, control, "
            "support, exposure, and experience depth."
        ),
        "strength_label": "Signal",
        "open_label": "Open reference page ->",
        "method_kicker": "Decision architecture",
        "method_title": "Why styles matter",
        "method_lead": (
            "The same destination can produce radically different experiences depending on the "
            "travel form. The styles index turns that difference into a navigable system."
        ),
        "method_card_1_label": "Constraint fit",
        "method_card_1_value": "How well the style survives real limits.",
        "method_card_2_label": "Operational burden",
        "method_card_2_value": "How much complexity the traveler must absorb.",
        "method_card_3_label": "Experience depth",
        "method_card_3_value": "How directly the traveler encounters place.",
        "final_kicker": "Next step",
        "final_title": "Move from preference to fit",
        "final_lead": (
            "The purpose of this layer is not to tell every traveler the same answer. "
            "It is to make the answer more legible."
        ),
    },
    "ar": {
        "styles_label": "أنماط سفر",
        "criteria_label": "معايير قرار",
        "reference_label": "نظام مرجعي",
        "title": "الوجوه السبعة عشر للسفر",
        "lead": (
            "كل نمط سفر هو نموذج مختلف للحركة عبر العالم. يتعامل TourVsTravel مع كل نمط "
            "كطريق قرار حقيقي يتشكل حسب التكلفة، الاستقلالية، عبء التنسيق، قابلية التوقع، "
            "عمق التجربة، والعلاقة بالمكان."
        ),
        "actions_label": "إجراءات صفحة الأنماط",
        "primary_action": "اعرف الأنسب لك",
        "secondary_action": "اقرأ المنهجية",
        "system_panel_label": "نظام مرجعي لأنماط السفر",
        "system_label": "دور النظام",
        "system_value": "تصنيف السفر حسب منطق القرار لا حسب الزخرفة.",
        "output_label": "المخرج المرجعي",
        "output_value": "خريطة منظمة لكيف تتصرف أشكال السفر المختلفة.",
        "scope_label": "النطاق الحالي",
        "scope_value": "نمطًا مرتبطًا بصفحات مرجعية فردية.",
        "grid_kicker": "طبقة مرجعية",
        "grid_title": "استكشف كل أنماط السفر",
        "grid_lead": (
            "هذه ليست تصنيفات محتوى عادية. إنها أنماط مختلفة من التكلفة، السيطرة، الدعم، "
            "الانكشاف، وعمق التجربة."
        ),
        "strength_label": "إشارة",
        "open_label": "افتح الصفحة المرجعية ->",
        "method_kicker": "هندسة القرار",
        "method_title": "لماذا تهم الأنماط",
        "method_lead": (
            "نفس الوجهة يمكن أن تنتج تجارب مختلفة جذريًا حسب شكل السفر. صفحة الأنماط "
            "تحول هذا الفرق إلى نظام قابل للتصفح والفهم."
        ),
        "method_card_1_label": "ملاءمة القيود",
        "method_card_1_value": "مدى قدرة النمط على الصمود أمام الحدود الواقعية.",
        "method_card_2_label": "العبء التشغيلي",
        "method_card_2_value": "مقدار التعقيد الذي يتحمله المسافر.",
        "method_card_3_label": "عمق التجربة",
        "method_card_3_value": "مدى اقتراب المسافر من عيش المكان مباشرة.",
        "final_kicker": "الخطوة التالية",
        "final_title": "انتقل من التفضيل إلى الملاءمة",
        "final_lead": "هدف هذه الطبقة ليس إعطاء نفس الجواب لكل مسافر، بل جعل الجواب أكثر وضوحًا.",
    },
    "fr": {
        "styles_label": "styles de voyage",
        "criteria_label": "critères de décision",
        "reference_label": "système de référence",
        "title": "Les 17 visages du voyage",
        "lead": (
            "Chaque style de voyage est un modèle différent de déplacement dans le monde. "
            "TourVsTravel traite chaque style comme une véritable logique de décision."
        ),
        "actions_label": "Actions de l’index des styles",
        "primary_action": "Trouver mon style",
        "secondary_action": "Lire la méthodologie",
        "system_panel_label": "Système de référence des styles",
        "system_label": "Rôle du système",
        "system_value": "Classer le voyage par logique de décision, pas par décor.",
        "output_label": "Sortie de référence",
        "output_value": "Une carte structurée des formes de voyage.",
        "scope_label": "Portée actuelle",
        "scope_value": "styles reliés à des pages de référence individuelles.",
        "grid_kicker": "Couche de référence",
        "grid_title": "Explorer tous les styles de voyage",
        "grid_lead": (
            "Ce ne sont pas de simples catégories éditoriales, mais des modèles distincts de coût, "
            "contrôle, soutien, exposition et profondeur d’expérience."
        ),
        "strength_label": "Signal",
        "open_label": "Ouvrir la page ->",
        "method_kicker": "Architecture de décision",
        "method_title": "Pourquoi les styles comptent",
        "method_lead": "Une même destination peut produire des expériences très différentes selon la forme du voyage.",
        "method_card_1_label": "Adéquation aux contraintes",
        "method_card_1_value": "La capacité du style à fonctionner sous limites réelles.",
        "method_card_2_label": "Charge opérationnelle",
        "method_card_2_value": "La complexité que le voyageur doit absorber.",
        "method_card_3_label": "Profondeur d’expérience",
        "method_card_3_value": "Le niveau de rencontre directe avec le lieu.",
        "final_kicker": "Étape suivante",
        "final_title": "Passer de la préférence à l’adéquation",
        "final_lead": "Cette couche rend le choix plus lisible avant l’engagement.",
    },
    "es": {
        "styles_label": "estilos de viaje",
        "criteria_label": "criterios de decisión",
        "reference_label": "sistema de referencia",
        "title": "Las 17 caras del viaje",
        "lead": (
            "Cada estilo de viaje es un modelo distinto para moverse por el mundo. "
            "TourVsTravel convierte esas diferencias en una estructura de decisión."
        ),
        "actions_label": "Acciones del índice de estilos",
        "primary_action": "Encuentra tu ajuste",
        "secondary_action": "Leer la metodología",
        "system_panel_label": "Sistema de referencia de estilos",
        "system_label": "Rol del sistema",
        "system_value": "Clasificar el viaje por lógica de decisión, no por decoración.",
        "output_label": "Salida de referencia",
        "output_value": "Un mapa estructurado de formas de viajar.",
        "scope_label": "Alcance actual",
        "scope_value": "estilos conectados a páginas de referencia.",
        "grid_kicker": "Capa de referencia",
        "grid_title": "Explora todos los estilos de viaje",
        "grid_lead": (
            "No son categorías de contenido, sino patrones distintos de coste, control, soporte, "
            "exposición y profundidad."
        ),
        "strength_label": "Señal",
        "open_label": "Abrir página ->",
        "method_kicker": "Arquitectura de decisión",
        "method_title": "Por qué importan los estilos",
        "method_lead": "El mismo destino puede generar experiencias distintas según la forma de viajar.",
        "method_card_1_label": "Ajuste a restricciones",
        "method_card_1_value": "Qué tan bien funciona el estilo bajo límites reales.",
        "method_card_2_label": "Carga operativa",
        "method_card_2_value": "Cuánta complejidad absorbe el viajero.",
        "method_card_3_label": "Profundidad de experiencia",
        "method_card_3_value": "Qué tan directamente se encuentra el lugar.",
        "final_kicker": "Siguiente paso",
        "final_title": "Pasar de preferencia a ajuste",
        "final_lead": "Esta capa hace que la elección sea más legible antes del compromiso.",
    },
    "de": {
        "styles_label": "Reisestile",
        "criteria_label": "Entscheidungskriterien",
        "reference_label": "Referenzsystem",
        "title": "Die 17 Gesichter des Reisens",
        "lead": (
            "Jeder Reisestil ist ein anderes Modell, sich durch die Welt zu bewegen. "
            "TourVsTravel macht diese Unterschiede als Entscheidungssystem lesbar."
        ),
        "actions_label": "Aktionen des Reisestil-Index",
        "primary_action": "Passenden Stil finden",
        "secondary_action": "Methodik lesen",
        "system_panel_label": "Referenzsystem der Reisestile",
        "system_label": "Systemrolle",
        "system_value": "Reisen nach Entscheidungslogik klassifizieren.",
        "output_label": "Referenzausgabe",
        "output_value": "Eine strukturierte Karte verschiedener Reiseformen.",
        "scope_label": "Aktueller Umfang",
        "scope_value": "Stile mit individuellen Referenzseiten.",
        "grid_kicker": "Referenzschicht",
        "grid_title": "Alle Reisestile erkunden",
        "grid_lead": (
            "Dies sind keine bloßen Inhaltskategorien, sondern unterschiedliche Muster von Kosten, "
            "Kontrolle, Unterstützung, Exposition und Tiefe."
        ),
        "strength_label": "Signal",
        "open_label": "Seite öffnen ->",
        "method_kicker": "Entscheidungsarchitektur",
        "method_title": "Warum Stile wichtig sind",
        "method_lead": "Dasselbe Ziel kann je nach Reiseform sehr unterschiedliche Erfahrungen erzeugen.",
        "method_card_1_label": "Passung zu Einschränkungen",
        "method_card_1_value": "Wie gut der Stil unter realen Grenzen funktioniert.",
        "method_card_2_label": "Operative Last",
        "method_card_2_value": "Wie viel Komplexität der Reisende übernimmt.",
        "method_card_3_label": "Erfahrungstiefe",
        "method_card_3_value": "Wie direkt der Ort erlebt wird.",
        "final_kicker": "Nächster Schritt",
        "final_title": "Von Vorliebe zu Passung",
        "final_lead": "Diese Ebene macht die Wahl vor der Entscheidung klarer.",
    },
    "zh": {
        "styles_label": "旅行方式",
        "criteria_label": "决策标准",
        "reference_label": "参考系统",
        "title": "旅行的17种面貌",
        "lead": "每一种旅行方式都是一种不同的移动模型。TourVsTravel 将这些差异转化为可理解的决策结构。",
        "actions_label": "旅行方式索引操作",
        "primary_action": "找到适合方式",
        "secondary_action": "阅读方法论",
        "system_panel_label": "旅行方式参考系统",
        "system_label": "系统角色",
        "system_value": "按决策逻辑分类旅行，而非按表面标签。",
        "output_label": "参考输出",
        "output_value": "不同旅行形式的结构化地图。",
        "scope_label": "当前范围",
        "scope_value": "种旅行方式连接到独立参考页面。",
        "grid_kicker": "参考层",
        "grid_title": "探索全部旅行方式",
        "grid_lead": "这些不是普通内容分类，而是成本、控制、支持、暴露度和体验深度的不同模式。",
        "strength_label": "信号",
        "open_label": "打开参考页 ->",
        "method_kicker": "决策架构",
        "method_title": "为什么旅行方式重要",
        "method_lead": "同一目的地会因旅行形式不同而产生完全不同的体验。",
        "method_card_1_label": "限制适配",
        "method_card_1_value": "该方式在现实限制下的表现。",
        "method_card_2_label": "操作负担",
        "method_card_2_value": "旅行者需要承担多少复杂性。",
        "method_card_3_label": "体验深度",
        "method_card_3_value": "旅行者与地点接触的直接程度。",
        "final_kicker": "下一步",
        "final_title": "从偏好走向适配",
        "final_lead": "这一层让选择在承诺之前更加清晰。",
    },
    "ja": {
        "styles_label": "旅行スタイル",
        "criteria_label": "意思決定基準",
        "reference_label": "参照システム",
        "title": "旅行の17の顔",
        "lead": "それぞれの旅行スタイルは、世界を移動するための異なるモデルです。TourVsTravel はその違いを意思決定の構造として整理します。",
        "actions_label": "旅行スタイル索引の操作",
        "primary_action": "自分に合う旅を探す",
        "secondary_action": "方法論を読む",
        "system_panel_label": "旅行スタイル参照システム",
        "system_label": "システムの役割",
        "system_value": "装飾ではなく意思決定ロジックで旅行を分類する。",
        "output_label": "参照出力",
        "output_value": "旅行形式の構造化された地図。",
        "scope_label": "現在の範囲",
        "scope_value": "スタイルが個別参照ページに接続されています。",
        "grid_kicker": "参照レイヤー",
        "grid_title": "すべての旅行スタイルを探索",
        "grid_lead": "これは単なるカテゴリではなく、費用、制御、支援、露出、体験深度の異なるパターンです。",
        "strength_label": "シグナル",
        "open_label": "参照ページを開く ->",
        "method_kicker": "意思決定設計",
        "method_title": "なぜスタイルが重要か",
        "method_lead": "同じ目的地でも、旅行形式によって体験は大きく変わります。",
        "method_card_1_label": "制約適合",
        "method_card_1_value": "現実的な制約下でどれだけ機能するか。",
        "method_card_2_label": "運用負担",
        "method_card_2_value": "旅行者がどれだけ複雑さを担うか。",
        "method_card_3_label": "体験深度",
        "method_card_3_value": "場所とどれだけ直接出会うか。",
        "final_kicker": "次のステップ",
        "final_title": "好みから適合へ",
        "final_lead": "このレイヤーは、決定前の選択をより明確にします。",
    },
}


# ============================================================================
# Helpers
# ============================================================================

def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise StylesIndexConfigError(f"{label} must be a mapping/object.")
    return value


def _ensure_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise StylesIndexConfigError(f"{label} must be a list.")
    return value


def _clean_string(value: Any, *, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return default
    return str(value).strip()


def _localized(value: Any, lang: str, *, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip() or default
    if isinstance(value, Mapping):
        candidates = (
            value.get(lang),
            value.get("en"),
            next((item for item in value.values() if isinstance(item, str) and item.strip()), None),
        )
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return default


def _normalize_https_base_url(site_config: Mapping[str, Any]) -> str:
    site = _ensure_mapping(site_config.get("site"), "site")
    raw = _clean_string(site.get("base_url"), default="https://tourvstravel.com")
    parsed = urlparse(raw)

    if parsed.scheme.lower() != "https":
        raise StylesIndexConfigError(f"site.base_url must use HTTPS. Got: {raw!r}")
    if not parsed.netloc:
        raise StylesIndexConfigError(f"site.base_url must be absolute. Got: {raw!r}")
    if parsed.query or parsed.fragment:
        raise StylesIndexConfigError("site.base_url must not contain query or fragment.")
    if (parsed.path or "") not in ("", "/"):
        raise StylesIndexConfigError(f"site.base_url must not contain a path. Got: {raw!r}")

    return f"https://{parsed.netloc.rstrip('/')}"


def _extract_site_name(site_config: Mapping[str, Any], lang: str) -> str:
    site = _ensure_mapping(site_config.get("site"), "site")
    return _localized(site.get("name"), lang, default="TourVsTravel")


def _extract_theme_color(site_config: Mapping[str, Any]) -> str:
    seo = site_config.get("seo")
    if isinstance(seo, Mapping) and isinstance(seo.get("theme_color"), str):
        return seo["theme_color"].strip()

    colors = site_config.get("branding", {}).get("colors", {}) if isinstance(site_config.get("branding"), Mapping) else {}
    if isinstance(colors, Mapping) and isinstance(colors.get("primary_blue"), str):
        return colors["primary_blue"].strip()

    return "#0f172a"


def _extract_enabled_languages(site_config: Mapping[str, Any]) -> List[str]:
    languages = site_config.get("languages")
    if isinstance(languages, list):
        codes: List[str] = []
        for idx, item in enumerate(languages):
            if not isinstance(item, Mapping):
                raise StylesIndexConfigError(f"languages[{idx}] must be a mapping/object.")
            code = _clean_string(item.get("code"))
            enabled = item.get("enabled", True)
            if code and enabled is True:
                codes.append(code)
        return [code for code in codes if code in SUPPORTED_LANGUAGES]

    if isinstance(languages, Mapping):
        codes = []
        for code, config in languages.items():
            if not isinstance(code, str):
                raise StylesIndexConfigError("language keys must be strings.")
            if isinstance(config, Mapping):
                if config.get("enabled", True) is True:
                    codes.append(code.strip())
            elif config is True:
                codes.append(code.strip())
        return [code for code in codes if code in SUPPORTED_LANGUAGES]

    return list(SUPPORTED_LANGUAGES)


def _language_direction(site_config: Mapping[str, Any], lang: str) -> str:
    languages = site_config.get("languages")
    if isinstance(languages, list):
        for item in languages:
            if isinstance(item, Mapping) and item.get("code") == lang:
                direction = item.get("dir", "ltr")
                return direction if direction in {"ltr", "rtl"} else "ltr"
    return "rtl" if lang == "ar" else "ltr"


def _language_locales(site_config: Mapping[str, Any], current_lang: str) -> tuple[Optional[str], List[str]]:
    current_locale: Optional[str] = None
    alternate_locales: List[str] = []
    languages = site_config.get("languages")

    if isinstance(languages, list):
        for item in languages:
            if not isinstance(item, Mapping):
                continue
            code = item.get("code")
            locale = item.get("locale")
            if not isinstance(locale, str) or not locale.strip():
                continue
            if code == current_lang:
                current_locale = locale.strip()
            else:
                alternate_locales.append(locale.strip())

    return current_locale, alternate_locales


def _require_existing_asset(asset_path: str, label: str) -> str:
    path_text = _clean_string(asset_path)
    if not path_text.startswith("/"):
        raise StylesIndexConfigError(f"{label} must be root-relative. Got: {asset_path!r}")

    physical = ROOT_DIR / path_text.lstrip("/")
    if not physical.is_file():
        raise StylesIndexConfigError(f"{label} points to a missing file: {path_text} -> {physical}")

    return path_text


def _infer_mime_type_from_path(asset_path: str) -> str:
    suffix = Path(asset_path).suffix.lower()
    if suffix == ".webp":
        return "image/webp"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    if suffix == ".svg":
        return "image/svg+xml"
    return "application/octet-stream"


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    branding = site_config.get("branding")
    if isinstance(branding, Mapping):
        logo = branding.get("logo")
        if isinstance(logo, Mapping) and isinstance(logo.get("icon_path"), str):
            return _require_existing_asset(logo["icon_path"], "branding.logo.icon_path")

    return _require_existing_asset("/static/img/brand/logo-icon.webp", "branding.logo.icon_path")


def _resolve_manifest_url() -> Optional[str]:
    manifest = ROOT_DIR / "site.webmanifest"
    return "/site.webmanifest" if manifest.is_file() else None


def _loaded_experience_types_payload() -> Mapping[str, Any]:
    payload = load_experience_types()
    if not isinstance(payload, Mapping):
        raise StylesIndexConfigError("load_experience_types() must return a mapping/object.")
    if "experience_types" not in payload:
        raise StylesIndexConfigError("load_experience_types() payload missing 'experience_types'.")
    _ensure_list(payload["experience_types"], "experience_types")
    return payload


def _family_label(
    families_by_id: Mapping[str, Any],
    family_id: str,
    lang: str,
) -> str:
    if family_id and family_id in families_by_id:
        family = families_by_id[family_id]
        if isinstance(family, Mapping):
            return _localized(
                family.get("label") or family.get("title") or family.get("name"),
                lang,
                default=family_id.replace("_", " ").replace("-", " ").title(),
            )
    if family_id:
        return family_id.replace("_", " ").replace("-", " ").title()
    return "Travel Style"


def _primary_strength(item: Mapping[str, Any], lang: str) -> str:
    explicit = _localized(
        item.get("primary_strength") or item.get("signature_strength") or item.get("core_strength"),
        lang,
        default="",
    )
    if explicit:
        return explicit

    baseline = item.get("baseline_scores")
    if isinstance(baseline, Mapping) and baseline:
        normalized_scores: List[tuple[str, float]] = []
        for key, value in baseline.items():
            if isinstance(value, (int, float)):
                normalized_scores.append((str(key), float(value)))
        if normalized_scores:
            top_key = sorted(normalized_scores, key=lambda pair: pair[1], reverse=True)[0][0]
            return top_key.replace("_", " ").replace("-", " ").title()

    return ""


def _normalize_experience_type(
    item: Mapping[str, Any],
    *,
    families_by_id: Mapping[str, Any],
    lang: str,
) -> Dict[str, Any]:
    slug = _clean_string(item.get("slug"))
    if not slug:
        raise StylesIndexConfigError("Experience type item is missing slug.")

    order_raw = item.get("order")
    if not isinstance(order_raw, int):
        raise StylesIndexConfigError(f"Experience type {slug!r} must have integer order.")

    title = _localized(
        item.get("title") or item.get("name") or item.get("label"),
        lang,
        default=slug.replace("-", " ").title(),
    )
    short_label = _localized(
        item.get("short_label") or item.get("subtitle") or item.get("tagline"),
        lang,
        default="",
    )
    summary = _localized(
        item.get("summary")
        or item.get("description")
        or item.get("intro")
        or (item.get("seo", {}) if isinstance(item.get("seo"), Mapping) else {}).get("description"),
        lang,
        default="A distinct travel style within the TourVsTravel reference system.",
    )
    family_id = _clean_string(
        item.get("family") or item.get("family_id") or item.get("group") or item.get("category"),
        default="travel_style",
    )

    return {
        "id": _clean_string(item.get("id"), default=slug),
        "slug": slug,
        "order": order_raw,
        "display_order": f"{order_raw:02d}",
        "title": title,
        "short_label": short_label,
        "summary": summary,
        "family_id": family_id,
        "family_label": _family_label(families_by_id, family_id, lang),
        "primary_strength": _primary_strength(item, lang),
        "href": f"/{lang}/styles/{slug}/",
    }


def _normalize_styles_for_lang(payload: Mapping[str, Any], lang: str) -> List[Dict[str, Any]]:
    raw_items = _ensure_list(payload.get("experience_types"), "experience_types")
    families_by_id_raw = payload.get("families_by_id", {})
    if not isinstance(families_by_id_raw, Mapping):
        families_by_id_raw = {}

    normalized: List[Dict[str, Any]] = []
    seen_slugs: set[str] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, Mapping):
            raise StylesIndexConfigError("Each experience type must be a mapping/object.")
        if raw_item.get("enabled", True) is not True:
            continue

        item = _normalize_experience_type(raw_item, families_by_id=families_by_id_raw, lang=lang)
        if item["slug"] in seen_slugs:
            raise StylesIndexConfigError(f"Duplicate experience type slug: {item['slug']}")
        seen_slugs.add(item["slug"])
        normalized.append(item)

    normalized.sort(key=lambda row: (row["order"], row["slug"]))
    if not normalized:
        raise StylesIndexConfigError("No enabled experience types available for styles index.")
    return normalized


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise StylesIndexConfigError(f"Missing templates directory: {TEMPLATES_DIR}")

    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path: Optional[Path] = None

    try:
        with NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(path.parent),
            delete=False,
            suffix=".tmp",
        ) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)

        if tmp_path is None:
            raise StylesIndexWriteError(f"Failed to create temporary file for {path}")

        tmp_path.replace(path)
    except Exception as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise StylesIndexWriteError(f"Unable to write styles index page {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise StylesIndexWriteError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise StylesIndexWriteError(f"Refusing symlink output directory: {resolved}")
    if resolved.parent.exists() and resolved.parent.is_symlink():
        raise StylesIndexWriteError(f"Refusing symlink parent for output directory: {resolved.parent}")
    return resolved


def _build_hreflang(base_url: str, languages: Sequence[str]) -> List[Dict[str, str]]:
    return [
        {
            "lang": lang,
            "url": f"{base_url}/{lang}/styles/",
        }
        for lang in languages
    ]


def _build_seo_payload(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    title: str,
    description: str,
    canonical_url: str,
    base_url: str,
    site_name: str,
    logo_url: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    locale, alternate_locales = _language_locales(site_config, lang)
    jsonld = [
        json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "Organization",
                "name": site_name,
                "url": base_url,
                "logo": f"{base_url}{logo_url}",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "WebPage",
                "name": title,
                "description": description,
                "url": canonical_url,
                "inLanguage": lang,
                "isPartOf": {
                    "@type": "WebSite",
                    "name": site_name,
                    "url": base_url,
                },
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    ]

    payload: Dict[str, Any] = {
        "lang": lang,
        "title": title,
        "description": description,
        "canonical_url": canonical_url,
        "robots_directive": "index, follow",
        "hreflang": _build_hreflang(base_url, languages),
        "og": {
            "title": title,
            "description": description,
            "image": f"{base_url}{logo_url}",
            "type": "website",
            "url": canonical_url,
            "site_name": site_name,
            "image_alt": site_name,
        },
        "twitter": {
            "card": "summary_large_image",
            "title": title,
            "description": description,
            "image": f"{base_url}{logo_url}",
            "image_alt": site_name,
        },
        "jsonld": jsonld,
        "extra_meta": [],
    }

    if locale:
        payload["og_locale"] = locale
    if alternate_locales:
        payload["og_locale_alternates"] = alternate_locales

    return payload


def _build_page_context(
    *,
    site_config: Mapping[str, Any],
    styles_payload: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    base_url = _normalize_https_base_url(site_config)
    site_name = _extract_site_name(site_config, lang)
    styles = _normalize_styles_for_lang(styles_payload, lang)
    copy = PAGE_COPY.get(lang, PAGE_COPY["en"])
    title = f"{copy['title']} | {site_name}"
    description = copy["lead"]
    canonical_url = f"{base_url}/{lang}/styles/"
    logo_url = _resolve_logo_path(site_config)
    favicon_url = logo_url
    favicon_type = _infer_mime_type_from_path(favicon_url)
    main_css_url = _require_existing_asset("/static/css/main.css", "main_css_url")
    main_js_url = _require_existing_asset("/static/js/main.js", "main_js_url")

    seo_payload = _build_seo_payload(
        site_config=site_config,
        lang=lang,
        title=title,
        description=description,
        canonical_url=canonical_url,
        base_url=base_url,
        site_name=site_name,
        logo_url=logo_url,
        languages=languages,
    )

    return {
        "base_url": base_url,
        "lang": lang,
        "page_lang": lang,
        "current_lang": lang,
        "language": lang,
        "page_dir": _language_direction(site_config, lang),
        "is_rtl": _language_direction(site_config, lang) == "rtl",
        "site_name": site_name,
        "style_count": len(styles),
        "styles": styles,
        "copy": copy,
        "canonical_url": canonical_url,
        "seo": seo_payload,
        "hreflang": seo_payload["hreflang"],
        "meta_desc": description,
        "robots_directive": seo_payload["robots_directive"],
        "body_class": "page-styles-index",
        "current_year": datetime.now(timezone.utc).year,
        "site_tagline": "",
        "site_summary": "",
        "theme_color": _extract_theme_color(site_config),
        "referrer_policy": "strict-origin-when-cross-origin",
        "csp_meta_policy": None,
        "main_css_url": main_css_url,
        "main_js_url": main_js_url,
        "favicon_url": favicon_url,
        "favicon_type": favicon_type,
        "apple_touch_icon_url": favicon_url,
        "manifest_url": _resolve_manifest_url(),
        "preload_assets": [
            {
                "href": main_css_url,
                "as": "style",
                "type": "text/css",
            }
        ],
        "page_css_assets": [],
        "page_js_assets": [],
        "active_nav": "styles",
        "footer_note": "",
    }


def render_styles_index_page(
    *,
    site_config: Mapping[str, Any],
    styles_payload: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise StylesIndexRenderError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc

    context = _build_page_context(
        site_config=site_config,
        styles_payload=styles_payload,
        lang=lang,
        languages=languages,
    )

    try:
        return template.render(**context)
    except TemplateError as exc:
        raise StylesIndexRenderError(f"Unable to render styles index page [{lang}]: {exc}") from exc


# ============================================================================
# Public API
# ============================================================================

def generate_styles_index_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise StylesIndexConfigError("load_site_config() must return a mapping/object.")

    styles_payload = _loaded_experience_types_payload()

    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise StylesIndexConfigError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)

    if not languages:
        raise StylesIndexConfigError("No enabled languages available for styles index generation.")

    rendered: List[tuple[Path, str, str]] = []
    for lang in languages:
        html_output = render_styles_index_page(
            site_config=site_config,
            styles_payload=styles_payload,
            lang=lang,
            languages=languages,
        )
        output_path = safe_output_dir / lang / "styles" / "index.html"
        rendered.append((output_path, html_output, lang))

    written: List[Path] = []
    for output_path, html_output, lang in rendered:
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated styles index page [%s] -> %s", lang, output_path)

    log.info("Styles index generation completed successfully. Files written: %d", len(written))
    return written


# ============================================================================
# CLI
# ============================================================================

def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate multilingual TourVsTravel styles index pages."
    )
    parser.add_argument(
        "--lang",
        type=str,
        default=None,
        help="Generate one language only, e.g. en, ar, fr, es, de, zh, ja.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory root. Default: ./output",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    try:
        generate_styles_index_pages(
            requested_lang=args.lang,
            output_dir=args.output_dir,
        )
    except GenerateStylesIndexError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected styles index generation failure: %s", exc)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
