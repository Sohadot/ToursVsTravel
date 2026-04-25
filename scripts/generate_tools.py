#!/usr/bin/env python3
"""
TourVsTravel — Tools Hub Generator
==================================

Generate multilingual official Tools Hub pages:

    /en/tools/
    /ar/tools/
    /fr/tools/
    /es/tools/
    /de/tools/
    /zh/tools/
    /ja/tools/

The Tools Hub presents TourVsTravel as a decision-support system rather than a
generic travel content site. It only links to currently available reference
layers and labels future tools as frameworks, not live engines.
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


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("generate_tools")


ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT_DIR / "static"
TEMPLATES_DIR = ROOT_DIR / "templates"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/tools.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")


class GenerateToolsError(Exception):
    """Raised when tools page generation fails."""


class ToolsConfigError(GenerateToolsError):
    """Raised when configuration is invalid."""


class ToolsRenderError(GenerateToolsError):
    """Raised when template rendering fails."""


class ToolsWriteError(GenerateToolsError):
    """Raised when output writing fails."""


PAGE_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "eyebrow": "Decision Tools · Travel Fit · Structured Comparison",
        "title": "Tools for Choosing How to Travel",
        "lead": "TourVsTravel tools are not booking widgets. They are decision instruments designed to clarify travel fit before money, time, and expectations are committed.",
        "actions_label": "Tools actions",
        "primary_action": "Start With Compare",
        "secondary_action": "Explore the 17 Styles",
        "methodology_action": "Read the Methodology",
        "panel_label": "Tools system signals",
        "panel_card_1_label": "System role",
        "panel_card_1_value": "Translate preference into structured fit.",
        "panel_card_2_label": "Decision logic",
        "panel_card_2_value": "Compare constraints, autonomy, burden, and depth.",
        "panel_card_3_label": "Reference tools",
        "panel_card_3_value": "tools and frameworks in the current hub.",
        "grid_kicker": "Operational layer",
        "grid_title": "Reference tools available now",
        "grid_lead": "This hub gathers the active decision layers of the site. Each tool is either a live reference page or a structured framework that will become a deeper engine later.",
        "signals_label": "Tool signals",
        "system_kicker": "Decision sequence",
        "system_title": "How the tools work together",
        "system_lead": "The tools are arranged as a progression: understand the styles, compare their behavior, then narrow the match according to constraints and intent.",
        "final_kicker": "Next action",
        "final_title": "Begin with the comparison layer",
        "final_lead": "The strongest first step is to compare travel forms before comparing destinations. The same place can produce very different outcomes depending on the structure of travel.",
    },
    "ar": {
        "eyebrow": "أدوات قرار · ملاءمة السفر · مقارنة منظمة",
        "title": "أدوات لاختيار كيف تسافر",
        "lead": "أدوات TourVsTravel ليست أدوات حجز. إنها أدوات قرار تساعد على توضيح ملاءمة نمط السفر قبل الالتزام بالمال والوقت والتوقعات.",
        "actions_label": "إجراءات الأدوات",
        "primary_action": "ابدأ بالمقارنة",
        "secondary_action": "استكشف الأنماط الـ 17",
        "methodology_action": "اقرأ المنهجية",
        "panel_label": "إشارات نظام الأدوات",
        "panel_card_1_label": "دور النظام",
        "panel_card_1_value": "تحويل التفضيل إلى ملاءمة منظمة.",
        "panel_card_2_label": "منطق القرار",
        "panel_card_2_value": "مقارنة القيود والاستقلالية والعبء وعمق التجربة.",
        "panel_card_3_label": "أدوات مرجعية",
        "panel_card_3_value": "أدوات وأطر داخل المحور الحالي.",
        "grid_kicker": "طبقة تشغيلية",
        "grid_title": "أدوات مرجعية متاحة الآن",
        "grid_lead": "يجمع هذا المحور طبقات القرار النشطة في الموقع. كل أداة إما صفحة مرجعية مباشرة أو إطار منظم سيتحول لاحقًا إلى محرك أعمق.",
        "signals_label": "إشارات الأداة",
        "system_kicker": "تسلسل القرار",
        "system_title": "كيف تعمل الأدوات معًا",
        "system_lead": "الأدوات مرتبة كتدرج: فهم الأنماط، مقارنة سلوكها، ثم تضييق الاختيار حسب القيود والنية.",
        "final_kicker": "الإجراء التالي",
        "final_title": "ابدأ بطبقة المقارنة",
        "final_lead": "أفضل خطوة أولى هي مقارنة أشكال السفر قبل مقارنة الوجهات. نفس المكان قد ينتج نتائج مختلفة جدًا حسب بنية السفر.",
    },
    "fr": {
        "eyebrow": "Outils de décision · adéquation voyage · comparaison structurée",
        "title": "Des outils pour choisir comment voyager",
        "lead": "Les outils TourVsTravel ne sont pas des widgets de réservation. Ce sont des instruments de décision conçus pour clarifier l’adéquation avant l’engagement.",
        "actions_label": "Actions des outils",
        "primary_action": "Commencer par comparer",
        "secondary_action": "Explorer les 17 styles",
        "methodology_action": "Lire la méthodologie",
        "panel_label": "Signaux du système d’outils",
        "panel_card_1_label": "Rôle du système",
        "panel_card_1_value": "Transformer une préférence en adéquation structurée.",
        "panel_card_2_label": "Logique de décision",
        "panel_card_2_value": "Comparer contraintes, autonomie, charge et profondeur.",
        "panel_card_3_label": "Outils de référence",
        "panel_card_3_value": "outils et cadres dans le hub actuel.",
        "grid_kicker": "Couche opérationnelle",
        "grid_title": "Outils de référence disponibles",
        "grid_lead": "Ce hub rassemble les couches de décision actives du site. Chaque outil est une page de référence ou un cadre structuré appelé à devenir plus profond.",
        "signals_label": "Signaux de l’outil",
        "system_kicker": "Séquence de décision",
        "system_title": "Comment les outils fonctionnent ensemble",
        "system_lead": "Les outils progressent de la compréhension des styles vers la comparaison, puis vers l’adéquation selon les contraintes et l’intention.",
        "final_kicker": "Prochaine action",
        "final_title": "Commencer par la comparaison",
        "final_lead": "La première étape la plus forte consiste à comparer les formes de voyage avant les destinations.",
    },
    "es": {
        "eyebrow": "Herramientas de decisión · ajuste de viaje · comparación estructurada",
        "title": "Herramientas para elegir cómo viajar",
        "lead": "Las herramientas de TourVsTravel no son widgets de reserva. Son instrumentos de decisión para aclarar el ajuste antes de comprometer dinero, tiempo y expectativas.",
        "actions_label": "Acciones de herramientas",
        "primary_action": "Empezar comparando",
        "secondary_action": "Explorar los 17 estilos",
        "methodology_action": "Leer la metodología",
        "panel_label": "Señales del sistema de herramientas",
        "panel_card_1_label": "Rol del sistema",
        "panel_card_1_value": "Traducir preferencia en ajuste estructurado.",
        "panel_card_2_label": "Lógica de decisión",
        "panel_card_2_value": "Comparar restricciones, autonomía, carga y profundidad.",
        "panel_card_3_label": "Herramientas de referencia",
        "panel_card_3_value": "herramientas y marcos en el hub actual.",
        "grid_kicker": "Capa operativa",
        "grid_title": "Herramientas de referencia disponibles",
        "grid_lead": "Este hub reúne las capas activas de decisión del sitio. Cada herramienta es una página de referencia o un marco estructurado.",
        "signals_label": "Señales de herramienta",
        "system_kicker": "Secuencia de decisión",
        "system_title": "Cómo trabajan juntas las herramientas",
        "system_lead": "Las herramientas avanzan desde entender estilos, compararlos y luego reducir la elección según restricciones e intención.",
        "final_kicker": "Siguiente acción",
        "final_title": "Empieza por la comparación",
        "final_lead": "El primer paso más sólido es comparar formas de viajar antes de comparar destinos.",
    },
    "de": {
        "eyebrow": "Entscheidungswerkzeuge · Reisepassung · strukturierter Vergleich",
        "title": "Werkzeuge zur Wahl der Reiseform",
        "lead": "TourVsTravel-Werkzeuge sind keine Buchungswidgets. Sie sind Entscheidungsinstrumente, um Passung vor Zeit-, Geld- und Erwartungsbindung zu klären.",
        "actions_label": "Werkzeugaktionen",
        "primary_action": "Mit Vergleich beginnen",
        "secondary_action": "17 Stile erkunden",
        "methodology_action": "Methodik lesen",
        "panel_label": "Signale des Werkzeugsystems",
        "panel_card_1_label": "Systemrolle",
        "panel_card_1_value": "Vorliebe in strukturierte Passung übersetzen.",
        "panel_card_2_label": "Entscheidungslogik",
        "panel_card_2_value": "Einschränkungen, Autonomie, Last und Tiefe vergleichen.",
        "panel_card_3_label": "Referenzwerkzeuge",
        "panel_card_3_value": "Werkzeuge und Rahmen im aktuellen Hub.",
        "grid_kicker": "Operative Ebene",
        "grid_title": "Verfügbare Referenzwerkzeuge",
        "grid_lead": "Dieser Hub bündelt die aktiven Entscheidungsebenen der Website. Jedes Werkzeug ist eine Referenzseite oder ein strukturierter Rahmen.",
        "signals_label": "Werkzeugsignale",
        "system_kicker": "Entscheidungsfolge",
        "system_title": "Wie die Werkzeuge zusammenarbeiten",
        "system_lead": "Die Werkzeuge führen vom Verständnis der Stile zum Vergleich und schließlich zur Passung.",
        "final_kicker": "Nächste Aktion",
        "final_title": "Mit der Vergleichsebene beginnen",
        "final_lead": "Der stärkste erste Schritt ist, Reiseformen zu vergleichen, bevor Reiseziele verglichen werden.",
    },
    "zh": {
        "eyebrow": "决策工具 · 旅行适配 · 结构化比较",
        "title": "选择如何旅行的工具",
        "lead": "TourVsTravel 工具不是预订组件，而是帮助你在投入金钱、时间和期待之前判断旅行适配度的决策工具。",
        "actions_label": "工具操作",
        "primary_action": "从比较开始",
        "secondary_action": "探索17种方式",
        "methodology_action": "阅读方法论",
        "panel_label": "工具系统信号",
        "panel_card_1_label": "系统角色",
        "panel_card_1_value": "把偏好转化为结构化适配。",
        "panel_card_2_label": "决策逻辑",
        "panel_card_2_value": "比较限制、自主性、负担与体验深度。",
        "panel_card_3_label": "参考工具",
        "panel_card_3_value": "个当前工具与框架。",
        "grid_kicker": "操作层",
        "grid_title": "当前可用的参考工具",
        "grid_lead": "本页面汇集网站当前的决策层。每个工具都是一个参考页面或结构化框架。",
        "signals_label": "工具信号",
        "system_kicker": "决策顺序",
        "system_title": "工具如何协同工作",
        "system_lead": "工具从理解旅行方式开始，再进入比较，最后根据限制与意图缩小适配范围。",
        "final_kicker": "下一步",
        "final_title": "从比较层开始",
        "final_lead": "最强的第一步，是先比较旅行形式，再比较目的地。",
    },
    "ja": {
        "eyebrow": "意思決定ツール · 旅行適合 · 構造化比較",
        "title": "どう旅するかを選ぶためのツール",
        "lead": "TourVsTravel のツールは予約ウィジェットではありません。時間、費用、期待を投じる前に旅行の適合性を明確にするための意思決定ツールです。",
        "actions_label": "ツール操作",
        "primary_action": "比較から始める",
        "secondary_action": "17スタイルを探索",
        "methodology_action": "方法論を読む",
        "panel_label": "ツールシステムのシグナル",
        "panel_card_1_label": "システムの役割",
        "panel_card_1_value": "好みを構造化された適合へ変換する。",
        "panel_card_2_label": "意思決定ロジック",
        "panel_card_2_value": "制約、自律性、負担、深度を比較する。",
        "panel_card_3_label": "参照ツール",
        "panel_card_3_value": "現在のハブ内のツールとフレームワーク。",
        "grid_kicker": "運用レイヤー",
        "grid_title": "現在利用できる参照ツール",
        "grid_lead": "このハブは、サイト内の意思決定レイヤーをまとめます。各ツールは参照ページまたは構造化フレームワークです。",
        "signals_label": "ツールシグナル",
        "system_kicker": "意思決定シーケンス",
        "system_title": "ツールがどう連携するか",
        "system_lead": "ツールは、スタイルの理解、比較、制約と意図による絞り込みへ進みます。",
        "final_kicker": "次の行動",
        "final_title": "比較レイヤーから始める",
        "final_lead": "最も強い第一歩は、目的地より先に旅行形式を比較することです。",
    },
}

TOOL_COPY: Dict[str, List[Dict[str, Any]]] = {
    "en": [
        {
            "title": "Travel Style Comparator",
            "type": "Live reference tool",
            "status": "Available",
            "status_key": "available",
            "description": "Compare travel forms by constraints, autonomy, support, complexity, and experience depth.",
            "signals": ["Best first step", "Connects to criteria", "Works across all styles"],
            "route": "compare",
            "action": "Open comparison layer",
        },
        {
            "title": "17 Styles Reference Map",
            "type": "Live reference layer",
            "status": "Available",
            "status_key": "available",
            "description": "Explore the full travel-style ontology before narrowing the right fit.",
            "signals": ["17 structured styles", "Individual reference pages", "Multilingual layer"],
            "route": "styles",
            "action": "Explore all styles",
        },
        {
            "title": "Methodology Framework",
            "type": "Reference doctrine",
            "status": "Available",
            "status_key": "available",
            "description": "Understand how TourVsTravel compares travel forms without reducing them to generic preference labels.",
            "signals": ["Decision criteria", "Scoring logic", "Conceptual foundation"],
            "route": "methodology",
            "action": "Read methodology",
        },
        {
            "title": "Find Your Match",
            "type": "Live decision tool",
            "status": "Available",
            "status_key": "available",
            "description": "A guided matching layer that converts traveler constraints into recommended travel-style directions.",
            "signals": ["Traveler intent", "Budget and burden", "Autonomy preference"],
            "route": "find_your_match",
            "action": "Open Find Your Match",
        },
    ],
    "ar": [
        {
            "title": "مقارن أنماط السفر",
            "type": "أداة مرجعية مباشرة",
            "status": "متاح",
            "status_key": "available",
            "description": "قارن أشكال السفر حسب القيود والاستقلالية والدعم والتعقيد وعمق التجربة.",
            "signals": ["أفضل خطوة أولى", "مرتبط بالمعايير", "يعمل عبر كل الأنماط"],
            "route": "compare",
            "action": "افتح طبقة المقارنة",
        },
        {
            "title": "خريطة الأنماط الـ 17",
            "type": "طبقة مرجعية مباشرة",
            "status": "متاح",
            "status_key": "available",
            "description": "استكشف أنماط السفر قبل تضييق الاختيار المناسب.",
            "signals": ["17 نمطًا منظمًا", "صفحات مرجعية فردية", "طبقة متعددة اللغات"],
            "route": "styles",
            "action": "استكشف كل الأنماط",
        },
        {
            "title": "إطار المنهجية",
            "type": "عقيدة مرجعية",
            "status": "متاح",
            "status_key": "available",
            "description": "افهم كيف يقارن TourVsTravel أشكال السفر دون اختزالها إلى تفضيلات عامة.",
            "signals": ["معايير قرار", "منطق تقييم", "أساس مفاهيمي"],
            "route": "methodology",
            "action": "اقرأ المنهجية",
        },
        {
            "title": "اعرف الأنسب لك",
            "type": "أداة قرار مباشرة",
            "status": "متاح",
            "status_key": "available",
            "description": "طبقة مطابقة موجهة تحول قيود المسافر إلى اتجاهات أنماط سفر مقترحة.",
            "signals": ["نية المسافر", "الميزانية والعبء", "تفضيل الاستقلالية"],
            "route": "find_your_match",
            "action": "افتح أداة الملاءمة",
        },
    ],
}

SYSTEM_STEPS: Dict[str, List[Dict[str, str]]] = {
    "en": [
        {"label": "Step 1", "value": "Identify the travel form."},
        {"label": "Step 2", "value": "Compare constraints and tradeoffs."},
        {"label": "Step 3", "value": "Move toward fit, not generic preference."},
    ],
    "ar": [
        {"label": "الخطوة 1", "value": "تحديد شكل السفر."},
        {"label": "الخطوة 2", "value": "مقارنة القيود والمفاضلات."},
        {"label": "الخطوة 3", "value": "الانتقال نحو الملاءمة لا التفضيل العام."},
    ],
    "fr": [
        {"label": "Étape 1", "value": "Identifier la forme de voyage."},
        {"label": "Étape 2", "value": "Comparer contraintes et compromis."},
        {"label": "Étape 3", "value": "Aller vers l’adéquation, pas la préférence générique."},
    ],
}

ROUTES = {
    "compare": "compare",
    "styles": "styles",
    "methodology": "methodology",
    "find_your_match": "tools/find-your-match",
}


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ToolsConfigError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise ToolsConfigError(f"{label} must be a string.")
    text = value.strip()
    if not allow_empty and not text:
        raise ToolsConfigError(f"{label} must not be empty.")
    return text


def _get_nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _localized(value: Any, lang: str, label: str, *, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip() or default
    if isinstance(value, Mapping):
        for key in (lang, "en"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    if default:
        return default
    raise ToolsConfigError(f"{label} must be a string or language map.")


def _is_absolute_https_url(value: str) -> bool:
    try:
        parsed = urlparse(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.netloc)
            and parsed.username is None
            and parsed.password is None
        )
    except Exception:
        return False


def _normalize_https_base_url(site_config: Mapping[str, Any]) -> str:
    raw = _get_nested(site_config, ("site", "base_url"), "https://tourvstravel.com")
    base_url = _ensure_string(raw, "site.base_url").rstrip("/")
    if not _is_absolute_https_url(base_url):
        raise ToolsConfigError(f"site.base_url must be an absolute HTTPS URL: {base_url!r}")
    return base_url


def _extract_enabled_languages(site_config: Mapping[str, Any]) -> List[str]:
    raw = _get_nested(site_config, ("languages", "supported"), None)
    if not isinstance(raw, list):
        raw = _get_nested(site_config, ("languages", "enabled"), None)
    if not isinstance(raw, list):
        return list(SUPPORTED_LANGUAGES)

    languages: List[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            code = _ensure_string(item.get("code"), "languages[].code")
            if item.get("enabled", True) is False:
                continue
        else:
            code = _ensure_string(item, "languages[]")
        if code in SUPPORTED_LANGUAGES and code not in languages:
            languages.append(code)
    return languages or list(SUPPORTED_LANGUAGES)


def _language_direction(site_config: Mapping[str, Any], lang: str) -> str:
    direction = _get_nested(site_config, ("languages", "direction", lang), None)
    if direction in {"rtl", "ltr"}:
        return str(direction)
    return "rtl" if lang == "ar" else "ltr"


def _language_locales(site_config: Mapping[str, Any], lang: str) -> tuple[Optional[str], List[str]]:
    locale_map = _get_nested(site_config, ("languages", "locales"), {})
    if not isinstance(locale_map, Mapping):
        return None, []
    current = locale_map.get(lang)
    alternates = [str(value) for key, value in locale_map.items() if key != lang and isinstance(value, str)]
    return (str(current) if isinstance(current, str) else None), alternates


def _extract_site_name(site_config: Mapping[str, Any], lang: str) -> str:
    name = _get_nested(site_config, ("site", "name"), "TourVsTravel")
    return _localized(name, lang, "site.name", default="TourVsTravel")


def _extract_theme_color(site_config: Mapping[str, Any]) -> str:
    color = _get_nested(site_config, ("branding", "theme_color"), "#0f172a")
    if not isinstance(color, str) or not color.strip():
        return "#0f172a"
    return color.strip()


def _infer_mime_type_from_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".png":
        return "image/png"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".webp":
        return "image/webp"
    return "image/x-icon"


def _require_existing_asset(public_path: str, label: str) -> str:
    path = _ensure_string(public_path, label)
    if not path.startswith("/static/"):
        raise ToolsConfigError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise ToolsConfigError(f"{label} points outside static/: {path}") from exc
    if not asset_path.is_file():
        raise ToolsConfigError(f"{label} points to a missing static asset: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo"), {})
    if not isinstance(logo, Mapping):
        logo = {}
    icon_path = logo.get("icon_path", "/static/img/brand/logo-icon.webp")
    return _require_existing_asset(_ensure_string(icon_path, "branding.logo.icon_path"), "branding.logo.icon_path")


def _resolve_manifest_url() -> Optional[str]:
    manifest_path = STATIC_DIR / "site.webmanifest"
    if manifest_path.is_file():
        return "/static/site.webmanifest"
    return None


def _count_styles() -> int:
    payload = load_experience_types()
    if not isinstance(payload, Mapping):
        raise ToolsConfigError("load_experience_types() must return a mapping/object.")
    active = payload.get("active_experience_types") or payload.get("experience_types")
    if not isinstance(active, list) or not active:
        raise ToolsConfigError("experience_types must provide active experience types.")
    return len(active)


def _localize_tools(lang: str) -> List[Dict[str, Any]]:
    raw_tools = TOOL_COPY.get(lang, TOOL_COPY["en"])
    tools: List[Dict[str, Any]] = []
    for raw in raw_tools:
        route_key = _ensure_string(raw.get("route"), "tool.route")
        if route_key not in ROUTES:
            raise ToolsConfigError(f"Unknown tool route key: {route_key}")
        tools.append(
            {
                "title": _ensure_string(raw.get("title"), "tool.title"),
                "type": _ensure_string(raw.get("type"), "tool.type"),
                "status": _ensure_string(raw.get("status"), "tool.status"),
                "status_key": _ensure_string(raw.get("status_key"), "tool.status_key"),
                "description": _ensure_string(raw.get("description"), "tool.description"),
                "signals": list(raw.get("signals", [])),
                "href": f"/{lang}/{ROUTES[route_key]}/",
                "action": _ensure_string(raw.get("action"), "tool.action"),
            }
        )
    return tools


def _system_steps(lang: str) -> List[Dict[str, str]]:
    return SYSTEM_STEPS.get(lang, SYSTEM_STEPS["en"])


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise ToolsConfigError(f"Missing templates directory: {TEMPLATES_DIR}")
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
        with NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp") as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)
    except Exception as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise ToolsWriteError(f"Unable to write tools page {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise ToolsWriteError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise ToolsWriteError(f"Refusing symlink output directory: {resolved}")
    if resolved.parent.exists() and resolved.parent.is_symlink():
        raise ToolsWriteError(f"Refusing symlink parent for output directory: {resolved.parent}")
    return resolved


def _build_hreflang(base_url: str, languages: Sequence[str]) -> List[Dict[str, str]]:
    return [{"lang": lang, "url": f"{base_url}/{lang}/tools/"} for lang in languages]


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
    tools: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    locale, alternate_locales = _language_locales(site_config, lang)
    jsonld = [
        json.dumps(
            {
                "@context": "https://schema.org",
                "@type": "WebPage",
                "name": title,
                "description": description,
                "url": canonical_url,
                "inLanguage": lang,
                "isPartOf": {"@type": "WebSite", "name": site_name, "url": base_url},
                "about": [{"@type": "Thing", "name": tool["title"]} for tool in tools],
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
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
    lang: str,
    languages: Sequence[str],
    style_count: int,
) -> Dict[str, Any]:
    base_url = _normalize_https_base_url(site_config)
    site_name = _extract_site_name(site_config, lang)
    copy = PAGE_COPY.get(lang, PAGE_COPY["en"])
    tools = _localize_tools(lang)
    logo_url = _resolve_logo_path(site_config)
    favicon_url = logo_url
    canonical_url = f"{base_url}/{lang}/tools/"
    title = f"{copy['title']} | {site_name}"
    description = copy["lead"]
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
        tools=tools,
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
        "tool_count": len(tools),
        "style_count": style_count,
        "tools": tools,
        "system_steps": _system_steps(lang),
        "copy": copy,
        "canonical_url": canonical_url,
        "seo": seo_payload,
        "hreflang": seo_payload["hreflang"],
        "meta_desc": description,
        "robots_directive": seo_payload["robots_directive"],
        "body_class": "page-tools",
        "current_year": datetime.now(timezone.utc).year,
        "site_tagline": "",
        "site_summary": "",
        "theme_color": _extract_theme_color(site_config),
        "referrer_policy": "strict-origin-when-cross-origin",
        "csp_meta_policy": None,
        "main_css_url": main_css_url,
        "main_js_url": main_js_url,
        "favicon_url": favicon_url,
        "favicon_type": _infer_mime_type_from_path(favicon_url),
        "apple_touch_icon_url": favicon_url,
        "manifest_url": _resolve_manifest_url(),
        "preload_assets": [{"href": main_css_url, "as": "style", "type": "text/css"}],
        "page_css_assets": [],
        "page_js_assets": [],
        "active_nav": "tools",
        "footer_note": "",
    }


def render_tools_page(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
    style_count: int,
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise ToolsRenderError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc

    context = _build_page_context(
        site_config=site_config,
        lang=lang,
        languages=languages,
        style_count=style_count,
    )

    try:
        html_output = template.render(**context)
    except TemplateError as exc:
        raise ToolsRenderError(f"Unable to render tools page [{lang}]: {exc}") from exc

    if not html_output.strip():
        raise ToolsRenderError(f"Rendered tools page is empty for language {lang!r}.")
    return html_output


def generate_tools_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise ToolsConfigError("load_site_config() must return a mapping/object.")
    style_count = _count_styles()

    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise ToolsConfigError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)

    if not languages:
        raise ToolsConfigError("No enabled languages available for tools generation.")

    rendered: List[tuple[Path, str, str]] = []
    for lang in languages:
        html_output = render_tools_page(
            site_config=site_config,
            lang=lang,
            languages=languages,
            style_count=style_count,
        )
        output_path = safe_output_dir / lang / "tools" / "index.html"
        rendered.append((output_path, html_output, lang))

    written: List[Path] = []
    for output_path, html_output, lang in rendered:
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated tools page [%s] -> %s", lang, output_path)

    log.info("Tools generation completed successfully. Files written: %d", len(written))
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate multilingual TourVsTravel tools hub pages.")
    parser.add_argument("--lang", type=str, default=None, help="Generate one language only.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory root.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        generate_tools_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateToolsError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected tools generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
