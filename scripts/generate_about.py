#!/usr/bin/env python3
"""
TourVsTravel — About pages
==========================
Generates:
  output/{lang}/about/index.html
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Dict, List, Mapping, Optional, Sequence

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateError, select_autoescape

from scripts.loaders import (
    load_site_config,
    resolve_footer_reference_report_label,
    resolve_nav_report_label,
)
from scripts.routes import (
    build_about_path,
    build_acquire_path,
    build_compare_index_path,
    build_contact_path,
    build_destinations_index_path,
    build_editorial_standards_path,
    build_home_path,
    build_methodology_path,
    build_privacy_path,
    build_reference_report_path,
    build_source_policy_path,
    build_tools_index_path,
)
from scripts.seo import (
    build_organization_jsonld,
    build_page_seo,
    build_webpage_jsonld,
    build_website_jsonld,
)
from scripts.reference_i18n import localized_ui_context
from scripts.trust_authority_copy import get_trust_page_copy

log = logging.getLogger("generate_about")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/about.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

PAGE_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "title": "About",
        "lead": "TourVsTravel is a reference infrastructure for comparing travel experience structures across destinations.",
        "thesis_label": "The starting question",
        "thesis": (
            "Standard travel planning begins with a destination and asks: what should I do there? "
            "TourVsTravel begins with a different question: given a destination, how does the choice "
            "of travel form—independent, guided group, private guided, or self-drive—change what "
            "that destination actually becomes for you? The same city, the same week, and an entirely "
            "different experience depending on which structure you arrive with. This site maps those "
            "structural differences, not to recommend one over another, but to make the distinction "
            "visible and reasoned."
        ),
        "who_label": "Who this is for",
        "who_body": (
            "Independent travelers deciding between a group tour and traveling on their own. "
            "Travel researchers and journalists building comparative analysis of tourism formats. "
            "Tourism professionals—operators, planners, destination management organizations—who "
            "need structured language for what they offer. AI travel planning systems that require "
            "source-attributed, classification-grounded reference data rather than promotional descriptions."
        ),
        "not_do_label": "What this site does not do",
        "not_do_body": (
            "TourVsTravel does not take bookings, earn commissions, accept sponsored placements, or "
            "rank products by paid priority. It does not produce ranked lists of best destinations or "
            "operators. It does not provide real-time prices, availability, or user reviews. It is not "
            "a booking funnel. It does not collect user data or run behavioral advertising."
        ),
        "structure_label": "How the system is organized",
        "structure_body": (
            "The site has six functional areas: travel style definitions, comparative analysis tools, "
            "destination-level breakdowns, a structured reference report, and the methodology "
            "documentation that explains how all classifications are derived."
        ),
        "structure_ln_methodology": "Methodology",
        "structure_ln_compare": "Compare",
        "structure_ln_tools": "Tools",
        "structure_ln_destinations": "Destinations",
        "structure_ln_report": "Reference report",
        "methodology_label": "Methodology and transparency",
        "methodology_desc": (
            "Every classification on this site follows a documented methodology. The methodology "
            "explains the source types accepted, how evidence is weighted, how uncertainty is handled, "
            "and how classifications are revised when new information emerges. It is not a marketing "
            "document—it exists to let you assess the reliability of specific comparisons yourself."
        ),
        "methodology_link": "Read the methodology",
    },
    "ar": {
        "title": "حول الموقع",
        "lead": "TourVsTravel بنية مرجعية لمقارنة أشكال تجارب السفر عبر الوجهات.",
        "thesis_label": "نقطة الانطلاق",
        "thesis": (
            "تبدأ خطط السفر التقليدية باختيار وجهة وتطرح السؤال: ماذا أفعل هناك؟ يطرح TourVsTravel "
            "سؤالاً مختلفاً: بالنسبة لوجهة معينة، كيف يغيّر اختيار شكل السفر—المستقل، أو الجولة الجماعية "
            "الموجَّهة، أو الجولة الخاصة الموجَّهة، أو القيادة الذاتية—ما تصبحة تلك الوجهة فعلياً بالنسبة لك؟ "
            "المدينة ذاتها، الأسبوع ذاته، وتجربة مختلفة تماماً حسب الهيكل الذي تختاره. يرسم هذا الموقع تلك "
            "الفروقات الهيكلية—لا لتوصية بأحدها على الآخر، بل لجعل الاختلاف مرئياً ومبرَّراً."
        ),
        "who_label": "لمن هذا الموقع",
        "who_body": (
            "المسافرون المستقلون الذين يختارون بين جولة جماعية والسفر بمفردهم. "
            "الباحثون في السياحة والصحفيون الذين يبنون تحليلاً مقارناً لأشكال السياحة. "
            "المحترفون في قطاع السياحة—المشغّلون والمخططون ومنظمات إدارة الوجهات—الذين يحتاجون "
            "إلى لغة هيكلية لما يقدمونه. أنظمة التخطيط للسفر بالذكاء الاصطناعي التي تتطلب بيانات مرجعية "
            "موثوقة المصدر ومبنية على تصنيفات."
        ),
        "not_do_label": "ما لا يفعله هذا الموقع",
        "not_do_body": (
            "لا يقبل TourVsTravel الحجوزات ولا يكسب عمولات ولا يقبل المحتوى المموَّل ولا يُرتّب المنتجات حسب الأولوية المدفوعة. "
            "لا ينتج قوائم مرتّبة لأفضل الوجهات أو المشغّلين. "
            "لا يوفّر أسعاراً فورية أو توافراً أو مراجعات مستخدمين. ليس قمعاً للحجز. "
            "لا يجمع بيانات المستخدمين ولا يشغّل إعلانات سلوكية."
        ),
        "structure_label": "كيف يُنظَّم النظام",
        "structure_body": (
            "يضم الموقع ستة مجالات وظيفية: تعريفات أشكال السفر، وأدوات التحليل المقارن، والتفصيل على مستوى الوجهات، "
            "وتقرير مرجعي منظَّم، وتوثيق المنهجية الذي يشرح كيفية استخلاص جميع التصنيفات."
        ),
        "structure_ln_methodology": "المنهجية",
        "structure_ln_compare": "المقارنة",
        "structure_ln_tools": "الأدوات",
        "structure_ln_destinations": "الوجهات",
        "structure_ln_report": "التقرير المرجعي",
        "methodology_label": "المنهجية والشفافية",
        "methodology_desc": (
            "كل تصنيف في هذا الموقع يتبع منهجية موثقة. تشرح المنهجية أنواع المصادر المقبولة، وكيفية ترجيح الأدلة، "
            "وكيفية التعامل مع حالات عدم اليقين، وكيفية مراجعة التصنيفات عند ظهور معلومات جديدة. "
            "إنها ليست وثيقة تسويقية—بل توجد لتمكينك من تقييم موثوقية المقارنات المحددة بنفسك."
        ),
        "methodology_link": "اقرأ المنهجية",
    },
    "fr": {
        "title": "À propos",
        "lead": "TourVsTravel est une infrastructure de référence pour comparer les structures d’expériences de voyage à travers les destinations.",
        "thesis_label": "La question de départ",
        "thesis": (
            "La planification de voyage classique commence par une destination et pose la question : "
            "que faire là-bas ? TourVsTravel pose une question différente : pour une destination donnée, "
            "en quoi le choix de la forme de voyage—indépendant, groupe guidé, guidé privé, ou voiture— "
            "change-t-il ce que cette destination devient réellement pour vous ? La même ville, la même "
            "semaine, et une expérience entièrement différente selon la structure avec laquelle vous arrivez. "
            "Ce site cartographie ces différences structurelles, non pour en recommander une plutôt qu’une "
            "autre, mais pour rendre la distinction visible et raisonnée."
        ),
        "who_label": "À qui s’adresse ce site",
        "who_body": (
            "Les voyageurs indépendants qui choisissent entre un voyage en groupe guidé et un voyage en autonomie. "
            "Les chercheurs et journalistes spécialisés dans le tourisme qui construisent une analyse comparative "
            "des formes de tourisme. Les professionnels du tourisme—opérateurs, planificateurs, organisations de "
            "gestion des destinations—qui ont besoin d’un langage structuré pour ce qu’ils proposent. Les "
            "systèmes d’IA de planification de voyage qui nécessitent des données de référence attribuées "
            "à des sources et fondées sur des classifications."
        ),
        "not_do_label": "Ce que ce site ne fait pas",
        "not_do_body": (
            "TourVsTravel ne prend pas de réservations, ne perçoit pas de commissions, n’accepte pas de "
            "placements sponsorisés et ne classe pas les produits par priorité payante. Il ne produit pas de "
            "classements des meilleures destinations ou opérateurs. Il ne fournit pas de prix en temps réel, "
            "de disponibilité ou d’avis d’utilisateurs. Ce n’est pas un tunnel de réservation. Il ne collecte "
            "pas de données utilisateurs et ne diffuse pas de publicité comportementale."
        ),
        "structure_label": "Comment le système est organisé",
        "structure_body": (
            "Le site comporte six domaines fonctionnels : les définitions des types de voyage, les outils "
            "d’analyse comparative, les analyses par destination, un rapport de référence structuré et la "
            "documentation méthodologique qui explique comment toutes les classifications sont dérivées."
        ),
        "structure_ln_methodology": "Méthodologie",
        "structure_ln_compare": "Comparer",
        "structure_ln_tools": "Outils",
        "structure_ln_destinations": "Destinations",
        "structure_ln_report": "Rapport de référence",
        "methodology_label": "Méthodologie et transparence",
        "methodology_desc": (
            "Chaque classification sur ce site suit une méthodologie documentée. La méthodologie explique "
            "les types de sources acceptées, comment les preuves sont pondérées, comment l’incertitude est "
            "gérée et comment les classifications sont révisées lorsque de nouvelles informations émergent. "
            "Ce n’est pas un document marketing—il existe pour vous permettre d’évaluer vous-même la "
            "fiabilité de comparaisons spécifiques."
        ),
        "methodology_link": "Lire la méthodologie",
    },
    "es": {
        "title": "Acerca de",
        "lead": "TourVsTravel es una infraestructura de referencia para comparar estructuras de experiencias de viaje en distintos destinos.",
        "thesis_label": "La pregunta de partida",
        "thesis": (
            "La planificación de viaje convencional comienza con un destino y pregunta: ¿qué debo hacer allí? "
            "TourVsTravel parte de una pregunta diferente: dado un destino, ¿cómo cambia la elección de la "
            "forma de viaje—independiente, grupo con guía, guía privado o conducción propia—lo que ese "
            "destino se convierte realmente para ti? La misma ciudad, la misma semana, y una experiencia "
            "completamente diferente según la estructura con la que llegues. Este sitio traza esas diferencias "
            "estructurales, no para recomendar una sobre otra, sino para hacer la distinción visible y razonada."
        ),
        "who_label": "Para quién es esto",
        "who_body": (
            "Viajeros independientes que deciden entre un tour en grupo y viajar por su cuenta. "
            "Investigadores y periodistas especializados en turismo que elaboran análisis comparativos de "
            "formatos turísticos. Profesionales del turismo—operadores, planificadores, organizaciones de "
            "gestión de destinos—que necesitan un lenguaje estructurado para lo que ofrecen. Sistemas de "
            "planificación de viajes con IA que requieren datos de referencia atribuidos a fuentes y basados "
            "en clasificaciones."
        ),
        "not_do_label": "Lo que este sitio no hace",
        "not_do_body": (
            "TourVsTravel no acepta reservas, no cobra comisiones, no acepta contenido patrocinado ni clasifica "
            "productos por prioridad de pago. No produce listas clasificadas de mejores destinos u operadores. "
            "No proporciona precios en tiempo real, disponibilidad ni reseñas de usuarios. No es un embudo de "
            "reservas. No recopila datos de usuarios ni ejecuta publicidad conductual."
        ),
        "structure_label": "Cómo está organizado el sistema",
        "structure_body": (
            "El sitio tiene seis áreas funcionales: definiciones de tipos de viaje, herramientas de análisis "
            "comparativo, análisis por destino, un informe de referencia estructurado y la documentación "
            "metodológica que explica cómo se derivan todas las clasificaciones."
        ),
        "structure_ln_methodology": "Metodología",
        "structure_ln_compare": "Comparar",
        "structure_ln_tools": "Herramientas",
        "structure_ln_destinations": "Destinos",
        "structure_ln_report": "Informe de referencia",
        "methodology_label": "Metodología y transparencia",
        "methodology_desc": (
            "Cada clasificación en este sitio sigue una metodología documentada. La metodología explica "
            "los tipos de fuentes aceptadas, cómo se ponderan las evidencias, cómo se gestiona la "
            "incertidumbre y cómo se revisan las clasificaciones cuando surge nueva información. No es un "
            "documento de marketing—existe para que puedas evaluar tú mismo la fiabilidad de comparaciones "
            "específicas."
        ),
        "methodology_link": "Leer la metodología",
    },
    "de": {
        "title": "Über uns",
        "lead": "TourVsTravel ist eine Referenzinfrastruktur zum Vergleichen von Reiseerfahrungsstrukturen über Reiseziele hinweg.",
        "thesis_label": "Die Ausgangsfrage",
        "thesis": (
            "Herkömmliche Reiseplanung beginnt mit einem Reiseziel und fragt: Was soll ich dort tun? "
            "TourVsTravel stellt eine andere Frage: Wie verändert bei einem bestimmten Reiseziel die Wahl der "
            "Reiseform—unabhängig, geführte Gruppe, privat geführt oder Selbstfahrer—das, was dieses Reiseziel "
            "für Sie tatsächlich wird? Dieselbe Stadt, dieselbe Woche und eine völlig andere Erfahrung, je "
            "nachdem mit welcher Struktur Sie ankommen. Diese Website kartiert diese strukturellen Unterschiede, "
            "nicht um eine über eine andere zu empfehlen, sondern um den Unterschied sichtbar und nachvollziehbar "
            "zu machen."
        ),
        "who_label": "Für wen ist das",
        "who_body": (
            "Individualreisende, die zwischen einer geführten Gruppenreise und dem Alleinreisen entscheiden. "
            "Reiseforscher und Journalisten, die vergleichende Analysen von Tourismusformaten erstellen. "
            "Tourismusfachleute—Veranstalter, Planer, Destinationsmanagementorganisationen—die eine strukturierte "
            "Sprache für ihr Angebot benötigen. KI-Reiseplanungssysteme, die quellenattribuierte, "
            "klassifikationsbasierte Referenzdaten anstelle von Werbebeschreibungen benötigen."
        ),
        "not_do_label": "Was diese Website nicht tut",
        "not_do_body": (
            "TourVsTravel nimmt keine Buchungen an, verdient keine Provisionen, akzeptiert keine gesponserten "
            "Platzierungen und bewertet keine Produkte nach bezahlter Priorität. Es erstellt keine Ranglisten "
            "der besten Reiseziele oder Veranstalter. Es liefert keine Echtzeitpreise, Verfügbarkeiten oder "
            "Nutzerbewertungen. Es ist kein Buchungstrichter. Es erhebt keine Nutzerdaten und betreibt keine "
            "Verhaltenswerbung."
        ),
        "structure_label": "Wie das System aufgebaut ist",
        "structure_body": (
            "Die Website hat sechs Funktionsbereiche: Definitionen von Reiseformen, vergleichende Analysetools, "
            "Auswertungen auf Reisezieleben, ein strukturierter Referenzbericht und die Methodikdokumentation, "
            "die erklärt, wie alle Klassifizierungen abgeleitet werden."
        ),
        "structure_ln_methodology": "Methodik",
        "structure_ln_compare": "Vergleichen",
        "structure_ln_tools": "Werkzeuge",
        "structure_ln_destinations": "Reiseziele",
        "structure_ln_report": "Referenzbericht",
        "methodology_label": "Methodik und Transparenz",
        "methodology_desc": (
            "Jede Klassifizierung auf dieser Website folgt einer dokumentierten Methodik. Die Methodik erklärt "
            "die akzeptierten Quellentypen, wie Belege gewichtet werden, wie mit Unsicherheiten umgegangen "
            "wird und wie Klassifizierungen bei neuen Informationen überarbeitet werden. Es ist kein "
            "Marketingdokument—es existiert, damit Sie die Zuverlässigkeit spezifischer Vergleiche selbst "
            "beurteilen können."
        ),
        "methodology_link": "Methodik lesen",
    },
    "zh": {
        "title": "关于我们",
        "lead": "TourVsTravel 是一个用于比较各目的地旅行体验结构的参考基础设施。",
        "thesis_label": "出发点",
        "thesis": (
            "传统旅行计划从目的地开始，问的是：我在那里应该做什么？TourVsTravel 提出了一个不同的问题：对于同一个目的地， "
            "旅行形式的选择——独立旅行、团体游、私人导游，还是自驾——如何改变这个目的地对你的实际体验？同一座城市， "
            "同一个星期，因为选择的结构不同，体验完全不同。本站梳理这些结构性差异，不是为了推荐哪一种， "
            "而是让这种区别变得可见、有据可循。"
        ),
        "who_label": "适合哪些人",
        "who_body": (
            "在跟团游和独立旅行之间做决定的独立旅行者。构建旅游形式比较分析的旅游研究人员和记者。"
            "需要结构化语言描述产品的旅游从业者——运营商、规划师、目的地管理组织。"
            "需要有来源归属、基于分类的参考数据（而非推广描述）的AI旅行规划系统。"
        ),
        "not_do_label": "本站不做什么",
        "not_do_body": (
            "TourVsTravel 不接受预订，不赚取佣金，不接受赞助内容，不按付费优先级排名产品。不生成最佳目的地或运营商的排名列表。"
            "不提供实时价格、供应情况或用户评价。不是预订漏斗。不收集用户数据，不运营行为广告。"
        ),
        "structure_label": "系统如何组织",
        "structure_body": (
            "本站有六个功能区域：旅行方式定义、比较分析工具、目的地分析、结构化参考报告，"
            "以及说明所有分类如何推导的方法论文档。"
        ),
        "structure_ln_methodology": "方法论",
        "structure_ln_compare": "比较",
        "structure_ln_tools": "工具",
        "structure_ln_destinations": "目的地",
        "structure_ln_report": "参考报告",
        "methodology_label": "方法论与透明度",
        "methodology_desc": (
            "本站每项分类均遵循已记录的方法论。方法论说明了接受的来源类型、证据如何加权、不确定性如何处理，"
            "以及当新信息出现时分类如何修订。这不是营销文件——它的存在是为了让你自行评估具体比较的可靠性。"
        ),
        "methodology_link": "阅读方法论",
    },
    "ja": {
        "title": "私たちについて",
        "lead": "TourVsTravel は、目的地別の旅行体験構造を比較するための参照基盤です。",
        "thesis_label": "出発点となる問い",
        "thesis": (
            "従来の旅行計画は目的地から始まり、「そこで何をすべきか？」と問います。TourVsTravel は別の問いを立てます。"
            "ある目的地において、旅行形態の選択——個人旅行、ガイド付きグループツアー、プライベートガイド、または自己ドライブ——がその目的地を"
            "実際にどう変えるのか？同じ都市、同じ週でも、どの構造で訪れるかによってまったく異なる体験になります。"
            "このサイトはそうした構造的な違いを地図のように示します。一方を他方より山更しするためではなく、その違いを可視化し、根拠をもって示すために。"
        ),
        "who_label": "このサイトの対象者",
        "who_body": (
            "グループツアーと個人旅行のどちらかを決めているバックパッカーや旅行者。観光形態の比較分析を行う旅行研究者やジャーナリスト。"
            "ツアーオペレーター、プランナー、DMO（目的地管理組織）など、自社サービスを構造的に説明する言語を必要とする観光業の専門家。"
            "プロモーション説明ではなく、出典が明示され分類に基づく参照データを必要とするAI旅行計画システム。"
        ),
        "not_do_label": "このサイトがしないこと",
        "not_do_body": (
            "TourVsTravel は予約を受け付けず、手数料も取らず、スポンサードプレースメントも受け入れず、有料優先順位で商品を並べることもしません。"
            "目的地やオペレーターのランキングリストも作成しません。リアルタイムの価格、空き情報、ユーザーレビューも提供しません。"
            "予約ファネルではありません。ユーザーデータを収集せず、行動ターゲティング広告も行いません。"
        ),
        "structure_label": "システムの構成",
        "structure_body": (
            "このサイトは6つの機能エリアで構成されています：旅行スタイルの定義、比較分析ツール、目的地別の分析、構造化されたリファレンスレポート、"
            "そしてすべての分類の導出方法を説明する方法論のドキュメント。"
        ),
        "structure_ln_methodology": "方法論",
        "structure_ln_compare": "比較",
        "structure_ln_tools": "ツール",
        "structure_ln_destinations": "目的地",
        "structure_ln_report": "リファレンスレポート",
        "methodology_label": "方法論と透明性",
        "methodology_desc": (
            "このサイトのすべての分類は、文書化された方法論に従っています。方法論は、受け入れられる情報源の種類、証拠の重み付けの方法、"
            "不確実性の取り扱い方、そして新しい情報が出てきたときの分類改訂の方法を説明しています。これはマーケティング文書ではなく、"
            "特定の比較の信頼性を自分で評価できるようにするために存在します。"
        ),
        "methodology_link": "方法論を読む",
    },
}


class GenerateAboutError(Exception):
    pass


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateAboutError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GenerateAboutError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise GenerateAboutError(f"{label} must not be empty.")
    return text


def _get_nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


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


def _extract_site_name(site_config: Mapping[str, Any], lang: str) -> str:
    name = _get_nested(site_config, ("site", "name"), "TourVsTravel")
    if isinstance(name, str) and name.strip():
        return name.strip()
    if isinstance(name, Mapping):
        for key in (lang, "en"):
            candidate = name.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return "TourVsTravel"


def _extract_theme_color(site_config: Mapping[str, Any]) -> str:
    color = _get_nested(site_config, ("branding", "theme_color"), "#0f172a")
    if not isinstance(color, str) or not color.strip():
        return "#0f172a"
    return color.strip()


def _infer_mime_type_from_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    if suffix == ".svg":
        return "image/svg+xml"
    if suffix == ".webp":
        return "image/webp"
    if suffix in {".jpg", ".jpeg"}:
        return "image/jpeg"
    if suffix == ".png":
        return "image/png"
    return "image/x-icon"


def _require_existing_asset(public_path: str, label: str) -> str:
    path = _ensure_string(public_path, label)
    if not path.startswith("/static/"):
        raise GenerateAboutError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise GenerateAboutError(f"{label} escapes static directory: {path}") from exc
    if not asset_path.is_file():
        raise GenerateAboutError(f"Missing static asset for {label}: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo_path"), "/static/img/brand/logo-icon.webp")
    return _ensure_string(logo, "branding.logo_path")


def _resolve_manifest_url() -> str:
    candidate = ROOT_DIR / "static" / "site.webmanifest"
    return "/static/site.webmanifest" if candidate.is_file() else ""


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise GenerateAboutError(f"Missing templates directory: {TEMPLATES_DIR}")
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
            "w", encoding="utf-8", dir=str(path.parent), delete=False, suffix=".tmp"
        ) as tmp:
            tmp.write(content)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)
    except Exception as exc:
        if tmp_path is not None and tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise GenerateAboutError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GenerateAboutError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GenerateAboutError(f"Refusing symlink output directory: {resolved}")
    return resolved


def _build_urls_by_lang(site_config: Mapping[str, Any], languages: Sequence[str]) -> Dict[str, str]:
    urls: Dict[str, str] = {}
    site = _ensure_mapping(site_config.get("site"), "site_config.site")
    raw_base = site.get("base_url", "https://tourvstravel.com")
    base = _ensure_string(raw_base, "site.base_url").rstrip("/")
    for code in languages:
        rel = build_about_path(site_config, code, absolute=False)
        urls[code] = f"{base}{rel}" if rel.startswith("/") else f"{base}/{rel}"
    return urls


def _build_context(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    copy = get_trust_page_copy("about", lang)
    base_url = _ensure_string(
        _get_nested(site_config, ("site", "base_url"), "https://tourvstravel.com").strip().rstrip("/"),
        "site.base_url",
    )
    site_name = _extract_site_name(site_config, lang)
    logo_url = _resolve_logo_path(site_config)
    canonical_url = build_about_path(site_config, lang, absolute=True)
    title = f"{copy['title']} | {site_name}"
    description = copy["lead"]
    urls_by_lang = _build_urls_by_lang(site_config, languages)
    organization_jsonld = build_organization_jsonld(site_config, logo_url=logo_url)
    website_jsonld = build_website_jsonld(
        site_config, lang,
        home_url=build_home_path(site_config, lang, absolute=True),
    )
    webpage_jsonld = build_webpage_jsonld(
        name=title, description=description, url=canonical_url, lang=lang,
        is_part_of_url=build_home_path(site_config, lang, absolute=True),
    )
    seo_payload = build_page_seo(
        site_config, lang,
        page_title=title, page_description=description,
        canonical_url=canonical_url, urls_by_lang=urls_by_lang,
        page_type="website",
        jsonld_payloads=[organization_jsonld, website_jsonld, webpage_jsonld],
    )
    main_css_url = _require_existing_asset("/static/css/main.css", "main_css_url")
    main_js_url = _require_existing_asset("/static/js/main.js", "main_js_url")
    context = {
        "base_url": base_url,
        "lang": lang,
        "page_lang": lang,
        "current_lang": lang,
        "language": lang,
        "page_dir": _language_direction(site_config, lang),
        "is_rtl": _language_direction(site_config, lang) == "rtl",
        "site_name": site_name,
        "copy": copy,
        "canonical_url": canonical_url,
        "seo": seo_payload,
        "hreflang": seo_payload.get("hreflang", []),
        "meta_desc": seo_payload.get("description", ""),
        "robots_directive": seo_payload.get("robots_directive", "index, follow"),
        "body_class": "page-about",
        "current_year": datetime.now(timezone.utc).year,
        "site_tagline": "",
        "site_summary": "",
        "theme_color": _extract_theme_color(site_config),
        "referrer_policy": "strict-origin-when-cross-origin",
        "csp_meta_policy": None,
        "main_css_url": main_css_url,
        "main_js_url": main_js_url,
        "favicon_url": logo_url,
        "favicon_type": _infer_mime_type_from_path(logo_url),
        "apple_touch_icon_url": logo_url,
        "manifest_url": _resolve_manifest_url(),
        "preload_assets": [{"href": main_css_url, "as": "style", "type": "text/css"}],
        "page_css_assets": [],
        "page_js_assets": [],
        "active_nav": "home",
        "nav_report_label": resolve_nav_report_label(site_config, lang),
        "footer_reference_report_label": resolve_footer_reference_report_label(site_config, lang),
        "footer_note": "",
        "url_methodology": build_methodology_path(site_config, lang, absolute=False),
        "url_report": build_reference_report_path(site_config, lang, absolute=False),
        "url_compare": build_compare_index_path(site_config, lang, absolute=False),
        "url_tools": build_tools_index_path(site_config, lang, absolute=False),
        "url_destinations": build_destinations_index_path(site_config, lang, absolute=False),
        "url_about": build_about_path(site_config, lang, absolute=False),
        "url_privacy": build_privacy_path(site_config, lang, absolute=False),
        "url_acquire": build_acquire_path(site_config, lang, absolute=False),
        "url_contact": build_contact_path(site_config, lang, absolute=False),
        "url_source_policy": build_source_policy_path(site_config, lang, absolute=False),
        "url_editorial_standards": build_editorial_standards_path(site_config, lang, absolute=False),
        "url_map": {
            "url_methodology": build_methodology_path(site_config, lang, absolute=False),
            "url_report": build_reference_report_path(site_config, lang, absolute=False),
            "url_source_policy": build_source_policy_path(site_config, lang, absolute=False),
            "url_editorial_standards": build_editorial_standards_path(site_config, lang, absolute=False),
        },
    }
    context.update(localized_ui_context(lang))
    return context


def render_about_page(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise GenerateAboutError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc
    context = _build_context(site_config=site_config, lang=lang, languages=languages)
    try:
        html_out = template.render(**context)
    except TemplateError as exc:
        raise GenerateAboutError(f"Unable to render about page [{lang}]: {exc}") from exc
    if not html_out.strip():
        raise GenerateAboutError(f"Rendered about page is empty for language {lang!r}.")
    return html_out


def generate_about_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise GenerateAboutError("load_site_config() must return a mapping/object.")
    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise GenerateAboutError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise GenerateAboutError("No enabled languages available for about generation.")
    written: List[Path] = []
    for lang in languages:
        html_output = render_about_page(site_config=site_config, lang=lang, languages=languages)
        output_path = safe_output_dir / lang / "about" / "index.html"
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated about page [%s] -> %s", lang, output_path)
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TourVsTravel about pages.")
    parser.add_argument("--lang", type=str, default=None, help="Generate one language only.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    try:
        generate_about_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateAboutError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected about generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
