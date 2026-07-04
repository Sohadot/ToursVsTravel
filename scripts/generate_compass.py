#!/usr/bin/env python3
"""
TourVsTravel - Travel Decision Compass
======================================
Generates:
  output/{lang}/tools/travel-decision-compass/index.html

The Compass is the first shipped implementation of the Structure Fit
Protocol (SFP, published as part of TDIS v1 at /{lang}/standard/):

  1. classify  - candidates are the 17 TSO structures
  2. score-fit - proximity across the six structural axes + traveler profile
  3. apply-standard - priors contextualized, uncertainty declared, no
     universal winner
  4. emit-diagnosis - ranked fit with explicit tradeoffs, linked back to the
     ontology class pages used

Governance:
- Structures, axes, and affinities are loaded from the canonical ontology
  dataset (single source shared with the TSO page and machine layer).
- Score bands and result count come from data/tools_config.yaml
  (evaluation_model), so engine behavior is configured, not hardcoded.
- Fully client-side: no network calls, no storage, no tracking. Estimates
  are structural fits, never live market data (TDIS rule cost-bands).
- Scope note (DECISIONS.md D-006): v1 diagnoses traveler-constraint fit
  only; the destination input configured in tools_config is the v2 contract
  and activates when the governed destinations dataset ships.
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

from scripts.generate_category_infrastructure import (
    AXIS_COPY,
    AXIS_ORDER,
    GenerateCategoryInfrastructureError,
    load_ontology_structures,
)
from scripts.loaders import (
    load_site_config,
    load_yaml,
    resolve_footer_reference_report_label,
    resolve_nav_report_label,
)
from scripts.reference_i18n import localized_ui_context
from scripts.routes import (
    build_about_path,
    build_acquire_path,
    build_changelog_path,
    build_compare_index_path,
    build_contact_path,
    build_destinations_index_path,
    build_editorial_standards_path,
    build_experience_type_path,
    build_home_path,
    build_methodology_path,
    build_ontology_path,
    build_privacy_path,
    build_reference_report_path,
    build_source_policy_path,
    build_standard_path,
    build_tools_index_path,
    build_travel_decision_architecture_path,
)
from scripts.seo import (
    build_organization_jsonld,
    build_page_seo,
    build_webpage_jsonld,
    build_website_jsonld,
)

log = logging.getLogger("generate_compass")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/compass.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

TOOL_ID = "travel_decision_compass"
TOOL_SLUG = "travel-decision-compass"
COMPASS_JS_PATH = "/static/js/travel-decision-compass.js"

PROFILE_ORDER = (
    "independent_planner",
    "family_coordinator",
    "first_time_traveler",
    "cost_sensitive_explorer",
    "comfort_priority_traveler",
    "logistics_averse_traveler",
)


class GenerateCompassError(Exception):
    pass


# ============================================================================
# Localized copy
# ============================================================================

VALUE_LABELS: Dict[str, Dict[str, str]] = {
    "low":      {"en": "low", "ar": "منخفض", "fr": "faible", "es": "bajo", "de": "niedrig", "zh": "低", "ja": "低い"},
    "medium":   {"en": "medium", "ar": "متوسط", "fr": "moyen", "es": "medio", "de": "mittel", "zh": "中", "ja": "中程度"},
    "high":     {"en": "high", "ar": "مرتفع", "fr": "élevé", "es": "alto", "de": "hoch", "zh": "高", "ja": "高い"},
    "fixed":    {"en": "fixed", "ar": "ثابت", "fr": "fixe", "es": "fijo", "de": "fest", "zh": "固定", "ja": "固定"},
    "balanced": {"en": "balanced", "ar": "متوازن", "fr": "équilibré", "es": "equilibrado", "de": "ausgewogen", "zh": "均衡", "ja": "均衡"},
    "flexible": {"en": "flexible", "ar": "مرن", "fr": "flexible", "es": "flexible", "de": "flexibel", "zh": "灵活", "ja": "柔軟"},
    "surface":  {"en": "surface", "ar": "سطحي", "fr": "en surface", "es": "superficial", "de": "oberflächlich", "zh": "表层", "ja": "表層"},
    "deep":     {"en": "deep", "ar": "عميق", "fr": "profond", "es": "profundo", "de": "tief", "zh": "深入", "ja": "深い"},
}

BAND_LABELS: Dict[str, Dict[str, str]] = {
    "strong_fit":   {"en": "Strong fit", "ar": "ملاءمة قوية", "fr": "Adéquation forte", "es": "Ajuste fuerte", "de": "Starke Passung", "zh": "高度适配", "ja": "高い適合"},
    "good_fit":     {"en": "Good fit", "ar": "ملاءمة جيدة", "fr": "Bonne adéquation", "es": "Buen ajuste", "de": "Gute Passung", "zh": "良好适配", "ja": "良い適合"},
    "possible_fit": {"en": "Possible fit", "ar": "ملاءمة محتملة", "fr": "Adéquation possible", "es": "Ajuste posible", "de": "Mögliche Passung", "zh": "可能适配", "ja": "適合の可能性"},
    "weak_fit":     {"en": "Weak fit", "ar": "ملاءمة ضعيفة", "fr": "Adéquation faible", "es": "Ajuste débil", "de": "Schwache Passung", "zh": "较弱适配", "ja": "弱い適合"},
    "no_fit":       {"en": "Not a fit", "ar": "غير ملائم", "fr": "Pas adapté", "es": "No adecuado", "de": "Keine Passung", "zh": "不适配", "ja": "不適合"},
}

QUESTION_TEXT: Dict[str, Dict[str, str]] = {
    "structure_intensity": {
        "en": "How much of the trip should be settled before departure?",
        "ar": "كم من الرحلة ينبغي حسمه قبل المغادرة؟",
        "fr": "Quelle part du voyage doit être réglée avant le départ ?",
        "es": "¿Qué parte del viaje debe quedar resuelta antes de salir?",
        "de": "Wie viel der Reise soll vor der Abreise feststehen?",
        "zh": "出发前应确定多少行程？",
        "ja": "出発前に旅程をどこまで確定させたいですか？",
    },
    "autonomy_level": {
        "en": "While traveling, how much do you want to decide yourself?",
        "ar": "أثناء السفر، كم تريد أن تقرر بنفسك؟",
        "fr": "En voyage, dans quelle mesure voulez-vous décider vous-même ?",
        "es": "Durante el viaje, ¿cuánto quieres decidir por ti mismo?",
        "de": "Wie viel möchten Sie unterwegs selbst entscheiden?",
        "zh": "旅行途中，你希望自己决定多少？",
        "ja": "旅行中、どの程度自分で決めたいですか？",
    },
    "support_level": {
        "en": "How much built-in help should the format carry?",
        "ar": "كم من المساعدة المدمجة تريد في صيغة السفر؟",
        "fr": "Quelle aide intégrée le format doit-il inclure ?",
        "es": "¿Cuánta ayuda incorporada debe tener el formato?",
        "de": "Wie viel eingebaute Unterstützung soll das Format bieten?",
        "zh": "这种旅行形式应内置多少协助？",
        "ja": "その旅行形式にどれだけのサポートを組み込みたいですか？",
    },
    "pace_profile": {
        "en": "How should time behave on this trip?",
        "ar": "كيف ينبغي أن يسير الوقت في هذه الرحلة؟",
        "fr": "Comment le temps doit-il se comporter pendant ce voyage ?",
        "es": "¿Cómo debe comportarse el tiempo en este viaje?",
        "de": "Wie soll sich die Zeit auf dieser Reise verhalten?",
        "zh": "这趟旅行的时间应如何安排？",
        "ja": "この旅で時間はどのように流れるべきですか？",
    },
    "immersion_profile": {
        "en": "How deep should contact with the place go?",
        "ar": "ما عمق الاتصال بالمكان الذي تريده؟",
        "fr": "Quelle profondeur de contact avec le lieu recherchez-vous ?",
        "es": "¿Qué profundidad de contacto con el lugar buscas?",
        "de": "Wie tief soll der Kontakt zum Ort gehen?",
        "zh": "你希望与当地的接触有多深？",
        "ja": "その土地との関わりはどの深さを望みますか？",
    },
    "predictability_profile": {
        "en": "How predictable should the trip stay?",
        "ar": "ما مقدار القابلية للتنبؤ الذي تريده في الرحلة؟",
        "fr": "À quel point le voyage doit-il rester prévisible ?",
        "es": "¿Cuán predecible debe mantenerse el viaje?",
        "de": "Wie vorhersehbar soll die Reise bleiben?",
        "zh": "这趟旅行应保持多大的可预测性？",
        "ja": "旅はどの程度予測可能であるべきですか？",
    },
    "traveler_profile": {
        "en": "Which describes you best on this trip?",
        "ar": "أي وصف يطابقك أكثر في هذه الرحلة؟",
        "fr": "Qu'est-ce qui vous décrit le mieux pour ce voyage ?",
        "es": "¿Qué te describe mejor en este viaje?",
        "de": "Was beschreibt Sie auf dieser Reise am besten?",
        "zh": "哪一项最能描述这趟旅行中的你？",
        "ja": "この旅でのあなたに最も当てはまるのはどれですか？",
    },
}

AXIS_OPTION_TEXT: Dict[str, Dict[str, Dict[str, str]]] = {
    "structure_intensity": {
        "high":   {"en": "Most of it — booked and scheduled", "ar": "معظمها — محجوزة ومجدولة", "fr": "L'essentiel — réservé et planifié", "es": "La mayor parte: reservada y programada", "de": "Das meiste — gebucht und terminiert", "zh": "大部分——已预订并排程", "ja": "ほとんど——予約・日程確定済み"},
        "medium": {"en": "The backbone only", "ar": "الهيكل الأساسي فقط", "fr": "Seulement l'ossature", "es": "Solo la estructura básica", "de": "Nur das Grundgerüst", "zh": "只定主干", "ja": "骨組みだけ"},
        "low":    {"en": "As little as possible", "ar": "أقل قدر ممكن", "fr": "Le moins possible", "es": "Lo mínimo posible", "de": "So wenig wie möglich", "zh": "越少越好", "ja": "できるだけ少なく"},
    },
    "autonomy_level": {
        "high":   {"en": "I decide almost everything", "ar": "أقرر كل شيء تقريبًا", "fr": "Je décide presque tout", "es": "Decido casi todo", "de": "Ich entscheide fast alles", "zh": "几乎都由我决定", "ja": "ほぼすべて自分で決める"},
        "medium": {"en": "I decide some, the rest is handled", "ar": "أقرر بعض الأمور والباقي يُدار", "fr": "Je décide en partie, le reste est géré", "es": "Decido una parte, el resto se gestiona", "de": "Ich entscheide teils, der Rest wird geregelt", "zh": "部分我定，其余交由安排", "ja": "一部は自分で、残りは任せる"},
        "low":    {"en": "I prefer it handled for me", "ar": "أفضّل أن يُدار الأمر عني", "fr": "Je préfère que ce soit géré pour moi", "es": "Prefiero que lo gestionen por mí", "de": "Ich lasse es lieber für mich regeln", "zh": "更希望有人替我安排", "ja": "任せる方がよい"},
    },
    "support_level": {
        "high":   {"en": "Full support on call", "ar": "دعم كامل عند الطلب", "fr": "Un soutien complet à disposition", "es": "Apoyo completo disponible", "de": "Volle Unterstützung auf Abruf", "zh": "全程可用的支持", "ja": "手厚いサポート"},
        "medium": {"en": "Help for the hard parts only", "ar": "مساعدة في الأجزاء الصعبة فقط", "fr": "De l'aide pour les parties difficiles seulement", "es": "Ayuda solo en las partes difíciles", "de": "Hilfe nur für die schwierigen Teile", "zh": "仅在困难环节需要帮助", "ja": "難しい部分だけ助けてほしい"},
        "low":    {"en": "I bring my own resourcefulness", "ar": "أعتمد على قدرتي في التدبير", "fr": "Je compte sur ma débrouillardise", "es": "Me valgo de mis propios recursos", "de": "Ich helfe mir selbst", "zh": "靠自己解决", "ja": "自力で対処する"},
    },
    "pace_profile": {
        "fixed":    {"en": "A set schedule", "ar": "جدول محدد", "fr": "Un horaire fixe", "es": "Un horario fijo", "de": "Ein fester Zeitplan", "zh": "固定日程", "ja": "決まったスケジュール"},
        "balanced": {"en": "A mix of planned and open", "ar": "مزيج من المخطط والمفتوح", "fr": "Un mélange de planifié et de libre", "es": "Mezcla de planificado y abierto", "de": "Mischung aus geplant und offen", "zh": "计划与自由兼有", "ja": "計画と自由の混合"},
        "flexible": {"en": "Open and adjustable", "ar": "مفتوح وقابل للتعديل", "fr": "Ouvert et ajustable", "es": "Abierto y ajustable", "de": "Offen und anpassbar", "zh": "开放可调整", "ja": "柔軟に調整できる"},
    },
    "immersion_profile": {
        "surface":  {"en": "The highlights, efficiently", "ar": "أبرز المعالم بكفاءة", "fr": "Les incontournables, efficacement", "es": "Lo esencial, con eficiencia", "de": "Die Highlights, effizient", "zh": "高效看亮点", "ja": "見どころを効率よく"},
        "balanced": {"en": "A balance of both", "ar": "توازن بين الاثنين", "fr": "Un équilibre des deux", "es": "Un equilibrio de ambos", "de": "Eine Balance aus beidem", "zh": "两者平衡", "ja": "両方のバランス"},
        "deep":     {"en": "Slow, deep contact", "ar": "اتصال بطيء وعميق", "fr": "Un contact lent et profond", "es": "Contacto lento y profundo", "de": "Langsamer, tiefer Kontakt", "zh": "缓慢而深入的接触", "ja": "ゆっくり深く関わる"},
    },
    "predictability_profile": {
        "high":   {"en": "Very predictable — few surprises", "ar": "قابل للتنبؤ جدًا — مفاجآت قليلة", "fr": "Très prévisible — peu de surprises", "es": "Muy predecible: pocas sorpresas", "de": "Sehr vorhersehbar — wenig Überraschungen", "zh": "高度可预测——少些意外", "ja": "非常に予測可能——驚きは少なく"},
        "medium": {"en": "Some room for the unplanned", "ar": "مساحة لبعض غير المخطط له", "fr": "Un peu de place pour l'imprévu", "es": "Algo de espacio para lo imprevisto", "de": "Etwas Raum für Ungeplantes", "zh": "留一些计划外空间", "ja": "予定外の余地も少し"},
        "low":    {"en": "Surprise is welcome", "ar": "المفاجأة مرحب بها", "fr": "La surprise est bienvenue", "es": "La sorpresa es bienvenida", "de": "Überraschung ist willkommen", "zh": "欢迎意外", "ja": "驚きは歓迎"},
    },
}

PROFILE_OPTION_TEXT: Dict[str, Dict[str, str]] = {
    "independent_planner":       {"en": "I plan and run my own trips", "ar": "أخطط رحلاتي وأديرها بنفسي", "fr": "Je planifie et gère mes propres voyages", "es": "Planifico y gestiono mis propios viajes", "de": "Ich plane und steuere meine Reisen selbst", "zh": "我自己规划并掌控旅程", "ja": "自分で旅を計画・運営する"},
    "family_coordinator":        {"en": "I coordinate for a family or group", "ar": "أنسق لعائلة أو مجموعة", "fr": "Je coordonne pour une famille ou un groupe", "es": "Coordino para una familia o grupo", "de": "Ich koordiniere für Familie oder Gruppe", "zh": "我为家庭或团队协调", "ja": "家族やグループの調整役"},
    "first_time_traveler":       {"en": "This kind of trip is new to me", "ar": "هذا النوع من الرحلات جديد عليّ", "fr": "Ce type de voyage est nouveau pour moi", "es": "Este tipo de viaje es nuevo para mí", "de": "Diese Art Reise ist neu für mich", "zh": "这类旅行对我是新体验", "ja": "この種の旅は初めて"},
    "cost_sensitive_explorer":   {"en": "I stretch every unit of budget", "ar": "أستثمر كل وحدة من الميزانية إلى أقصاها", "fr": "J'optimise chaque unité de budget", "es": "Estiro cada unidad de presupuesto", "de": "Ich hole aus jedem Budget das Maximum", "zh": "把每分预算用到极致", "ja": "予算を最大限に活かす"},
    "comfort_priority_traveler": {"en": "Comfort comes first", "ar": "الراحة أولًا", "fr": "Le confort d'abord", "es": "La comodidad es lo primero", "de": "Komfort geht vor", "zh": "舒适优先", "ja": "快適さが最優先"},
    "logistics_averse_traveler": {"en": "I want zero logistics on my plate", "ar": "لا أريد أي أعباء لوجستية", "fr": "Je ne veux aucune logistique à gérer", "es": "No quiero ninguna logística a mi cargo", "de": "Ich will keinerlei Logistik am Hals", "zh": "不想操心任何后勤", "ja": "手配事は一切抱えたくない"},
}

PAGE_COPY: Dict[str, Dict[str, Any]] = {
    "en": {
        "lead": "A structure-fit diagnosis: answer seven questions about constraints and intent, and get the travel structures that actually fit — with the tradeoffs stated.",
        "core_statement": "The Compass is the first shipped implementation of the Structure Fit Protocol. It runs entirely in your browser: no account, no tracking, no data sent anywhere.",
        "meta_description": "The Travel Decision Compass diagnoses which of the seventeen travel structures fit your constraints and intent, using the Structure Fit Protocol from the Travel Decision Integrity Standard.",
        "how_heading": "How the diagnosis works",
        "how_paragraphs": [
            "Your answers describe the trip you actually want across the six structural axes of the ontology, plus your traveler profile. Every one of the seventeen travel structures is scored for proximity to that description, and the top results are returned with their fit band.",
            "The result is a structural prior, not a verdict: it tells you which trip architectures match your constraints before destination context is applied. No structure is universally best, and the diagnosis always states what each option trades away.",
        ],
        "form_heading": "Seven questions",
        "noscript_note": "This tool runs in the browser and requires JavaScript. The seventeen structures it diagnoses are readable without it on the ontology page.",
        "submit_label": "Run the diagnosis",
        "reset_label": "Reset",
        "results_title": "Your structure-fit diagnosis",
        "matched_label": "Aligned with your answers:",
        "traded_label": "What this choice trades away:",
        "citation_label": "Cite as",
        "priors_note": "These rankings are structural priors under TDIS v1: contextualize them with destination and personal factors before committing. No universal winner exists between structures.",
        "incomplete_error": "Please answer all seven questions before running the diagnosis.",
        "standard_heading": "What governs this tool",
        "standard_paragraph": "The Compass implements the Structure Fit Protocol and is bound by the Travel Decision Integrity Standard: explicit criteria, priors before context, no fabricated prices, no universal winner.",
        "link_ontology": "Travel Structure Ontology (TSO) v1",
        "link_standard": "Integrity Standard (TDIS) v1",
        "link_methodology": "Methodology",
    },
    "ar": {
        "lead": "تشخيص ملاءمة بنيوي: أجب عن سبعة أسئلة حول القيود والنية، واحصل على بنى السفر التي تلائمك فعلًا — مع ذكر المفاضلات صراحة.",
        "core_statement": "البوصلة هي أول تنفيذ مُطلق لبروتوكول ملاءمة البنية. تعمل بالكامل في متصفحك: بلا حساب، بلا تتبع، وبلا إرسال أي بيانات.",
        "meta_description": "تشخّص بوصلة قرار السفر أيًا من بنى السفر السبع عشرة يلائم قيودك ونيتك، باستخدام بروتوكول ملاءمة البنية من معيار سلامة قرار السفر.",
        "how_heading": "كيف يعمل التشخيص",
        "how_paragraphs": [
            "تصف إجاباتك الرحلة التي تريدها فعلًا عبر المحاور البنيوية الستة للأنطولوجيا، إضافة إلى ملفك كمسافر. تُقيَّم كل بنية من البنى السبع عشرة بحسب قربها من ذلك الوصف، وتُعرض أفضل النتائج مع نطاق ملاءمتها.",
            "النتيجة افتراض بنيوي مسبق لا حكم نهائي: تخبرك أي هياكل رحلات تطابق قيودك قبل تطبيق سياق الوجهة. لا توجد بنية أفضل للجميع، والتشخيص يذكر دائمًا ما يتخلى عنه كل خيار.",
        ],
        "form_heading": "سبعة أسئلة",
        "noscript_note": "تعمل هذه الأداة في المتصفح وتتطلب JavaScript. البنى السبع عشرة التي تشخصها متاحة للقراءة بدونها في صفحة الأنطولوجيا.",
        "submit_label": "شغّل التشخيص",
        "reset_label": "إعادة تعيين",
        "results_title": "تشخيص ملاءمتك البنيوية",
        "matched_label": "متوافق مع إجاباتك:",
        "traded_label": "ما يتخلى عنه هذا الخيار:",
        "citation_label": "الاستشهاد",
        "priors_note": "هذه الترتيبات افتراضات بنيوية مسبقة وفق TDIS v1: ضعها في سياق الوجهة وعواملك الشخصية قبل الالتزام. لا يوجد فائز مطلق بين البنى.",
        "incomplete_error": "يرجى الإجابة عن الأسئلة السبعة كلها قبل تشغيل التشخيص.",
        "standard_heading": "ما الذي يحكم هذه الأداة",
        "standard_paragraph": "تنفذ البوصلة بروتوكول ملاءمة البنية وتلتزم بمعيار سلامة قرار السفر: معايير صريحة، وافتراضات مسبقة قبل السياق، وبلا أسعار مختلقة، وبلا فائز مطلق.",
        "link_ontology": "أنطولوجيا بنى السفر (TSO) v1",
        "link_standard": "معيار السلامة (TDIS) v1",
        "link_methodology": "المنهجية",
    },
    "fr": {
        "lead": "Un diagnostic d'adéquation structurelle : répondez à sept questions sur vos contraintes et votre intention, et obtenez les structures de voyage qui conviennent vraiment — compromis énoncés.",
        "core_statement": "La Boussole est la première implémentation publiée du Structure Fit Protocol. Elle fonctionne entièrement dans votre navigateur : sans compte, sans traçage, sans envoi de données.",
        "meta_description": "La Boussole de Décision de Voyage diagnostique lesquelles des dix-sept structures de voyage correspondent à vos contraintes et à votre intention, selon le Structure Fit Protocol du Travel Decision Integrity Standard.",
        "how_heading": "Comment fonctionne le diagnostic",
        "how_paragraphs": [
            "Vos réponses décrivent le voyage que vous voulez vraiment selon les six axes structurels de l'ontologie, plus votre profil de voyageur. Chacune des dix-sept structures est notée selon sa proximité avec cette description, et les meilleurs résultats sont présentés avec leur bande d'adéquation.",
            "Le résultat est un a priori structurel, non un verdict : il indique quelles architectures de voyage correspondent à vos contraintes avant l'application du contexte de destination. Aucune structure n'est universellement meilleure, et le diagnostic énonce toujours ce que chaque option sacrifie.",
        ],
        "form_heading": "Sept questions",
        "noscript_note": "Cet outil fonctionne dans le navigateur et nécessite JavaScript. Les dix-sept structures qu'il diagnostique restent lisibles sans lui sur la page de l'ontologie.",
        "submit_label": "Lancer le diagnostic",
        "reset_label": "Réinitialiser",
        "results_title": "Votre diagnostic d'adéquation structurelle",
        "matched_label": "Aligné avec vos réponses :",
        "traded_label": "Ce que ce choix sacrifie :",
        "citation_label": "Citer comme",
        "priors_note": "Ces classements sont des a priori structurels selon TDIS v1 : contextualisez-les avec la destination et vos facteurs personnels avant de vous engager. Aucun vainqueur universel n'existe entre les structures.",
        "incomplete_error": "Veuillez répondre aux sept questions avant de lancer le diagnostic.",
        "standard_heading": "Ce qui gouverne cet outil",
        "standard_paragraph": "La Boussole implémente le Structure Fit Protocol et est liée par le Travel Decision Integrity Standard : critères explicites, a priori avant contexte, aucun prix fabriqué, aucun vainqueur universel.",
        "link_ontology": "Ontologie des structures de voyage (TSO) v1",
        "link_standard": "Standard d'intégrité (TDIS) v1",
        "link_methodology": "Méthodologie",
    },
    "es": {
        "lead": "Un diagnóstico de ajuste estructural: responde siete preguntas sobre restricciones e intención y obtén las estructuras de viaje que realmente encajan, con las contrapartidas declaradas.",
        "core_statement": "La Brújula es la primera implementación publicada del Structure Fit Protocol. Funciona por completo en tu navegador: sin cuenta, sin rastreo, sin envío de datos.",
        "meta_description": "La Brújula de Decisión de Viaje diagnostica cuáles de las diecisiete estructuras de viaje encajan con tus restricciones e intención, según el Structure Fit Protocol del Travel Decision Integrity Standard.",
        "how_heading": "Cómo funciona el diagnóstico",
        "how_paragraphs": [
            "Tus respuestas describen el viaje que realmente quieres según los seis ejes estructurales de la ontología, más tu perfil de viajero. Cada una de las diecisiete estructuras se puntúa por proximidad a esa descripción, y los mejores resultados se muestran con su banda de ajuste.",
            "El resultado es un prior estructural, no un veredicto: indica qué arquitecturas de viaje coinciden con tus restricciones antes de aplicar el contexto de destino. Ninguna estructura es universalmente mejor, y el diagnóstico siempre declara lo que cada opción sacrifica.",
        ],
        "form_heading": "Siete preguntas",
        "noscript_note": "Esta herramienta funciona en el navegador y requiere JavaScript. Las diecisiete estructuras que diagnostica pueden leerse sin él en la página de la ontología.",
        "submit_label": "Ejecutar el diagnóstico",
        "reset_label": "Restablecer",
        "results_title": "Tu diagnóstico de ajuste estructural",
        "matched_label": "Alineado con tus respuestas:",
        "traded_label": "Lo que esta opción sacrifica:",
        "citation_label": "Citar como",
        "priors_note": "Estas clasificaciones son priores estructurales según TDIS v1: contextualízalas con el destino y tus factores personales antes de comprometerte. No existe un ganador universal entre estructuras.",
        "incomplete_error": "Responde las siete preguntas antes de ejecutar el diagnóstico.",
        "standard_heading": "Qué gobierna esta herramienta",
        "standard_paragraph": "La Brújula implementa el Structure Fit Protocol y está sujeta al Travel Decision Integrity Standard: criterios explícitos, priores antes del contexto, sin precios fabricados, sin ganador universal.",
        "link_ontology": "Ontología de estructuras de viaje (TSO) v1",
        "link_standard": "Estándar de integridad (TDIS) v1",
        "link_methodology": "Metodología",
    },
    "de": {
        "lead": "Eine strukturelle Passungsdiagnose: Beantworten Sie sieben Fragen zu Beschränkungen und Absicht und erhalten Sie die Reisestrukturen, die wirklich passen — mit benannten Zielkonflikten.",
        "core_statement": "Der Kompass ist die erste veröffentlichte Implementierung des Structure Fit Protocol. Er läuft vollständig im Browser: kein Konto, kein Tracking, keine Datenübertragung.",
        "meta_description": "Der Reise-Entscheidungskompass diagnostiziert, welche der siebzehn Reisestrukturen zu Ihren Beschränkungen und Absichten passen — nach dem Structure Fit Protocol des Travel Decision Integrity Standard.",
        "how_heading": "Wie die Diagnose funktioniert",
        "how_paragraphs": [
            "Ihre Antworten beschreiben die Reise, die Sie wirklich wollen, entlang der sechs Strukturachsen der Ontologie plus Ihres Reiseprofils. Jede der siebzehn Strukturen wird nach ihrer Nähe zu dieser Beschreibung bewertet, und die besten Ergebnisse erscheinen mit ihrem Passungsband.",
            "Das Ergebnis ist ein struktureller Prior, kein Urteil: Es zeigt, welche Reisearchitekturen zu Ihren Beschränkungen passen, bevor der Zielkontext angewendet wird. Keine Struktur ist universell die beste, und die Diagnose benennt stets, was jede Option opfert.",
        ],
        "form_heading": "Sieben Fragen",
        "noscript_note": "Dieses Werkzeug läuft im Browser und benötigt JavaScript. Die siebzehn diagnostizierten Strukturen sind ohne JavaScript auf der Ontologie-Seite lesbar.",
        "submit_label": "Diagnose ausführen",
        "reset_label": "Zurücksetzen",
        "results_title": "Ihre strukturelle Passungsdiagnose",
        "matched_label": "Im Einklang mit Ihren Antworten:",
        "traded_label": "Was diese Wahl opfert:",
        "citation_label": "Zitieren als",
        "priors_note": "Diese Rangfolgen sind strukturelle Prioren nach TDIS v1: Kontextualisieren Sie sie mit Ziel- und persönlichen Faktoren, bevor Sie sich festlegen. Zwischen Strukturen gibt es keinen universellen Gewinner.",
        "incomplete_error": "Bitte beantworten Sie alle sieben Fragen, bevor Sie die Diagnose ausführen.",
        "standard_heading": "Was dieses Werkzeug regelt",
        "standard_paragraph": "Der Kompass implementiert das Structure Fit Protocol und ist an den Travel Decision Integrity Standard gebunden: explizite Kriterien, Prioren vor Kontext, keine erfundenen Preise, kein universeller Gewinner.",
        "link_ontology": "Ontologie der Reisestrukturen (TSO) v1",
        "link_standard": "Integritätsstandard (TDIS) v1",
        "link_methodology": "Methodik",
    },
    "zh": {
        "lead": "结构适配诊断：回答关于约束与意图的七个问题，获得真正适合你的旅行结构——并明确说明取舍。",
        "core_statement": "指南针是结构适配协议的首个已发布实现。它完全在你的浏览器中运行：无账户、无跟踪、不发送任何数据。",
        "meta_description": "旅行决策指南针依据旅行决策完整性标准中的结构适配协议，诊断十七种旅行结构中哪些符合你的约束与意图。",
        "how_heading": "诊断如何进行",
        "how_paragraphs": [
            "你的回答沿本体的六个结构轴加上旅行者画像，描述你真正想要的旅行。十七种旅行结构逐一按与该描述的接近程度打分，并连同适配区间返回最佳结果。",
            "结果是结构性先验，不是结论：它告诉你在应用目的地情境之前，哪些旅行架构与你的约束匹配。没有任何结构对所有人最优，诊断始终说明每个选项所放弃的东西。",
        ],
        "form_heading": "七个问题",
        "noscript_note": "此工具在浏览器中运行，需要 JavaScript。它所诊断的十七种结构可在本体页面上直接阅读。",
        "submit_label": "运行诊断",
        "reset_label": "重置",
        "results_title": "你的结构适配诊断",
        "matched_label": "与你的回答一致：",
        "traded_label": "此选择放弃了什么：",
        "citation_label": "引用格式",
        "priors_note": "这些排名是 TDIS v1 下的结构性先验：在做出承诺前，请结合目的地与个人因素加以情境化。结构之间不存在普适的赢家。",
        "incomplete_error": "请先回答全部七个问题，再运行诊断。",
        "standard_heading": "本工具受何治理",
        "standard_paragraph": "指南针实现结构适配协议，并受旅行决策完整性标准约束：显式标准、先验先于情境、不编造价格、不设普适赢家。",
        "link_ontology": "旅行结构本体（TSO）v1",
        "link_standard": "完整性标准（TDIS）v1",
        "link_methodology": "方法论",
    },
    "ja": {
        "lead": "構造適合診断：制約と意図に関する7つの質問に答えると、本当に合う旅行構造が——トレードオフの明示とともに——提示される。",
        "core_statement": "コンパスは構造適合プロトコルの最初の公開実装である。すべてブラウザ内で動作する：アカウント不要、トラッキングなし、データ送信なし。",
        "meta_description": "トラベル・ディシジョン・コンパスは、旅行意思決定インテグリティ基準の構造適合プロトコルに基づき、17の旅行構造のうちどれがあなたの制約と意図に適合するかを診断する。",
        "how_heading": "診断の仕組み",
        "how_paragraphs": [
            "あなたの回答は、オントロジーの6つの構造軸と旅行者プロファイルに沿って、本当に望む旅を記述する。17の旅行構造それぞれがその記述への近さで採点され、上位の結果が適合バンドとともに返される。",
            "結果は構造的な事前値であり、評決ではない。目的地の文脈を適用する前に、どの旅行アーキテクチャがあなたの制約に合うかを示すものだ。普遍的に最良の構造は存在せず、診断は各選択肢が何を犠牲にするかを常に明示する。",
        ],
        "form_heading": "7つの質問",
        "noscript_note": "このツールはブラウザで動作し、JavaScript を必要とする。診断対象の17構造は、オントロジーのページでそのまま読むことができる。",
        "submit_label": "診断を実行",
        "reset_label": "リセット",
        "results_title": "あなたの構造適合診断",
        "matched_label": "回答と一致：",
        "traded_label": "この選択が犠牲にするもの：",
        "citation_label": "引用形式",
        "priors_note": "この順位は TDIS v1 における構造的事前値である。確定する前に、目的地や個人的要因とあわせて文脈化すること。構造間に普遍的な勝者は存在しない。",
        "incomplete_error": "診断を実行する前に、7つの質問すべてに回答してください。",
        "standard_heading": "このツールを統治するもの",
        "standard_paragraph": "コンパスは構造適合プロトコルを実装し、旅行意思決定インテグリティ基準に拘束される：明示的な基準、文脈より先の事前値、価格の捏造なし、普遍的勝者なし。",
        "link_ontology": "旅行構造オントロジー（TSO）v1",
        "link_standard": "インテグリティ基準（TDIS）v1",
        "link_methodology": "方法論",
    },
}

AXIS_QUESTION_ORDER = (
    "structure_intensity",
    "autonomy_level",
    "support_level",
    "pace_profile",
    "immersion_profile",
    "predictability_profile",
)

AXIS_OPTION_ORDER = {
    "structure_intensity": ("high", "medium", "low"),
    "autonomy_level": ("high", "medium", "low"),
    "support_level": ("high", "medium", "low"),
    "pace_profile": ("fixed", "balanced", "flexible"),
    "immersion_profile": ("surface", "balanced", "deep"),
    "predictability_profile": ("high", "medium", "low"),
}


# ============================================================================
# Engine configuration from tools_config (source of truth)
# ============================================================================

def _load_engine_settings() -> Dict[str, Any]:
    raw = load_yaml("tools_config.yaml")
    if not isinstance(raw, Mapping):
        raise GenerateCompassError("tools_config.yaml must be a mapping.")
    tools = raw.get("tools")
    if not isinstance(tools, list):
        raise GenerateCompassError("tools_config.tools must be a list.")

    tool = next((item for item in tools if isinstance(item, Mapping) and item.get("id") == TOOL_ID), None)
    if tool is None:
        raise GenerateCompassError(f"Tool {TOOL_ID!r} not found in tools_config.")

    evaluation = tool.get("evaluation_model")
    if not isinstance(evaluation, Mapping):
        raise GenerateCompassError(f"{TOOL_ID}.evaluation_model must be a mapping.")

    raw_bands = evaluation.get("score_bands")
    if not isinstance(raw_bands, list) or not raw_bands:
        raise GenerateCompassError(f"{TOOL_ID}.evaluation_model.score_bands must be a non-empty list.")

    bands: List[Dict[str, Any]] = []
    for idx, raw in enumerate(raw_bands):
        if not isinstance(raw, Mapping):
            raise GenerateCompassError(f"score_bands[{idx}] must be a mapping.")
        key = raw.get("key")
        if key not in BAND_LABELS:
            raise GenerateCompassError(f"score_bands[{idx}].key {key!r} has no localized label.")
        bands.append({"key": key, "min": int(raw["min"]), "max": int(raw["max"])})

    ranking = evaluation.get("ranking")
    max_results = 3
    if isinstance(ranking, Mapping) and isinstance(ranking.get("max_results"), int):
        max_results = ranking["max_results"]

    name = tool.get("name")
    if not isinstance(name, Mapping):
        raise GenerateCompassError(f"{TOOL_ID}.name must be a multilingual mapping.")

    return {"bands": bands, "max_results": max_results, "name": dict(name)}


# ============================================================================
# Rendering plumbing (same contract as the reference-page generators)
# ============================================================================

def _ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GenerateCompassError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise GenerateCompassError(f"{label} must not be empty.")
    return text


def _get_nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


def _extract_enabled_languages(site_config: Mapping[str, Any]) -> List[str]:
    raw = site_config.get("languages")
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
    languages = site_config.get("languages")
    if isinstance(languages, list):
        for item in languages:
            if isinstance(item, Mapping) and item.get("code") == lang and item.get("dir") in {"rtl", "ltr"}:
                return str(item["dir"])
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
        raise GenerateCompassError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise GenerateCompassError(f"{label} escapes static directory: {path}") from exc
    if not asset_path.is_file():
        raise GenerateCompassError(f"Missing static asset for {label}: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo_path"), "/static/img/brand/logo-icon.webp")
    return _ensure_string(logo, "branding.logo_path")


def _resolve_manifest_url() -> str:
    candidate = ROOT_DIR / "static" / "site.webmanifest"
    return "/static/site.webmanifest" if candidate.is_file() else ""


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise GenerateCompassError(f"Missing templates directory: {TEMPLATES_DIR}")
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
        raise GenerateCompassError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GenerateCompassError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GenerateCompassError(f"Refusing symlink output directory: {resolved}")
    return resolved


def _compass_path(lang: str) -> str:
    return f"/{lang}/tools/{TOOL_SLUG}/"


def _build_urls_by_lang(site_config: Mapping[str, Any], languages: Sequence[str]) -> Dict[str, str]:
    site = site_config.get("site")
    if not isinstance(site, Mapping):
        raise GenerateCompassError("site_config.site must be a mapping.")
    base = _ensure_string(site.get("base_url", "https://tourvstravel.com"), "site.base_url").rstrip("/")
    return {code: f"{base}{_compass_path(code)}" for code in languages}


def _build_questions(lang: str) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    for axis_id in AXIS_QUESTION_ORDER:
        questions.append({
            "id": axis_id,
            "text": QUESTION_TEXT[axis_id][lang],
            "options": [
                {"value": value, "text": AXIS_OPTION_TEXT[axis_id][value][lang]}
                for value in AXIS_OPTION_ORDER[axis_id]
            ],
        })
    questions.append({
        "id": "traveler_profile",
        "text": QUESTION_TEXT["traveler_profile"][lang],
        "options": [
            {"value": key, "text": PROFILE_OPTION_TEXT[key][lang]}
            for key in PROFILE_ORDER
        ],
    })
    return questions


def _build_compass_config(
    site_config: Mapping[str, Any],
    lang: str,
    structures: Sequence[Mapping[str, Any]],
    engine: Mapping[str, Any],
) -> Dict[str, Any]:
    localized_structures: List[Dict[str, Any]] = []
    for structure in structures:
        affinity = structure.get("profile_affinity")
        if not isinstance(affinity, Mapping):
            raise GenerateCompassError(f"Structure {structure['id']!r} is missing profile_affinity.")
        for profile_key in PROFILE_ORDER:
            if profile_key not in affinity:
                raise GenerateCompassError(
                    f"Structure {structure['id']!r} is missing profile_affinity[{profile_key!r}]."
                )
        localized_structures.append({
            "order": structure["order"],
            "label": structure["label"][lang],
            "summary": structure["summary"][lang],
            "citation": structure["citation"],
            "url": build_experience_type_path(site_config, lang, structure["slug"], absolute=False),
            "structural_axes": dict(structure["structural_axes"]),
            "profile_affinity": {key: affinity[key] for key in PROFILE_ORDER},
        })

    copy = PAGE_COPY[lang]
    return {
        "structures": localized_structures,
        "max_results": engine["max_results"],
        "score_bands": [
            {**band, "label": BAND_LABELS[band["key"]][lang]} for band in engine["bands"]
        ],
        "axis_names": {axis_id: AXIS_COPY[axis_id]["name"][lang] for axis_id in AXIS_ORDER},
        "value_labels": {value: labels[lang] for value, labels in VALUE_LABELS.items()},
        "copy": {
            "results_title": copy["results_title"],
            "matched_label": copy["matched_label"],
            "traded_label": copy["traded_label"],
            "citation_label": copy["citation_label"],
            "priors_note": copy["priors_note"],
            "incomplete_error": copy["incomplete_error"],
        },
    }


def _build_context(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
    structures: Sequence[Mapping[str, Any]],
    engine: Mapping[str, Any],
) -> Dict[str, Any]:
    copy = dict(PAGE_COPY[lang])
    copy["title"] = _ensure_string(engine["name"].get(lang), f"tools_config.{TOOL_ID}.name.{lang}")
    copy["questions"] = _build_questions(lang)

    site = site_config.get("site")
    if not isinstance(site, Mapping):
        raise GenerateCompassError("site_config.site must be a mapping.")
    base_url = _ensure_string(site.get("base_url", "https://tourvstravel.com"), "site.base_url").rstrip("/")
    site_name = _extract_site_name(site_config, lang)
    logo_url = _resolve_logo_path(site_config)
    canonical_url = f"{base_url}{_compass_path(lang)}"
    title = f"{copy['title']} | {site_name}"
    description = copy["meta_description"]
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
    compass_js_url = _require_existing_asset(COMPASS_JS_PATH, "compass_js_url")

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
        "compass_config": _build_compass_config(site_config, lang, structures, engine),
        "canonical_url": canonical_url,
        "seo": seo_payload,
        "hreflang": seo_payload.get("hreflang", []),
        "meta_desc": seo_payload.get("description", ""),
        "robots_directive": seo_payload.get("robots_directive", "index, follow"),
        "body_class": "page-travel-decision-compass",
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
        "page_js_assets": [{"src": compass_js_url}],
        "active_nav": "tools",
        "nav_report_label": resolve_nav_report_label(site_config, lang),
        "footer_reference_report_label": resolve_footer_reference_report_label(site_config, lang),
        "footer_note": "",
        "url_home": build_home_path(site_config, lang, absolute=False),
        "url_methodology": build_methodology_path(site_config, lang, absolute=False),
        "url_report": build_reference_report_path(site_config, lang, absolute=False),
        "url_compare_index": build_compare_index_path(site_config, lang, absolute=False),
        "url_tools_index": build_tools_index_path(site_config, lang, absolute=False),
        "url_destinations_index": build_destinations_index_path(site_config, lang, absolute=False),
        "url_about": build_about_path(site_config, lang, absolute=False),
        "url_privacy": build_privacy_path(site_config, lang, absolute=False),
        "url_acquire": build_acquire_path(site_config, lang, absolute=False),
        "url_contact": build_contact_path(site_config, lang, absolute=False),
        "url_source_policy": build_source_policy_path(site_config, lang, absolute=False),
        "url_editorial_standards": build_editorial_standards_path(site_config, lang, absolute=False),
        "url_travel_decision_architecture": build_travel_decision_architecture_path(site_config, lang, absolute=False),
        "url_ontology": build_ontology_path(site_config, lang, absolute=False),
        "url_standard": build_standard_path(site_config, lang, absolute=False),
        "url_changelog": build_changelog_path(site_config, lang, absolute=False),
    }
    context.update(localized_ui_context(lang))
    return context


def render_compass_page(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
    structures: Sequence[Mapping[str, Any]],
    engine: Mapping[str, Any],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise GenerateCompassError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc
    context = _build_context(
        site_config=site_config,
        lang=lang,
        languages=languages,
        structures=structures,
        engine=engine,
    )
    try:
        html_out = template.render(**context)
    except TemplateError as exc:
        raise GenerateCompassError(f"Unable to render compass page [{lang}]: {exc}") from exc
    if not html_out.strip():
        raise GenerateCompassError(f"Rendered compass page is empty for language {lang!r}.")
    return html_out


def generate_compass_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise GenerateCompassError("load_site_config() must return a mapping/object.")

    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise GenerateCompassError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise GenerateCompassError("No enabled languages available for compass generation.")

    try:
        structures = load_ontology_structures()
    except GenerateCategoryInfrastructureError as exc:
        raise GenerateCompassError(f"Ontology loading failed: {exc}") from exc
    engine = _load_engine_settings()

    written: List[Path] = []
    for lang in languages:
        html_output = render_compass_page(
            site_config=site_config,
            lang=lang,
            languages=languages,
            structures=structures,
            engine=engine,
        )
        output_path = safe_output_dir / lang / "tools" / TOOL_SLUG / "index.html"
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated compass page [%s] -> %s", lang, output_path)
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the TourVsTravel Travel Decision Compass pages.")
    parser.add_argument("--lang", type=str, default=None, help="Generate one language only.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    try:
        generate_compass_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateCompassError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected compass generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
