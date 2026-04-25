#!/usr/bin/env python3
"""
TourVsTravel — Destinations Hub Generator
=========================================

Generate multilingual destination interpretation hub pages:

    /{lang}/destinations/

This is not a generic destination directory. It explains that the same place
changes meaning depending on the travel style used to experience it.
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
log = logging.getLogger("generate_destinations")


ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT_DIR / "static"
TEMPLATES_DIR = ROOT_DIR / "templates"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/destinations.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")


class GenerateDestinationsError(Exception):
    """Raised when destination hub generation fails."""


class DestinationsConfigError(GenerateDestinationsError):
    """Raised when destination hub configuration is invalid."""


class DestinationsRenderError(GenerateDestinationsError):
    """Raised when destination hub rendering fails."""


class DestinationsWriteError(GenerateDestinationsError):
    """Raised when destination hub writing fails."""


PAGE_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "eyebrow": "Destination Interpretation · Travel Style Context · Decision Layer",
        "title": "The Same Place Is Not the Same Trip",
        "lead": "TourVsTravel treats destinations as interpreted environments, not static points on a map. The same city, coast, region, or route changes depending on whether it is entered through a guided tour, independent travel, family travel, luxury travel, slow travel, or backpacking.",
        "actions_label": "Destination hub actions",
        "primary_action": "Find Your Match",
        "secondary_action": "Explore Travel Styles",
        "compare_action": "Compare Travel Forms",
        "panel_label": "Destination interpretation signals",
        "panel_card_1_label": "Core thesis",
        "panel_card_1_value": "A destination changes with the travel form used to experience it.",
        "panel_card_2_label": "Connected styles",
        "panel_card_2_value": "travel styles currently shape interpretation.",
        "panel_card_3_label": "Output",
        "panel_card_3_value": "Destination meaning becomes legible before commitment.",
        "thesis_kicker": "Reference thesis",
        "thesis_title": "Destination is not only where you go",
        "thesis_lead": "A destination is a system of access, rhythm, cost, friction, support, exposure, and depth. A traveler does not simply arrive at a place; they arrive through a structure.",
        "lenses_kicker": "Interpretation lenses",
        "lenses_title": "How a destination changes",
        "lenses_lead": "Before building individual destination pages, TourVsTravel defines the lenses that make destination interpretation systematic rather than promotional.",
        "styles_kicker": "Travel-style effect",
        "styles_title": "The travel form changes the destination",
        "styles_lead": "These style lenses show why the same place cannot be evaluated without considering how it is traveled.",
        "open_style_label": "Open style reference ->",
        "method_kicker": "Method",
        "method_title": "A destination hub without false coverage",
        "method_lead": "This hub establishes the logic before scaling into individual destination pages. It avoids fake coverage, thin destination lists, and generic tourism language.",
        "final_kicker": "Next step",
        "final_title": "Choose the travel form before judging the place",
        "final_lead": "A destination only becomes meaningful when it is interpreted through constraints, autonomy, support, burden, depth, and predictability.",
    },
    "ar": {
        "eyebrow": "تفسير الوجهات · سياق نمط السفر · طبقة قرار",
        "title": "نفس المكان ليس نفس الرحلة",
        "lead": "يتعامل TourVsTravel مع الوجهات كبيئات تُفسَّر حسب نمط السفر، لا كنقاط ثابتة على الخريطة. فالمدينة أو الساحل أو المنطقة نفسها تتغير عندما تُعاش عبر جولة منظمة أو سفر مستقل أو سفر عائلي أو سفر فاخر أو سفر بطيء أو backpacking.",
        "actions_label": "إجراءات محور الوجهات",
        "primary_action": "اعرف الأنسب لك",
        "secondary_action": "استكشف أنماط السفر",
        "compare_action": "قارن أشكال السفر",
        "panel_label": "إشارات تفسير الوجهات",
        "panel_card_1_label": "الأطروحة الأساسية",
        "panel_card_1_value": "الوجهة تتغير حسب شكل السفر الذي تدخل من خلاله.",
        "panel_card_2_label": "الأنماط المرتبطة",
        "panel_card_2_value": "نمط سفر يشكل التفسير حاليًا.",
        "panel_card_3_label": "المخرج",
        "panel_card_3_value": "تصبح دلالة الوجهة أوضح قبل الالتزام.",
        "thesis_kicker": "أطروحة مرجعية",
        "thesis_title": "الوجهة ليست فقط المكان الذي تذهب إليه",
        "thesis_lead": "الوجهة هي نظام من الوصول، الإيقاع، التكلفة، الاحتكاك، الدعم، الانكشاف، وعمق التجربة. المسافر لا يصل فقط إلى مكان؛ بل يصل من خلال بنية.",
        "lenses_kicker": "عدسات التفسير",
        "lenses_title": "كيف تتغير الوجهة",
        "lenses_lead": "قبل بناء صفحات وجهات فردية، يحدد TourVsTravel العدسات التي تجعل تفسير الوجهات منهجيًا لا ترويجيًا.",
        "styles_kicker": "أثر نمط السفر",
        "styles_title": "شكل السفر يغير الوجهة",
        "styles_lead": "هذه العدسات توضح لماذا لا يمكن تقييم المكان دون فهم طريقة السفر إليه وداخله.",
        "open_style_label": "افتح الصفحة المرجعية <-",
        "method_kicker": "المنهج",
        "method_title": "محور وجهات بدون تغطية وهمية",
        "method_lead": "هذا المحور يثبت المنطق قبل التوسع إلى صفحات وجهات فردية، ويتجنب القوائم الضعيفة واللغة السياحية العامة.",
        "final_kicker": "الخطوة التالية",
        "final_title": "اختر شكل السفر قبل الحكم على المكان",
        "final_lead": "تصبح الوجهة ذات معنى عندما تُفهم عبر القيود، الاستقلالية، الدعم، العبء، العمق، وقابلية التوقع.",
    },
    "fr": {
        "eyebrow": "Interprétation des destinations · contexte de style · couche de décision",
        "title": "Le même lieu n’est pas le même voyage",
        "lead": "TourVsTravel traite les destinations comme des environnements interprétés par le style de voyage, pas comme de simples points sur une carte.",
        "actions_label": "Actions du hub destinations",
        "primary_action": "Trouver mon style",
        "secondary_action": "Explorer les styles",
        "compare_action": "Comparer les formes de voyage",
        "panel_label": "Signaux d’interprétation",
        "panel_card_1_label": "Thèse centrale",
        "panel_card_1_value": "Une destination change selon la forme de voyage utilisée.",
        "panel_card_2_label": "Styles connectés",
        "panel_card_2_value": "styles structurent l’interprétation.",
        "panel_card_3_label": "Résultat",
        "panel_card_3_value": "Le sens de la destination devient lisible avant l’engagement.",
        "thesis_kicker": "Thèse de référence",
        "thesis_title": "Une destination n’est pas seulement un lieu",
        "thesis_lead": "Une destination est un système d’accès, de rythme, de coût, de friction, de soutien, d’exposition et de profondeur.",
        "lenses_kicker": "Lentilles d’interprétation",
        "lenses_title": "Comment une destination change",
        "lenses_lead": "Avant de créer des pages de destinations individuelles, TourVsTravel définit les lentilles qui rendent l’interprétation systématique.",
        "styles_kicker": "Effet du style",
        "styles_title": "La forme du voyage change la destination",
        "styles_lead": "Ces lentilles montrent pourquoi un lieu ne peut pas être évalué sans comprendre la forme du voyage.",
        "open_style_label": "Ouvrir la référence ->",
        "method_kicker": "Méthode",
        "method_title": "Un hub destinations sans fausse couverture",
        "method_lead": "Ce hub établit la logique avant d’étendre le système vers des pages individuelles.",
        "final_kicker": "Étape suivante",
        "final_title": "Choisir la forme avant de juger le lieu",
        "final_lead": "Une destination devient intelligible par les contraintes, l’autonomie, le soutien, la charge, la profondeur et la prévisibilité.",
    },
    "es": {
        "eyebrow": "Interpretación de destinos · contexto de estilo · capa de decisión",
        "title": "El mismo lugar no es el mismo viaje",
        "lead": "TourVsTravel trata los destinos como entornos interpretados por el estilo de viaje, no como puntos estáticos.",
        "actions_label": "Acciones del hub de destinos",
        "primary_action": "Encuentra tu ajuste",
        "secondary_action": "Explorar estilos",
        "compare_action": "Comparar formas de viajar",
        "panel_label": "Señales de interpretación",
        "panel_card_1_label": "Tesis central",
        "panel_card_1_value": "Un destino cambia según la forma de viaje.",
        "panel_card_2_label": "Estilos conectados",
        "panel_card_2_value": "estilos dan forma a la interpretación.",
        "panel_card_3_label": "Resultado",
        "panel_card_3_value": "El significado del destino se vuelve legible antes del compromiso.",
        "thesis_kicker": "Tesis de referencia",
        "thesis_title": "Un destino no es solo dónde vas",
        "thesis_lead": "Un destino es un sistema de acceso, ritmo, coste, fricción, apoyo, exposición y profundidad.",
        "lenses_kicker": "Lentes de interpretación",
        "lenses_title": "Cómo cambia un destino",
        "lenses_lead": "Antes de crear páginas individuales, TourVsTravel define lentes que hacen la interpretación sistemática.",
        "styles_kicker": "Efecto del estilo",
        "styles_title": "La forma de viajar cambia el destino",
        "styles_lead": "Estas lentes muestran por qué un lugar no se puede evaluar sin considerar cómo se viaja.",
        "open_style_label": "Abrir referencia ->",
        "method_kicker": "Método",
        "method_title": "Un hub sin cobertura falsa",
        "method_lead": "Este hub establece la lógica antes de escalar a páginas individuales de destinos.",
        "final_kicker": "Siguiente paso",
        "final_title": "Elige la forma antes de juzgar el lugar",
        "final_lead": "Un destino se vuelve significativo mediante restricciones, autonomía, apoyo, carga, profundidad y previsibilidad.",
    },
    "de": {
        "eyebrow": "Destinationsdeutung · Reisestil-Kontext · Entscheidungsebene",
        "title": "Derselbe Ort ist nicht dieselbe Reise",
        "lead": "TourVsTravel behandelt Destinationen als durch Reisestile interpretierte Umgebungen, nicht als statische Kartenpunkte.",
        "actions_label": "Aktionen des Destinations-Hubs",
        "primary_action": "Passenden Stil finden",
        "secondary_action": "Reisestile erkunden",
        "compare_action": "Reiseformen vergleichen",
        "panel_label": "Interpretationssignale",
        "panel_card_1_label": "Kernthese",
        "panel_card_1_value": "Eine Destination verändert sich mit der Reiseform.",
        "panel_card_2_label": "Verbundene Stile",
        "panel_card_2_value": "Reisestile strukturieren die Interpretation.",
        "panel_card_3_label": "Ausgabe",
        "panel_card_3_value": "Bedeutung wird vor der Entscheidung lesbar.",
        "thesis_kicker": "Referenzthese",
        "thesis_title": "Eine Destination ist nicht nur ein Ort",
        "thesis_lead": "Eine Destination ist ein System aus Zugang, Rhythmus, Kosten, Reibung, Unterstützung, Exposition und Tiefe.",
        "lenses_kicker": "Interpretationslinsen",
        "lenses_title": "Wie eine Destination sich verändert",
        "lenses_lead": "Vor einzelnen Destinationsseiten definiert TourVsTravel die Linsen der systematischen Interpretation.",
        "styles_kicker": "Stileffekt",
        "styles_title": "Die Reiseform verändert die Destination",
        "styles_lead": "Diese Linsen zeigen, warum ein Ort nicht ohne seine Reiseform bewertet werden kann.",
        "open_style_label": "Referenz öffnen ->",
        "method_kicker": "Methode",
        "method_title": "Ein Hub ohne falsche Abdeckung",
        "method_lead": "Dieser Hub etabliert die Logik, bevor einzelne Destinationsseiten skaliert werden.",
        "final_kicker": "Nächster Schritt",
        "final_title": "Wähle die Reiseform, bevor du den Ort beurteilst",
        "final_lead": "Eine Destination wird durch Einschränkungen, Autonomie, Unterstützung, Last, Tiefe und Vorhersehbarkeit verständlich.",
    },
    "zh": {
        "eyebrow": "目的地解释 · 旅行方式语境 · 决策层",
        "title": "同一个地方，不是同一次旅行",
        "lead": "TourVsTravel 将目的地视为由旅行方式解释的环境，而不是地图上的静态点。",
        "actions_label": "目的地中心操作",
        "primary_action": "找到适合方式",
        "secondary_action": "探索旅行方式",
        "compare_action": "比较旅行形式",
        "panel_label": "目的地解释信号",
        "panel_card_1_label": "核心论点",
        "panel_card_1_value": "目的地会随着旅行形式而改变。",
        "panel_card_2_label": "关联方式",
        "panel_card_2_value": "种旅行方式塑造解释。",
        "panel_card_3_label": "输出",
        "panel_card_3_value": "目的地意义在承诺前变得清晰。",
        "thesis_kicker": "参考论点",
        "thesis_title": "目的地不只是你去哪里",
        "thesis_lead": "目的地是访问、节奏、成本、摩擦、支持、暴露度和体验深度的系统。",
        "lenses_kicker": "解释镜头",
        "lenses_title": "目的地如何改变",
        "lenses_lead": "在建立单独目的地页面前，TourVsTravel 先定义系统化解释镜头。",
        "styles_kicker": "旅行方式影响",
        "styles_title": "旅行形式改变目的地",
        "styles_lead": "这些镜头说明为什么不能脱离旅行方式来评价一个地方。",
        "open_style_label": "打开方式参考 ->",
        "method_kicker": "方法",
        "method_title": "没有虚假覆盖的目的地中心",
        "method_lead": "这个中心先建立逻辑，再逐步扩展到单独目的地页面。",
        "final_kicker": "下一步",
        "final_title": "先选择旅行形式，再判断地点",
        "final_lead": "目的地通过限制、自主、支持、负担、深度和可预测性变得有意义。",
    },
    "ja": {
        "eyebrow": "目的地解釈 · 旅行スタイル文脈 · 意思決定レイヤー",
        "title": "同じ場所は、同じ旅ではない",
        "lead": "TourVsTravel は、目的地を地図上の静的な点ではなく、旅行スタイルによって解釈される環境として扱います。",
        "actions_label": "目的地ハブの操作",
        "primary_action": "自分に合う旅を探す",
        "secondary_action": "旅行スタイルを探索",
        "compare_action": "旅行形式を比較",
        "panel_label": "目的地解釈のシグナル",
        "panel_card_1_label": "中心命題",
        "panel_card_1_value": "目的地は旅行形式によって変化する。",
        "panel_card_2_label": "接続スタイル",
        "panel_card_2_value": "旅行スタイルが解釈を形作ります。",
        "panel_card_3_label": "出力",
        "panel_card_3_value": "目的地の意味が決定前に読み取れる。",
        "thesis_kicker": "参照命題",
        "thesis_title": "目的地は単なる場所ではない",
        "thesis_lead": "目的地は、アクセス、リズム、費用、摩擦、支援、露出、深度のシステムです。",
        "lenses_kicker": "解釈レンズ",
        "lenses_title": "目的地がどう変わるか",
        "lenses_lead": "個別ページを作る前に、TourVsTravel は体系的な解釈レンズを定義します。",
        "styles_kicker": "スタイル効果",
        "styles_title": "旅行形式が目的地を変える",
        "styles_lead": "これらのレンズは、旅行形式なしに場所を評価できない理由を示します。",
        "open_style_label": "参照を開く ->",
        "method_kicker": "方法",
        "method_title": "偽の網羅性を持たない目的地ハブ",
        "method_lead": "このハブは、個別目的地ページへ拡張する前に論理を確立します。",
        "final_kicker": "次のステップ",
        "final_title": "場所を判断する前に旅行形式を選ぶ",
        "final_lead": "目的地は、制約、自律性、支援、負担、深度、予測可能性を通じて意味を持ちます。",
    },
}


DESTINATION_LENSES: Dict[str, List[Dict[str, str]]] = {
    "en": [
        {"label": "Access", "title": "How the place is entered", "description": "A destination changes when access is handled by a guide, a cruise route, a rental car, public transport, or self-navigation.", "signal": "Access is the first layer of interpretation."},
        {"label": "Rhythm", "title": "How time moves there", "description": "The same city can feel compressed, slow, curated, chaotic, luxurious, or improvisational depending on the pace of travel.", "signal": "Pace changes perception."},
        {"label": "Friction", "title": "How much difficulty is exposed", "description": "Some styles hide friction; others make it part of the experience. Both produce different versions of the same place.", "signal": "Friction is not always failure."},
        {"label": "Support", "title": "How much mediation exists", "description": "Translation, local knowledge, safety, and logistics can make the same destination feel controlled or open-ended.", "signal": "Support changes confidence."},
        {"label": "Depth", "title": "How directly the place is encountered", "description": "A destination may be consumed through highlights, lived through routine, or explored through immersion.", "signal": "Depth changes meaning."},
        {"label": "Cost logic", "title": "How value is distributed", "description": "Luxury, budget, package, slow, and independent travel distribute cost across comfort, time, access, and autonomy differently.", "signal": "Cost is a structure, not just a price."},
    ],
    "ar": [
        {"label": "الوصول", "title": "كيف يدخل المسافر إلى المكان", "description": "تتغير الوجهة عندما يكون الوصول عبر مرشد أو مسار بحري أو سيارة أو نقل عام أو تنقل ذاتي.", "signal": "الوصول هو طبقة التفسير الأولى."},
        {"label": "الإيقاع", "title": "كيف يتحرك الوقت داخل الوجهة", "description": "المدينة نفسها قد تبدو مضغوطة أو بطيئة أو منظمة أو فوضوية أو فاخرة حسب إيقاع السفر.", "signal": "الإيقاع يغير الإدراك."},
        {"label": "الاحتكاك", "title": "ما مقدار الصعوبة الظاهرة", "description": "بعض الأنماط تخفي الاحتكاك، وبعضها يجعله جزءًا من التجربة.", "signal": "الاحتكاك ليس دائمًا فشلًا."},
        {"label": "الدعم", "title": "ما مقدار الوساطة الموجودة", "description": "اللغة والمعرفة المحلية والسلامة واللوجستيك تجعل الوجهة مضبوطة أو مفتوحة.", "signal": "الدعم يغير الثقة."},
        {"label": "العمق", "title": "كيف يُعاش المكان مباشرة", "description": "قد تُستهلك الوجهة عبر أبرز النقاط أو تُعاش عبر الروتين أو تُستكشف بالانغماس.", "signal": "العمق يغير المعنى."},
        {"label": "منطق التكلفة", "title": "كيف تتوزع القيمة", "description": "السفر الفاخر أو الاقتصادي أو البطيء أو المستقل يوزع التكلفة بين الراحة والوقت والوصول والاستقلالية.", "signal": "التكلفة بنية وليست سعرًا فقط."},
    ],
    "fr": [
        {"label": "Accès", "title": "Comment le lieu est abordé", "description": "Une destination change selon que l’accès passe par guide, croisière, voiture, transport public ou autonomie.", "signal": "L’accès est la première couche."},
        {"label": "Rythme", "title": "Comment le temps s’y déplace", "description": "Une même ville peut paraître comprimée, lente, organisée, chaotique ou luxueuse selon le rythme.", "signal": "Le rythme change la perception."},
        {"label": "Friction", "title": "Quelle difficulté apparaît", "description": "Certains styles cachent la friction; d’autres l’intègrent à l’expérience.", "signal": "La friction n’est pas toujours un échec."},
        {"label": "Soutien", "title": "Quelle médiation existe", "description": "Langue, connaissance locale, sécurité et logistique changent la confiance du voyageur.", "signal": "Le soutien change l’assurance."},
        {"label": "Profondeur", "title": "Comment le lieu est rencontré", "description": "Un lieu peut être consommé par ses points forts, vécu par routine ou exploré par immersion.", "signal": "La profondeur change le sens."},
        {"label": "Logique de coût", "title": "Comment la valeur se distribue", "description": "Le coût se répartit entre confort, temps, accès et autonomie.", "signal": "Le coût est une structure."},
    ],
}

STYLE_EFFECT_COPY: Dict[str, Dict[str, str]] = {
    "guided-group-tour": {"en": "Turns the destination into a sequenced narrative with reduced uncertainty and mediated access.", "ar": "يحوّل الوجهة إلى سرد منظم بتقليل عدم اليقين ووساطة أكبر في الوصول.", "fr": "Transforme la destination en récit séquencé avec moins d’incertitude et un accès médiatisé."},
    "independent-travel": {"en": "Turns the destination into a field of direct choices, navigation, tradeoffs, and self-managed friction.", "ar": "يحوّل الوجهة إلى مجال اختيارات مباشرة وتنقل ومفاضلات واحتكاك ذاتي الإدارة.", "fr": "Transforme la destination en champ de choix directs, arbitrages et friction autogérée."},
    "backpacking": {"en": "Exposes the destination through budget pressure, mobility, uncertainty, and high-contact experience.", "ar": "يكشف الوجهة عبر ضغط الميزانية والحركة وعدم اليقين والاحتكاك المباشر.", "fr": "Expose la destination par budget limité, mobilité, incertitude et contact direct."},
    "luxury-travel": {"en": "Filters the destination through comfort, access control, service quality, and reduced operational burden.", "ar": "يفسر الوجهة عبر الراحة وضبط الوصول وجودة الخدمة وتقليل العبء التشغيلي.", "fr": "Filtre la destination par confort, contrôle d’accès, service et moindre charge opérationnelle."},
    "family-travel": {"en": "Reframes the destination around safety, pacing, coordination, predictability, and shared constraints.", "ar": "يعيد تشكيل الوجهة حول السلامة والإيقاع والتنسيق وقابلية التوقع والقيود المشتركة.", "fr": "Recadre la destination autour de sécurité, rythme, coordination, prévisibilité et contraintes partagées."},
    "slow-travel": {"en": "Turns the destination into a long-duration environment where routine, depth, and local rhythm matter.", "ar": "يحوّل الوجهة إلى بيئة طويلة المدى حيث يصبح الروتين والعمق والإيقاع المحلي مهمًا.", "fr": "Transforme la destination en environnement long où routine, profondeur et rythme local comptent."},
}

METHOD_CARDS: Dict[str, List[Dict[str, str]]] = {
    "en": [
        {"label": "No false inventory", "value": "The hub does not pretend to contain hundreds of thin destination pages."},
        {"label": "Interpretation first", "value": "Destination meaning is defined before destination scale is generated."},
        {"label": "Style-connected", "value": "Every future destination page should connect to travel-style logic."},
    ],
    "ar": [
        {"label": "لا مخزون وهمي", "value": "لا يدعي المحور امتلاك مئات الصفحات الضعيفة عن الوجهات."},
        {"label": "التفسير أولًا", "value": "يُعرّف معنى الوجهة قبل التوسع في صفحات كثيرة."},
        {"label": "مرتبط بالأنماط", "value": "كل صفحة وجهة مستقبلية يجب أن ترتبط بمنطق أنماط السفر."},
    ],
    "fr": [
        {"label": "Pas d’inventaire fictif", "value": "Le hub ne prétend pas contenir des centaines de pages faibles."},
        {"label": "Interprétation d’abord", "value": "Le sens de la destination est défini avant l’échelle."},
        {"label": "Connecté aux styles", "value": "Chaque future page doit se connecter à la logique des styles."},
    ],
}

INTERPRETATION_STEPS: Dict[str, List[Dict[str, str]]] = {
    "en": [
        {"label": "Layer 1", "title": "Place", "description": "The physical destination: city, coast, route, region, or landscape."},
        {"label": "Layer 2", "title": "Travel form", "description": "The method used to enter, move through, and experience that place."},
        {"label": "Layer 3", "title": "Traveler fit", "description": "The relationship between the place, the style, and the traveler’s constraints."},
    ],
    "ar": [
        {"label": "الطبقة 1", "title": "المكان", "description": "الوجهة المادية: مدينة، ساحل، مسار، منطقة، أو مشهد طبيعي."},
        {"label": "الطبقة 2", "title": "شكل السفر", "description": "الطريقة التي يدخل بها المسافر المكان ويتحرك داخله ويعيشه."},
        {"label": "الطبقة 3", "title": "ملاءمة المسافر", "description": "العلاقة بين المكان والنمط وقيود المسافر."},
    ],
    "fr": [
        {"label": "Couche 1", "title": "Lieu", "description": "La destination physique: ville, côte, route, région ou paysage."},
        {"label": "Couche 2", "title": "Forme de voyage", "description": "La manière d’entrer, de se déplacer et d’expérimenter le lieu."},
        {"label": "Couche 3", "title": "Adéquation", "description": "La relation entre lieu, style et contraintes du voyageur."},
    ],
}


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
        for candidate in (value.get(lang), value.get("en")):
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
    return default


def _get_nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _normalize_https_base_url(site_config: Mapping[str, Any]) -> str:
    raw = _clean_string(_get_nested(site_config, ("site", "base_url"), "https://tourvstravel.com"))
    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise DestinationsConfigError(f"site.base_url must be an absolute HTTPS URL. Got: {raw!r}")
    if parsed.query or parsed.fragment or (parsed.path or "") not in ("", "/"):
        raise DestinationsConfigError(f"site.base_url must not contain path, query, or fragment. Got: {raw!r}")
    return f"https://{parsed.netloc.rstrip('/')}"


def _extract_enabled_languages(site_config: Mapping[str, Any]) -> List[str]:
    raw = _get_nested(site_config, ("languages", "supported"), None)
    if not isinstance(raw, list):
        raw = _get_nested(site_config, ("languages", "enabled"), None)
    if not isinstance(raw, list):
        return list(SUPPORTED_LANGUAGES)
    languages: List[str] = []
    for item in raw:
        code = _clean_string(item.get("code") if isinstance(item, Mapping) else item)
        if isinstance(item, Mapping) and item.get("enabled", True) is False:
            continue
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
    return _localized(_get_nested(site_config, ("site", "name"), "TourVsTravel"), lang, default="TourVsTravel")


def _extract_theme_color(site_config: Mapping[str, Any]) -> str:
    color = _get_nested(site_config, ("branding", "theme_color"), "#0f172a")
    return color.strip() if isinstance(color, str) and color.strip() else "#0f172a"


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
    if not public_path.startswith("/static/"):
        raise DestinationsConfigError(f"{label} must start with /static/: {public_path}")
    asset_path = (ROOT_DIR / public_path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise DestinationsConfigError(f"{label} points outside static/: {public_path}") from exc
    if not asset_path.is_file():
        raise DestinationsConfigError(f"{label} points to a missing static asset: {public_path}")
    return public_path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo"), {})
    if not isinstance(logo, Mapping):
        logo = {}
    icon_path = _clean_string(logo.get("icon_path"), default="/static/img/brand/logo-icon.webp")
    return _require_existing_asset(icon_path, "branding.logo.icon_path")


def _resolve_manifest_url() -> Optional[str]:
    return "/static/site.webmanifest" if (STATIC_DIR / "site.webmanifest").is_file() else None


def _style_items(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    for key in ("active_experience_types", "experience_types"):
        value = payload.get(key)
        if isinstance(value, list):
            items = [item for item in value if isinstance(item, Mapping)]
            if items:
                return items
    return []


def _style_by_slug(payload: Mapping[str, Any]) -> Dict[str, Mapping[str, Any]]:
    return {
        _clean_string(item.get("slug")): item
        for item in _style_items(payload)
        if _clean_string(item.get("slug"))
    }


def _style_title(item: Mapping[str, Any], lang: str, slug: str) -> str:
    return _localized(item.get("title") or item.get("name") or item.get("label"), lang, default=slug.replace("-", " ").title())


def _style_lenses(payload: Mapping[str, Any], lang: str) -> List[Dict[str, str]]:
    by_slug = _style_by_slug(payload)
    preferred_slugs = (
        "guided-group-tour",
        "independent-travel",
        "backpacking",
        "luxury-travel",
        "family-travel",
        "slow-travel",
    )
    output: List[Dict[str, str]] = []
    for slug in preferred_slugs:
        item = by_slug.get(slug)
        if not item:
            continue
        effect_copy = STYLE_EFFECT_COPY.get(slug, {})
        output.append(
            {
                "slug": slug,
                "title": _style_title(item, lang, slug),
                "description": effect_copy.get(lang, effect_copy.get("en", "")),
                "href": f"/{lang}/styles/{slug}/",
                "signal": slug.replace("-", " ").title(),
            }
        )
    if output:
        return output
    return [
        {
            "slug": _clean_string(item.get("slug")),
            "title": _style_title(item, lang, _clean_string(item.get("slug"))),
            "description": "A travel style that changes how the destination is encountered.",
            "href": f"/{lang}/styles/{_clean_string(item.get('slug'))}/",
            "signal": _clean_string(item.get("slug")).replace("-", " ").title(),
        }
        for item in _style_items(payload)[:6]
        if _clean_string(item.get("slug"))
    ]


def _number_lenses(lenses: List[Dict[str, str]]) -> List[Dict[str, str]]:
    output: List[Dict[str, str]] = []
    for idx, lens in enumerate(lenses, start=1):
        item = dict(lens)
        item["number"] = f"{idx:02d}"
        output.append(item)
    return output


def _destination_lenses(lang: str) -> List[Dict[str, str]]:
    return _number_lenses(DESTINATION_LENSES.get(lang, DESTINATION_LENSES["en"]))


def _method_cards(lang: str) -> List[Dict[str, str]]:
    return METHOD_CARDS.get(lang, METHOD_CARDS["en"])


def _interpretation_steps(lang: str) -> List[Dict[str, str]]:
    return INTERPRETATION_STEPS.get(lang, INTERPRETATION_STEPS["en"])


def _create_jinja_env() -> Environment:
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
        raise DestinationsWriteError(f"Unable to write destination hub page {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise DestinationsWriteError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise DestinationsWriteError(f"Refusing symlink output directory: {resolved}")
    if resolved.parent.exists() and resolved.parent.is_symlink():
        raise DestinationsWriteError(f"Refusing symlink parent for output directory: {resolved.parent}")
    return resolved


def _build_hreflang(base_url: str, languages: Sequence[str]) -> List[Dict[str, str]]:
    return [{"lang": lang, "url": f"{base_url}/{lang}/destinations/"} for lang in languages]


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
                "@type": "WebPage",
                "name": title,
                "description": description,
                "url": canonical_url,
                "inLanguage": lang,
                "isPartOf": {"@type": "WebSite", "name": site_name, "url": base_url},
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
        "og": {"title": title, "description": description, "image": f"{base_url}{logo_url}", "type": "website", "url": canonical_url, "site_name": site_name, "image_alt": site_name},
        "twitter": {"card": "summary_large_image", "title": title, "description": description, "image": f"{base_url}{logo_url}", "image_alt": site_name},
        "jsonld": jsonld,
        "extra_meta": [],
    }
    if locale:
        payload["og_locale"] = locale
    if alternate_locales:
        payload["og_locale_alternates"] = alternate_locales
    return payload


def _build_context(site_config: Mapping[str, Any], styles_payload: Mapping[str, Any], lang: str, languages: Sequence[str]) -> Dict[str, Any]:
    base_url = _normalize_https_base_url(site_config)
    site_name = _extract_site_name(site_config, lang)
    copy = PAGE_COPY.get(lang, PAGE_COPY["en"])
    logo_url = _resolve_logo_path(site_config)
    canonical_url = f"{base_url}/{lang}/destinations/"
    title = f"{copy['title']} | {site_name}"
    description = copy["lead"]
    seo_payload = _build_seo_payload(site_config=site_config, lang=lang, title=title, description=description, canonical_url=canonical_url, base_url=base_url, site_name=site_name, logo_url=logo_url, languages=languages)
    main_css_url = _require_existing_asset("/static/css/main.css", "main_css_url")
    main_js_url = _require_existing_asset("/static/js/main.js", "main_js_url")

    return {
        "base_url": base_url,
        "lang": lang,
        "page_lang": lang,
        "current_lang": lang,
        "language": lang,
        "page_dir": _language_direction(site_config, lang),
        "is_rtl": _language_direction(site_config, lang) == "rtl",
        "body_class": "page-destinations",
        "current_year": datetime.now(timezone.utc).year,
        "site_name": site_name,
        "copy": copy,
        "style_count": len(_style_items(styles_payload)) or 17,
        "destination_lenses": _destination_lenses(lang),
        "style_lenses": _style_lenses(styles_payload, lang),
        "method_cards": _method_cards(lang),
        "interpretation_steps": _interpretation_steps(lang),
        "canonical_url": canonical_url,
        "seo": seo_payload,
        "hreflang": seo_payload["hreflang"],
        "meta_desc": description,
        "robots_directive": seo_payload["robots_directive"],
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
        "active_nav": "destinations",
        "footer_note": "",
    }


def render_destinations_page(*, site_config: Mapping[str, Any], styles_payload: Mapping[str, Any], lang: str, languages: Sequence[str]) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise DestinationsRenderError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc
    try:
        html_output = template.render(**_build_context(site_config, styles_payload, lang, languages))
    except TemplateError as exc:
        raise DestinationsRenderError(f"Unable to render destinations page [{lang}]: {exc}") from exc
    if not html_output.strip():
        raise DestinationsRenderError(f"Rendered destinations page is empty for language {lang!r}.")
    return html_output


def generate_destinations_pages(*, requested_lang: Optional[str] = None, output_dir: Path = DEFAULT_OUTPUT_DIR) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise DestinationsConfigError("load_site_config() must return a mapping/object.")
    styles_payload = load_experience_types()
    if not isinstance(styles_payload, Mapping):
        raise DestinationsConfigError("load_experience_types() must return a mapping/object.")
    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise DestinationsConfigError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise DestinationsConfigError("No enabled languages available for destinations generation.")

    rendered: List[tuple[Path, str, str]] = []
    for lang in languages:
        html_output = render_destinations_page(site_config=site_config, styles_payload=styles_payload, lang=lang, languages=languages)
        output_path = safe_output_dir / lang / "destinations" / "index.html"
        rendered.append((output_path, html_output, lang))
    written: List[Path] = []
    for output_path, html_output, lang in rendered:
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated destinations page [%s] -> %s", lang, output_path)
    log.info("Destinations generation completed successfully. Files written: %d", len(written))
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate multilingual TourVsTravel destination interpretation hub pages.")
    parser.add_argument("--lang", type=str, default=None, help="Generate one language only.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory root.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        generate_destinations_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateDestinationsError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected destinations generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
