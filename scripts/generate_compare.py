#!/usr/bin/env python3
"""
TourVsTravel — Compare Index Generator
======================================

Generate the multilingual comparison decision-system entry page:

    /en/compare/
    /ar/compare/
    /fr/compare/
    /es/compare/
    /de/compare/
    /zh/compare/
    /ja/compare/

The page is intentionally not an interactive tool yet. It is the formal
reference layer that explains what TourVsTravel compares and why.
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

from scripts.loaders import load_comparison_criteria, load_experience_types, load_site_config


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("generate_compare")


ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT_DIR / "static"
TEMPLATES_DIR = ROOT_DIR / "templates"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/compare.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")


class GenerateCompareError(Exception):
    """Raised when compare page generation fails."""


class CompareConfigError(GenerateCompareError):
    """Raised when compare source data or configuration is invalid."""


class CompareRenderError(GenerateCompareError):
    """Raised when compare page rendering fails."""


class CompareWriteError(GenerateCompareError):
    """Raised when compare page writing fails."""


PAGE_COPY: Dict[str, Dict[str, Any]] = {
    "en": {
        "eyebrow": "Compare Layer • Decision System Activation",
        "title": "Compare travel styles by decision fit, not destination alone.",
        "lead": "The same destination can reward or punish different travel structures. TourVsTravel compares styles through constraints, operational burden, support, depth, predictability, and traveler fit.",
        "actions_label": "Compare page actions",
        "primary_action": "Explore All 17 Styles",
        "secondary_action": "Read the Methodology",
        "system_panel_label": "Comparison system summary",
        "criteria_kicker": "Decision criteria",
        "criteria_title": "What the comparison system measures",
        "criteria_lead": "Each criterion turns a vague travel preference into a publishable decision signal.",
        "low_label": "Low",
        "high_label": "High",
        "pairs_kicker": "Featured comparisons",
        "pairs_title": "Start with the core travel tradeoffs",
        "pairs_lead": "These pairs show why the useful question is not only where to go, but how to move through the place.",
        "signal_label": "Decision signal",
        "explore_styles_label": "Explore styles",
        "method_kicker": "How comparison works",
        "method_title": "A structured path from preference to fit",
        "method_lead": "The compare layer starts with style behavior, applies weighted criteria, then explains the tradeoff instead of hiding it behind a single recommendation.",
        "method_steps": [
            ("Define the travel structures", "Each style is treated as an operating model with its own cost, control, support, and depth profile."),
            ("Apply the criteria", "The same criteria are used across styles so the comparison stays consistent and repeatable."),
            ("Explain the tradeoff", "The output describes why one style may fit better under a specific traveler constraint."),
        ],
        "final_kicker": "Next step",
        "final_title": "Use styles as the map and compare as the decision layer.",
        "final_lead": "Begin with the reference index, then use comparison logic to understand which travel form fits the trip you actually want to take.",
        "pair_summaries": {
            "guided_group_tour:independent_travel": "A comparison between outsourced structure and self-directed control.",
            "backpacking:luxury_travel": "A comparison between value-density and friction-reduced comfort.",
            "family_travel:solo_travel": "A comparison between coordination burden and individual autonomy.",
        },
        "pair_signals": {
            "guided_group_tour:independent_travel": "support vs autonomy",
            "backpacking:luxury_travel": "cost pressure vs comfort",
            "family_travel:solo_travel": "shared logistics vs personal flexibility",
        },
    },
    "ar": {
        "eyebrow": "طبقة المقارنة • تفعيل نظام القرار",
        "title": "قارن أنماط السفر حسب الملاءمة، لا حسب الوجهة وحدها.",
        "lead": "نفس الوجهة قد تناسب شكل سفر وتُضعف شكلًا آخر. يقارن TourVsTravel الأنماط عبر القيود، العبء التشغيلي، الدعم، العمق، قابلية التوقع، وملاءمة المسافر.",
        "actions_label": "إجراءات صفحة المقارنة",
        "primary_action": "استكشف كل الأنماط",
        "secondary_action": "اقرأ المنهجية",
        "system_panel_label": "ملخص نظام المقارنة",
        "criteria_kicker": "معايير القرار",
        "criteria_title": "ما الذي يقيسه نظام المقارنة",
        "criteria_lead": "كل معيار يحول تفضيلًا غامضًا إلى إشارة قرار قابلة للنشر.",
        "low_label": "منخفض",
        "high_label": "مرتفع",
        "pairs_kicker": "مقارنات أساسية",
        "pairs_title": "ابدأ من مفاضلات السفر الجوهرية",
        "pairs_lead": "هذه المقارنات توضّح أن السؤال المفيد ليس فقط أين تذهب، بل كيف تعيش المكان.",
        "signal_label": "إشارة القرار",
        "explore_styles_label": "استكشف الأنماط",
        "method_kicker": "كيف تعمل المقارنة",
        "method_title": "مسار منظم من التفضيل إلى الملاءمة",
        "method_lead": "تبدأ طبقة المقارنة بسلوك النمط، ثم تطبق معايير موزونة، ثم تشرح المفاضلة بدل إخفائها خلف توصية واحدة.",
        "method_steps": [
            ("تعريف بنية السفر", "كل نمط يُعامل كنموذج تشغيلي له تكلفة وسيطرة ودعم وعمق خاص به."),
            ("تطبيق المعايير", "تُستخدم المعايير نفسها عبر الأنماط حتى تبقى المقارنة ثابتة وقابلة للتكرار."),
            ("شرح المفاضلة", "المخرج يوضح لماذا قد يناسب نمط معين قيود مسافر محدد."),
        ],
        "final_kicker": "الخطوة التالية",
        "final_title": "استخدم الأنماط كخريطة والمقارنة كطبقة قرار.",
        "final_lead": "ابدأ بالفهرس المرجعي، ثم استخدم منطق المقارنة لفهم شكل السفر الأنسب لرحلتك الحقيقية.",
        "pair_summaries": {},
        "pair_signals": {},
    },
    "fr": {
        "eyebrow": "Couche de comparaison • système de décision",
        "title": "Comparer les styles de voyage par adéquation, pas seulement par destination.",
        "lead": "Une même destination peut favoriser des structures de voyage différentes. TourVsTravel compare les styles par contraintes, charge opérationnelle, soutien, profondeur, prévisibilité et adéquation au voyageur.",
        "actions_label": "Actions de comparaison",
        "primary_action": "Explorer les 17 styles",
        "secondary_action": "Lire la méthodologie",
        "system_panel_label": "Résumé du système de comparaison",
        "criteria_kicker": "Critères de décision",
        "criteria_title": "Ce que mesure le système",
        "criteria_lead": "Chaque critère transforme une préférence vague en signal de décision publiable.",
        "low_label": "Faible",
        "high_label": "Élevé",
        "pairs_kicker": "Comparaisons clés",
        "pairs_title": "Commencer par les compromis essentiels",
        "pairs_lead": "La bonne question n’est pas seulement où aller, mais comment traverser le lieu.",
        "signal_label": "Signal",
        "explore_styles_label": "Explorer les styles",
        "method_kicker": "Fonctionnement",
        "method_title": "Un chemin structuré de la préférence à l’adéquation",
        "method_lead": "La couche compare le comportement des styles, applique des critères pondérés, puis explique le compromis.",
        "method_steps": [
            ("Définir les structures", "Chaque style est traité comme un modèle opérationnel."),
            ("Appliquer les critères", "Les mêmes critères gardent la comparaison cohérente."),
            ("Expliquer le compromis", "Le résultat dit pourquoi un style correspond mieux à certaines contraintes."),
        ],
        "final_kicker": "Étape suivante",
        "final_title": "Les styles sont la carte, la comparaison est la décision.",
        "final_lead": "Commencez par l’index, puis utilisez la logique de comparaison pour lire l’adéquation réelle.",
        "pair_summaries": {},
        "pair_signals": {},
    },
    "es": {
        "eyebrow": "Capa de comparación • sistema de decisión",
        "title": "Compara estilos de viaje por ajuste, no solo por destino.",
        "lead": "El mismo destino puede favorecer estructuras distintas. TourVsTravel compara estilos por restricciones, carga operativa, apoyo, profundidad, previsibilidad y ajuste al viajero.",
        "actions_label": "Acciones de comparación",
        "primary_action": "Explorar los 17 estilos",
        "secondary_action": "Leer la metodología",
        "system_panel_label": "Resumen del sistema de comparación",
        "criteria_kicker": "Criterios de decisión",
        "criteria_title": "Qué mide el sistema",
        "criteria_lead": "Cada criterio convierte una preferencia vaga en una señal de decisión publicable.",
        "low_label": "Bajo",
        "high_label": "Alto",
        "pairs_kicker": "Comparaciones destacadas",
        "pairs_title": "Empieza con los compromisos centrales",
        "pairs_lead": "La pregunta útil no es solo dónde ir, sino cómo moverse por el lugar.",
        "signal_label": "Señal",
        "explore_styles_label": "Explorar estilos",
        "method_kicker": "Cómo funciona",
        "method_title": "Un camino estructurado de preferencia a ajuste",
        "method_lead": "La capa compara comportamiento, aplica criterios ponderados y explica el compromiso.",
        "method_steps": [
            ("Definir estructuras", "Cada estilo funciona como un modelo operativo."),
            ("Aplicar criterios", "Los mismos criterios mantienen la comparación consistente."),
            ("Explicar el compromiso", "El resultado muestra por qué un estilo encaja mejor bajo ciertas restricciones."),
        ],
        "final_kicker": "Siguiente paso",
        "final_title": "Los estilos son el mapa; comparar es decidir.",
        "final_lead": "Empieza por el índice y usa la lógica de comparación para leer el ajuste real.",
        "pair_summaries": {},
        "pair_signals": {},
    },
    "de": {
        "eyebrow": "Vergleichsebene • Entscheidungssystem",
        "title": "Reisestile nach Passung vergleichen, nicht nur nach Ziel.",
        "lead": "Dasselbe Ziel kann unterschiedliche Reiseformen begünstigen. TourVsTravel vergleicht Stile nach Einschränkungen, operativer Last, Unterstützung, Tiefe, Vorhersehbarkeit und Reisendenpassung.",
        "actions_label": "Vergleichsaktionen",
        "primary_action": "Alle 17 Stile erkunden",
        "secondary_action": "Methodik lesen",
        "system_panel_label": "Zusammenfassung des Vergleichssystems",
        "criteria_kicker": "Entscheidungskriterien",
        "criteria_title": "Was das System misst",
        "criteria_lead": "Jedes Kriterium macht aus einer vagen Vorliebe ein Entscheidungssignal.",
        "low_label": "Niedrig",
        "high_label": "Hoch",
        "pairs_kicker": "Ausgewählte Vergleiche",
        "pairs_title": "Mit den zentralen Kompromissen beginnen",
        "pairs_lead": "Die nützliche Frage ist nicht nur wohin, sondern wie man den Ort erlebt.",
        "signal_label": "Signal",
        "explore_styles_label": "Stile erkunden",
        "method_kicker": "Funktionsweise",
        "method_title": "Ein strukturierter Weg von Vorliebe zu Passung",
        "method_lead": "Die Ebene vergleicht Stil Verhalten, wendet gewichtete Kriterien an und erklärt den Kompromiss.",
        "method_steps": [
            ("Strukturen definieren", "Jeder Stil wird als operatives Modell behandelt."),
            ("Kriterien anwenden", "Dieselben Kriterien halten den Vergleich konsistent."),
            ("Kompromiss erklären", "Das Ergebnis zeigt, warum ein Stil unter bestimmten Grenzen besser passt."),
        ],
        "final_kicker": "Nächster Schritt",
        "final_title": "Stile sind die Karte; Vergleich ist die Entscheidung.",
        "final_lead": "Beginne mit dem Index und nutze Vergleichslogik für echte Passung.",
        "pair_summaries": {},
        "pair_signals": {},
    },
    "zh": {
        "eyebrow": "比较层 • 决策系统",
        "title": "按适配度比较旅行方式，而不只看目的地。",
        "lead": "同一目的地会因旅行结构不同而产生不同结果。TourVsTravel 按限制、操作负担、支持、深度、可预测性和旅行者适配度进行比较。",
        "actions_label": "比较页操作",
        "primary_action": "探索17种方式",
        "secondary_action": "阅读方法论",
        "system_panel_label": "比较系统摘要",
        "criteria_kicker": "决策标准",
        "criteria_title": "系统衡量什么",
        "criteria_lead": "每个标准把模糊偏好转化为可发布的决策信号。",
        "low_label": "低",
        "high_label": "高",
        "pairs_kicker": "精选比较",
        "pairs_title": "从核心取舍开始",
        "pairs_lead": "有用的问题不只是去哪里，而是如何体验那里。",
        "signal_label": "信号",
        "explore_styles_label": "探索方式",
        "method_kicker": "比较方式",
        "method_title": "从偏好到适配的结构化路径",
        "method_lead": "比较层先理解旅行方式行为，再应用加权标准，并解释取舍。",
        "method_steps": [
            ("定义旅行结构", "每种方式都被视为一种操作模型。"),
            ("应用标准", "相同标准让比较保持一致。"),
            ("解释取舍", "结果说明为什么某种方式更适合特定限制。"),
        ],
        "final_kicker": "下一步",
        "final_title": "旅行方式是地图，比较是决策层。",
        "final_lead": "从参考索引开始，再用比较逻辑理解真实适配度。",
        "pair_summaries": {},
        "pair_signals": {},
    },
    "ja": {
        "eyebrow": "比較レイヤー • 意思決定システム",
        "title": "目的地だけでなく、適合性で旅行スタイルを比較する。",
        "lead": "同じ目的地でも旅行構造によって結果は変わります。TourVsTravel は制約、運用負担、支援、深度、予測可能性、旅行者適合で比較します。",
        "actions_label": "比較ページの操作",
        "primary_action": "17のスタイルを探索",
        "secondary_action": "方法論を読む",
        "system_panel_label": "比較システム概要",
        "criteria_kicker": "意思決定基準",
        "criteria_title": "システムが測るもの",
        "criteria_lead": "各基準は曖昧な好みを意思決定シグナルに変換します。",
        "low_label": "低",
        "high_label": "高",
        "pairs_kicker": "注目比較",
        "pairs_title": "中心的なトレードオフから始める",
        "pairs_lead": "重要なのはどこへ行くかだけでなく、どう体験するかです。",
        "signal_label": "シグナル",
        "explore_styles_label": "スタイルを探索",
        "method_kicker": "比較の仕組み",
        "method_title": "好みから適合へ向かう構造化された道筋",
        "method_lead": "比較レイヤーはスタイルの振る舞いを見て、重み付き基準を適用し、トレードオフを説明します。",
        "method_steps": [
            ("旅行構造を定義", "各スタイルを運用モデルとして扱います。"),
            ("基準を適用", "同じ基準で比較を一貫させます。"),
            ("トレードオフを説明", "特定の制約下でなぜ合うのかを示します。"),
        ],
        "final_kicker": "次のステップ",
        "final_title": "スタイルは地図、比較は意思決定レイヤーです。",
        "final_lead": "参照インデックスから始め、比較ロジックで実際の適合性を理解します。",
        "pair_summaries": {},
        "pair_signals": {},
    },
}

FEATURED_PAIR_IDS = (
    ("guided_group_tour", "independent_travel"),
    ("backpacking", "luxury_travel"),
    ("family_travel", "solo_travel"),
)


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CompareConfigError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise CompareConfigError(f"{label} must be a string.")
    text = value.strip()
    if not allow_empty and not text:
        raise CompareConfigError(f"{label} must not be empty.")
    return text


def _ensure_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise CompareConfigError(f"{label} must be a list.")
    return value


def _get_nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _translate(value: Any, lang: str, label: str) -> str:
    if isinstance(value, Mapping):
        if lang in value:
            return _ensure_string(value[lang], f"{label}.{lang}")
        if "en" in value:
            return _ensure_string(value["en"], f"{label}.en")
    return _ensure_string(value, label)


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
        raise CompareConfigError(f"site.base_url must be an absolute HTTPS URL: {base_url!r}")
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
    alternate = [str(value) for key, value in locale_map.items() if key != lang and isinstance(value, str)]
    return (str(current) if isinstance(current, str) else None), alternate


def _extract_site_name(site_config: Mapping[str, Any], lang: str) -> str:
    name = _get_nested(site_config, ("site", "name"), "TourVsTravel")
    if isinstance(name, Mapping):
        return _translate(name, lang, "site.name")
    return _ensure_string(name, "site.name")


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
        raise CompareConfigError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise CompareConfigError(f"{label} points outside static/: {path}") from exc
    if not asset_path.is_file():
        raise CompareConfigError(f"{label} points to a missing static asset: {path}")
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


def _normalize_criteria(criteria_payload: Mapping[str, Any], lang: str) -> List[Dict[str, Any]]:
    raw_criteria = _ensure_list(criteria_payload.get("criteria"), "comparison_criteria.criteria")
    normalized: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    for raw in raw_criteria:
        item = _ensure_mapping(raw, "comparison_criteria.criteria[]")
        if item.get("enabled", True) is not True:
            continue
        criterion_id = _ensure_string(item.get("id"), "criterion.id")
        if criterion_id in seen_ids:
            raise CompareConfigError(f"Duplicate criterion id: {criterion_id}")
        seen_ids.add(criterion_id)
        copy = _ensure_mapping(item.get("copy"), f"criterion.{criterion_id}.copy")
        order = item.get("order")
        weight = item.get("weight")
        if not isinstance(order, int) or isinstance(order, bool):
            raise CompareConfigError(f"criterion.{criterion_id}.order must be an integer.")
        if not isinstance(weight, int) or isinstance(weight, bool):
            raise CompareConfigError(f"criterion.{criterion_id}.weight must be an integer.")
        normalized.append(
            {
                "id": criterion_id,
                "order": order,
                "display_order": f"{order:02d}",
                "weight": weight,
                "title": _translate(copy.get("name"), lang, f"criterion.{criterion_id}.copy.name"),
                "description": _translate(copy.get("description"), lang, f"criterion.{criterion_id}.copy.description"),
                "low_meaning": _translate(copy.get("low_meaning"), lang, f"criterion.{criterion_id}.copy.low_meaning"),
                "high_meaning": _translate(copy.get("high_meaning"), lang, f"criterion.{criterion_id}.copy.high_meaning"),
            }
        )

    normalized.sort(key=lambda row: (row["order"], row["id"]))
    if not normalized:
        raise CompareConfigError("No enabled comparison criteria available.")
    return normalized


def _normalize_styles(experience_payload: Mapping[str, Any], lang: str) -> Dict[str, Dict[str, str]]:
    raw_styles = _ensure_list(experience_payload.get("active_experience_types"), "experience_types.active_experience_types")
    styles: Dict[str, Dict[str, str]] = {}

    for raw in raw_styles:
        item = _ensure_mapping(raw, "experience_types.active_experience_types[]")
        style_id = _ensure_string(item.get("id"), "experience_type.id")
        slug = _ensure_string(item.get("slug"), f"experience_type.{style_id}.slug")
        label = _translate(item.get("label"), lang, f"experience_type.{style_id}.label")
        summary = _translate(item.get("summary"), lang, f"experience_type.{style_id}.summary")
        styles[style_id] = {
            "id": style_id,
            "slug": slug,
            "title": label,
            "summary": summary,
            "href": f"/{lang}/styles/{slug}/",
        }

    if not styles:
        raise CompareConfigError("No active experience types available.")
    return styles


def _build_featured_pairs(styles_by_id: Mapping[str, Mapping[str, str]], lang: str) -> List[Dict[str, Any]]:
    copy = PAGE_COPY.get(lang, PAGE_COPY["en"])
    fallback_copy = PAGE_COPY["en"]
    pairs: List[Dict[str, Any]] = []

    for left_id, right_id in FEATURED_PAIR_IDS:
        if left_id not in styles_by_id or right_id not in styles_by_id:
            raise CompareConfigError(f"Featured pair references missing style: {left_id}, {right_id}")
        key = f"{left_id}:{right_id}"
        summary = copy.get("pair_summaries", {}).get(key) or fallback_copy["pair_summaries"][key]
        signal = copy.get("pair_signals", {}).get(key) or fallback_copy["pair_signals"][key]
        pairs.append(
            {
                "a": dict(styles_by_id[left_id]),
                "b": dict(styles_by_id[right_id]),
                "summary": summary,
                "signal": signal,
            }
        )
    return pairs


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise CompareConfigError(f"Missing templates directory: {TEMPLATES_DIR}")
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
        raise CompareWriteError(f"Unable to write compare page {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise CompareWriteError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise CompareWriteError(f"Refusing symlink output directory: {resolved}")
    if resolved.parent.exists() and resolved.parent.is_symlink():
        raise CompareWriteError(f"Refusing symlink parent for output directory: {resolved.parent}")
    return resolved


def _build_hreflang(base_url: str, languages: Sequence[str]) -> List[Dict[str, str]]:
    return [{"lang": lang, "url": f"{base_url}/{lang}/compare/"} for lang in languages]


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
    criteria: Sequence[Mapping[str, Any]],
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
                "about": [{"@type": "DefinedTerm", "name": criterion["title"]} for criterion in criteria],
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
    criteria_payload: Mapping[str, Any],
    experience_payload: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    base_url = _normalize_https_base_url(site_config)
    site_name = _extract_site_name(site_config, lang)
    copy = PAGE_COPY.get(lang, PAGE_COPY["en"])
    criteria = _normalize_criteria(criteria_payload, lang)
    styles_by_id = _normalize_styles(experience_payload, lang)
    featured_pairs = _build_featured_pairs(styles_by_id, lang)
    logo_url = _resolve_logo_path(site_config)
    favicon_url = logo_url
    canonical_url = f"{base_url}/{lang}/compare/"
    title = f"{copy['title']} | {site_name}"
    description = copy["lead"]
    scoring = _ensure_mapping(
        _get_nested(criteria_payload, ("defaults", "scoring_model"), {}),
        "comparison_criteria.defaults.scoring_model",
    )
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
        criteria=criteria,
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
        "copy": copy,
        "criteria": criteria,
        "featured_pairs": featured_pairs,
        "method_steps": [
            {"number": f"{idx:02d}", "title": title, "text": text}
            for idx, (title, text) in enumerate(copy["method_steps"], start=1)
        ],
        "system_cards": [
            {"label": "Styles", "value": str(len(styles_by_id))},
            {"label": "Criteria", "value": str(len(criteria))},
            {"label": "Scale", "value": f"{scoring.get('min', 1)}-{scoring.get('max', 5)}"},
        ],
        "canonical_url": canonical_url,
        "seo": seo_payload,
        "hreflang": seo_payload["hreflang"],
        "meta_desc": description,
        "robots_directive": seo_payload["robots_directive"],
        "body_class": "page-compare",
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
        "active_nav": "compare",
        "footer_note": "",
    }


def render_compare_page(
    *,
    site_config: Mapping[str, Any],
    criteria_payload: Mapping[str, Any],
    experience_payload: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise CompareRenderError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc

    context = _build_page_context(
        site_config=site_config,
        criteria_payload=criteria_payload,
        experience_payload=experience_payload,
        lang=lang,
        languages=languages,
    )

    try:
        return template.render(**context)
    except TemplateError as exc:
        raise CompareRenderError(f"Unable to render compare page [{lang}]: {exc}") from exc


def generate_compare_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    criteria_payload = load_comparison_criteria()
    experience_payload = load_experience_types()

    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise CompareConfigError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)

    rendered: List[tuple[Path, str, str]] = []
    for lang in languages:
        html_output = render_compare_page(
            site_config=site_config,
            criteria_payload=criteria_payload,
            experience_payload=experience_payload,
            lang=lang,
            languages=languages,
        )
        output_path = safe_output_dir / lang / "compare" / "index.html"
        rendered.append((output_path, html_output, lang))

    written: List[Path] = []
    for output_path, html_output, lang in rendered:
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated compare page [%s] -> %s", lang, output_path)

    log.info("Compare generation completed successfully. Files written: %d", len(written))
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate multilingual TourVsTravel compare pages.")
    parser.add_argument("--lang", type=str, default=None, help="Generate one language only.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory root.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        generate_compare_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateCompareError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected compare generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
