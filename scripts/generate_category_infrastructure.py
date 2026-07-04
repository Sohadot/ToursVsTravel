#!/usr/bin/env python3
"""
TourVsTravel - Category infrastructure pages
============================================
Generates the named category-infrastructure reference pages:

  output/{lang}/ontology/index.html    Travel Structure Ontology (TSO) v1
  output/{lang}/standard/index.html    Travel Decision Integrity Standard (TDIS) v1
                                       (includes the Structure Fit Protocol)
  output/{lang}/changelog/index.html   Public append-only changelog

Governance:
- These pages render the canonical datasets (experience_types.yaml,
  comparison_criteria.yaml, changelog.yaml). They present the source of
  truth; they do not paraphrase it.
- Copy is fully localized in all seven languages. English fallback in
  localized pages is a build defect (enforced by build.py).
- TDIS rules and SFP steps are defined once here and consumed by both the
  HTML pages and the machine layer (generate_machine_layer.py), so human
  pages and JSON endpoints cannot drift apart.
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
    load_comparison_criteria,
    load_experience_types,
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

log = logging.getLogger("generate_category_infrastructure")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

TSO_VERSION = "1.0.0"
TDIS_VERSION = "1.0.0"

PAGE_TEMPLATES = {
    "ontology": "pages/ontology.html",
    "standard": "pages/standard.html",
    "changelog": "pages/changelog.html",
}

PAGE_OUTPUT_DIRS = {
    "ontology": "ontology",
    "standard": "standard",
    "changelog": "changelog",
}


class GenerateCategoryInfrastructureError(Exception):
    pass


# ============================================================================
# TDIS rules and SFP steps — single source for HTML pages AND machine layer
# ============================================================================

TDIS_RULES: List[Dict[str, Any]] = [
    {
        "id": "classify-first",
        "text": {
            "en": "Both options are identified as travel structures from the ontology, not moods or marketing labels.",
            "ar": "يُحدَّد كلا الخيارين كبنيتي سفر من الأنطولوجيا، لا كمزاج أو تسميات تسويقية.",
            "fr": "Les deux options sont identifiées comme des structures de voyage issues de l'ontologie, non comme des humeurs ou des étiquettes marketing.",
            "es": "Ambas opciones se identifican como estructuras de viaje de la ontología, no como estados de ánimo ni etiquetas de marketing.",
            "de": "Beide Optionen werden als Reisestrukturen aus der Ontologie identifiziert, nicht als Stimmungen oder Marketing-Etiketten.",
            "zh": "两个选项都必须被识别为本体中的旅行结构，而不是情绪或营销标签。",
            "ja": "両方の選択肢は、気分やマーケティング上のラベルではなく、オントロジーの旅行構造として識別される。",
        },
    },
    {
        "id": "explicit-criteria",
        "text": {
            "en": "Comparison runs over explicit criteria with declared scales, never vague editorial preference.",
            "ar": "تجري المقارنة عبر معايير صريحة بمقاييس معلنة، لا عبر تفضيل تحريري غامض أبدًا.",
            "fr": "La comparaison s'appuie sur des critères explicites aux échelles déclarées, jamais sur une préférence éditoriale vague.",
            "es": "La comparación se realiza sobre criterios explícitos con escalas declaradas, nunca sobre una preferencia editorial vaga.",
            "de": "Der Vergleich läuft über explizite Kriterien mit deklarierten Skalen, niemals über vage redaktionelle Vorlieben.",
            "zh": "比较必须基于具有明确刻度的显式标准，绝不依赖模糊的编辑偏好。",
            "ja": "比較は宣言された尺度を持つ明示的な基準で行い、曖昧な編集的好みには決して依拠しない。",
        },
    },
    {
        "id": "priors-context",
        "text": {
            "en": "Baseline scores are treated as structural priors and are contextualized before any recommendation.",
            "ar": "تُعامل الدرجات الأساسية كافتراضات بنيوية مسبقة، وتوضع في سياقها قبل أي توصية.",
            "fr": "Les scores de référence sont traités comme des a priori structurels et sont contextualisés avant toute recommandation.",
            "es": "Las puntuaciones de base se tratan como priores estructurales y se contextualizan antes de cualquier recomendación.",
            "de": "Basiswerte werden als strukturelle Prioren behandelt und vor jeder Empfehlung kontextualisiert.",
            "zh": "基线分数被视为结构性先验，在给出任何建议之前必须结合具体情境。",
            "ja": "ベースラインスコアは構造的な事前値として扱い、いかなる推奨の前にも文脈化する。",
        },
    },
    {
        "id": "cost-bands",
        "text": {
            "en": "Cost statements are bands and structures; live prices are never fabricated.",
            "ar": "بيانات التكلفة نطاقات وبنى؛ ولا تُختلق أسعار حية أبدًا.",
            "fr": "Les indications de coût sont des fourchettes et des structures ; aucun prix en direct n'est jamais fabriqué.",
            "es": "Las indicaciones de coste son rangos y estructuras; nunca se fabrican precios en vivo.",
            "de": "Kostenangaben sind Bänder und Strukturen; Live-Preise werden niemals erfunden.",
            "zh": "成本表述使用区间和结构；绝不编造实时价格。",
            "ja": "費用の記述は帯域と構造で示し、ライブ価格を決して捏造しない。",
        },
    },
    {
        "id": "evidence-declared",
        "text": {
            "en": "Sources are identifiable, and missing evidence is declared rather than hidden.",
            "ar": "المصادر قابلة للتحديد، وغياب الدليل يُعلَن ولا يُخفى.",
            "fr": "Les sources sont identifiables, et l'absence de preuve est déclarée plutôt que dissimulée.",
            "es": "Las fuentes son identificables, y la falta de evidencia se declara en lugar de ocultarse.",
            "de": "Quellen sind identifizierbar, und fehlende Belege werden erklärt statt verborgen.",
            "zh": "来源必须可识别，缺少证据时应当声明而非隐藏。",
            "ja": "情報源は識別可能であり、証拠の欠如は隠さずに明示する。",
        },
    },
    {
        "id": "fit-first",
        "text": {
            "en": "Fit precedes preference; tradeoffs are stated before aspirations.",
            "ar": "الملاءمة تسبق التفضيل؛ وتُذكر المفاضلات قبل الطموحات.",
            "fr": "L'adéquation précède la préférence ; les compromis sont énoncés avant les aspirations.",
            "es": "El ajuste precede a la preferencia; las contrapartidas se enuncian antes que las aspiraciones.",
            "de": "Passung geht vor Vorliebe; Zielkonflikte werden vor Wünschen benannt.",
            "zh": "适配先于偏好；先说明取舍，再谈愿景。",
            "ja": "適合が好みに先立つ。願望より先にトレードオフを明示する。",
        },
    },
    {
        "id": "no-universal-winner",
        "text": {
            "en": "No universal winner is declared between structures.",
            "ar": "لا يُعلَن فائز مطلق بين البنى.",
            "fr": "Aucun vainqueur universel n'est déclaré entre les structures.",
            "es": "No se declara un ganador universal entre estructuras.",
            "de": "Zwischen Strukturen wird kein universeller Gewinner erklärt.",
            "zh": "不在结构之间宣布普适的赢家。",
            "ja": "構造間で普遍的な勝者を宣言しない。",
        },
    },
]

SFP_STEPS: List[Dict[str, Any]] = [
    {
        "id": "classify",
        "text": {
            "en": "Classify the candidate options into ontology structures.",
            "ar": "صنّف الخيارات المرشحة إلى بنى من الأنطولوجيا.",
            "fr": "Classer les options candidates dans les structures de l'ontologie.",
            "es": "Clasificar las opciones candidatas en estructuras de la ontología.",
            "de": "Die Kandidatenoptionen in Ontologie-Strukturen einordnen.",
            "zh": "将候选选项归类到本体结构中。",
            "ja": "候補となる選択肢をオントロジーの構造に分類する。",
        },
    },
    {
        "id": "score-fit",
        "text": {
            "en": "Score fit across the six structural axes for the declared traveler constraints.",
            "ar": "قيّم الملاءمة عبر المحاور البنيوية الستة وفق قيود المسافر المعلنة.",
            "fr": "Évaluer l'adéquation sur les six axes structurels selon les contraintes déclarées du voyageur.",
            "es": "Puntuar el ajuste en los seis ejes estructurales según las restricciones declaradas del viajero.",
            "de": "Die Passung entlang der sechs Strukturachsen für die erklärten Reisebeschränkungen bewerten.",
            "zh": "根据旅行者声明的约束条件，在六个结构轴上评估适配度。",
            "ja": "宣言された旅行者の制約に対し、6つの構造軸で適合度を採点する。",
        },
    },
    {
        "id": "apply-standard",
        "text": {
            "en": "Apply the standard: contextualize priors, keep costs in bands, declare uncertainty.",
            "ar": "طبّق المعيار: ضع الافتراضات المسبقة في سياقها، وأبقِ التكاليف في نطاقات، وأعلن عدم اليقين.",
            "fr": "Appliquer le standard : contextualiser les a priori, garder les coûts en fourchettes, déclarer l'incertitude.",
            "es": "Aplicar el estándar: contextualizar los priores, mantener los costes en rangos, declarar la incertidumbre.",
            "de": "Den Standard anwenden: Prioren kontextualisieren, Kosten in Bändern halten, Unsicherheit erklären.",
            "zh": "应用标准：将先验置于情境中，成本保持区间表述，声明不确定性。",
            "ja": "基準を適用する：事前値を文脈化し、費用は帯域で示し、不確実性を明示する。",
        },
    },
    {
        "id": "emit-diagnosis",
        "text": {
            "en": "Emit a diagnosis: ranked fit, explicit tradeoffs, and what each choice costs the traveler, linked back to the class pages used.",
            "ar": "أصدر تشخيصًا: ترتيب الملاءمة، والمفاضلات الصريحة، وما يكلفه كل خيار للمسافر، مع روابط إلى صفحات البنى المستخدمة.",
            "fr": "Émettre un diagnostic : adéquation classée, compromis explicites et coût de chaque choix pour le voyageur, avec liens vers les pages de classes utilisées.",
            "es": "Emitir un diagnóstico: ajuste ordenado, contrapartidas explícitas y lo que cada elección cuesta al viajero, con enlaces a las páginas de clase utilizadas.",
            "de": "Eine Diagnose ausgeben: geordnete Passung, explizite Zielkonflikte und was jede Wahl den Reisenden kostet, verlinkt auf die verwendeten Klassenseiten.",
            "zh": "输出诊断：适配度排序、明确的取舍，以及每个选择让旅行者付出的代价，并链接回所使用的结构页面。",
            "ja": "診断を出力する：適合度の順位、明示的なトレードオフ、各選択が旅行者に何を犠牲にさせるかを、使用した構造ページへのリンクとともに示す。",
        },
    },
]

AXIS_ORDER = (
    "structure_intensity",
    "autonomy_level",
    "support_level",
    "pace_profile",
    "immersion_profile",
    "predictability_profile",
)

AXIS_COPY: Dict[str, Dict[str, Dict[str, str]]] = {
    "structure_intensity": {
        "name": {
            "en": "Structure intensity", "ar": "كثافة البنية", "fr": "Intensité de structure",
            "es": "Intensidad de estructura", "de": "Strukturintensität", "zh": "结构强度", "ja": "構造強度",
        },
        "definition": {
            "en": "How much of the trip is fixed in advance.",
            "ar": "مقدار ما يُثبَّت من الرحلة مسبقًا.",
            "fr": "Quelle part du voyage est fixée à l'avance.",
            "es": "Qué parte del viaje queda fijada de antemano.",
            "de": "Wie viel der Reise im Voraus festgelegt ist.",
            "zh": "行程有多少在出发前就已固定。",
            "ja": "旅程のどれだけが事前に固定されているか。",
        },
    },
    "autonomy_level": {
        "name": {
            "en": "Autonomy level", "ar": "مستوى الاستقلالية", "fr": "Niveau d'autonomie",
            "es": "Nivel de autonomía", "de": "Autonomiegrad", "zh": "自主程度", "ja": "自律性レベル",
        },
        "definition": {
            "en": "How much control the traveler keeps over decisions en route.",
            "ar": "مقدار التحكم الذي يحتفظ به المسافر في القرارات أثناء الطريق.",
            "fr": "Quel contrôle le voyageur conserve sur les décisions en cours de route.",
            "es": "Cuánto control conserva el viajero sobre las decisiones durante el trayecto.",
            "de": "Wie viel Kontrolle Reisende unterwegs über Entscheidungen behalten.",
            "zh": "旅行者在途中对决策保留多少控制权。",
            "ja": "旅行者が道中の意思決定にどれだけの裁量を保つか。",
        },
    },
    "support_level": {
        "name": {
            "en": "Support level", "ar": "مستوى الدعم", "fr": "Niveau de soutien",
            "es": "Nivel de apoyo", "de": "Unterstützungsgrad", "zh": "支持程度", "ja": "サポートレベル",
        },
        "definition": {
            "en": "How much operational help is built into the format.",
            "ar": "مقدار المساعدة التشغيلية المدمجة في الصيغة.",
            "fr": "Quelle aide opérationnelle est intégrée au format.",
            "es": "Cuánta ayuda operativa incorpora el formato.",
            "de": "Wie viel operative Hilfe im Format eingebaut ist.",
            "zh": "该形式内置了多少操作层面的协助。",
            "ja": "その形式にどれだけの運用サポートが組み込まれているか。",
        },
    },
    "pace_profile": {
        "name": {
            "en": "Pace profile", "ar": "نمط الإيقاع", "fr": "Profil de rythme",
            "es": "Perfil de ritmo", "de": "Tempoprofil", "zh": "节奏特征", "ja": "ペースプロファイル",
        },
        "definition": {
            "en": "Whether time on the trip is fixed, balanced, or flexible.",
            "ar": "هل الوقت في الرحلة ثابت أم متوازن أم مرن.",
            "fr": "Si le temps du voyage est fixe, équilibré ou flexible.",
            "es": "Si el tiempo del viaje es fijo, equilibrado o flexible.",
            "de": "Ob die Zeit auf der Reise fest, ausgewogen oder flexibel ist.",
            "zh": "旅行中的时间是固定、均衡还是灵活。",
            "ja": "旅の時間が固定的か、均衡的か、柔軟か。",
        },
    },
    "immersion_profile": {
        "name": {
            "en": "Immersion profile", "ar": "نمط الانغماس", "fr": "Profil d'immersion",
            "es": "Perfil de inmersión", "de": "Immersionsprofil", "zh": "沉浸特征", "ja": "没入プロファイル",
        },
        "definition": {
            "en": "Whether contact with place tends to be surface, balanced, or deep.",
            "ar": "هل يميل الاتصال بالمكان إلى السطحية أم التوازن أم العمق.",
            "fr": "Si le contact avec le lieu tend à être superficiel, équilibré ou profond.",
            "es": "Si el contacto con el lugar tiende a ser superficial, equilibrado o profundo.",
            "de": "Ob der Kontakt zum Ort eher oberflächlich, ausgewogen oder tief ist.",
            "zh": "与地方的接触倾向于表层、均衡还是深入。",
            "ja": "場所との接触が表層的か、均衡的か、深いか。",
        },
    },
    "predictability_profile": {
        "name": {
            "en": "Predictability profile", "ar": "نمط القابلية للتنبؤ", "fr": "Profil de prévisibilité",
            "es": "Perfil de previsibilidad", "de": "Vorhersagbarkeitsprofil", "zh": "可预测性特征", "ja": "予測可能性プロファイル",
        },
        "definition": {
            "en": "How much uncertainty the format absorbs before it reaches the traveler.",
            "ar": "مقدار عدم اليقين الذي تمتصه الصيغة قبل أن يصل إلى المسافر.",
            "fr": "Quelle part d'incertitude le format absorbe avant qu'elle n'atteigne le voyageur.",
            "es": "Cuánta incertidumbre absorbe el formato antes de que llegue al viajero.",
            "de": "Wie viel Unsicherheit das Format abfängt, bevor sie Reisende erreicht.",
            "zh": "该形式在不确定性触及旅行者之前吸收了多少。",
            "ja": "不確実性が旅行者に届く前に、その形式がどれだけ吸収するか。",
        },
    },
}


# ============================================================================
# Localized page copy
# ============================================================================

ONTOLOGY_COPY: Dict[str, Dict[str, Any]] = {
    "en": {
        "title": "Travel Structure Ontology (TSO) v1",
        "lead": "The canonical classification of the seventeen travel structures used across the TourVsTravel reference system.",
        "core_statement": "A travel structure is a decision structure with stable operational meaning, not a marketing label. This ontology defines the classes, the axes they are measured on, and the rules that keep both stable.",
        "meta_description": "The Travel Structure Ontology (TSO) v1 is the canonical, versioned classification of the seventeen travel structures used across TourVsTravel, with six declared structural axes and machine-readable access.",
        "sections": [
            {"heading": "What this ontology is", "paragraphs": [
                "The Travel Structure Ontology defines the seventeen structures TourVsTravel uses to classify how a trip is built. Every comparison page, decision tool, and reference document in the system resolves to these classes. The ontology is the system's source of truth: pages implement it, they do not reinterpret it.",
                "Each class is defined by what it is, what it is not, and how it behaves under the system's comparison criteria. Classes carry stable identifiers that never change meaning.",
            ]},
            {"heading": "How to read baseline scores", "paragraphs": [
                "Baseline scores are structural priors, not verdicts. They describe how a structure tends to behave before destination and traveler context are applied. Every published comparison must contextualize them; the ontology forbids treating a prior as a universal answer.",
            ]},
            {"heading": "Versioning and citation", "paragraphs": [
                "The ontology is append-only. Classes and axes are never silently renamed or deleted; every substantive change is versioned and recorded in the public changelog. Cite a class as: TSO v1 / guided-group-tour.",
            ]},
            {"heading": "Machine-readable access", "paragraphs": [
                "The complete ontology is published as a versioned JSON artifact at /ontology/tso-v1.json, and each class at /api/structures/{slug}.json. The machine layer mirrors these pages one to one: agents and humans read the same truth.",
            ]},
        ],
        "axes_heading": "The six structural axes",
        "axes_intro": "Every structure is profiled on six axes with declared scales. The axes are the coordinate system of the category: they make two forms of travel comparable without reducing them to preference.",
        "structures_heading": "The seventeen structures",
        "structures_intro": "Each class links to its full reference page. Labels and definitions below are rendered directly from the ontology dataset: this page renders the source of truth, it does not paraphrase it.",
        "citation_label": "Cite as",
    },
    "ar": {
        "title": "أنطولوجيا بنى السفر (TSO) — الإصدار الأول",
        "lead": "التصنيف القانوني للبنى السبع عشرة للسفر المستخدمة في نظام TourVsTravel المرجعي كله.",
        "core_statement": "بنية السفر هي بنية قرار ذات معنى تشغيلي ثابت، لا تسمية تسويقية. تعرّف هذه الأنطولوجيا الفئات والمحاور التي تُقاس عليها والقواعد التي تحفظ ثبات الاثنين معًا.",
        "meta_description": "أنطولوجيا بنى السفر (TSO) الإصدار الأول هي التصنيف القانوني المُصدَّر للبنى السبع عشرة للسفر المستخدمة في TourVsTravel، بستة محاور بنيوية معلنة ووصول مقروء آليًا.",
        "sections": [
            {"heading": "ما هذه الأنطولوجيا", "paragraphs": [
                "تعرّف أنطولوجيا بنى السفر البنى السبع عشرة التي يستخدمها TourVsTravel لتصنيف طريقة بناء الرحلة. كل صفحة مقارنة وكل أداة قرار وكل وثيقة مرجعية في النظام تعود إلى هذه الفئات. الأنطولوجيا هي مصدر الحقيقة في النظام: الصفحات تنفذها ولا تعيد تفسيرها.",
                "تُعرَّف كل فئة بما هي، وبما ليست، وبكيفية سلوكها وفق معايير المقارنة في النظام. وتحمل الفئات معرّفات ثابتة لا يتغير معناها أبدًا.",
            ]},
            {"heading": "كيف تُقرأ الدرجات الأساسية", "paragraphs": [
                "الدرجات الأساسية افتراضات بنيوية مسبقة وليست أحكامًا نهائية. إنها تصف كيف تميل البنية إلى السلوك قبل تطبيق سياق الوجهة والمسافر. يجب على كل مقارنة منشورة أن تضعها في سياقها؛ وتمنع الأنطولوجيا معاملة الافتراض المسبق كإجابة مطلقة.",
            ]},
            {"heading": "الإصدار والاستشهاد", "paragraphs": [
                "الأنطولوجيا لا تقبل إلا الإضافة. لا تُعاد تسمية الفئات والمحاور ولا تُحذف بصمت؛ فكل تغيير جوهري يُصدَّر ويُسجَّل في سجل التغييرات العلني. يُستشهد بالفئة هكذا: TSO v1 / guided-group-tour.",
            ]},
            {"heading": "الوصول المقروء آليًا", "paragraphs": [
                "تُنشر الأنطولوجيا كاملة كوثيقة JSON مُصدَّرة على المسار ‎/ontology/tso-v1.json، وكل فئة على ‎/api/structures/{slug}.json. طبقة الآلة مرآة لهذه الصفحات واحدًا لواحد: الوكلاء والبشر يقرؤون الحقيقة نفسها.",
            ]},
        ],
        "axes_heading": "المحاور البنيوية الستة",
        "axes_intro": "تُرسم سمات كل بنية على ستة محاور بمقاييس معلنة. المحاور هي نظام الإحداثيات للفئة: تجعل شكلين من السفر قابلين للمقارنة دون اختزالهما في التفضيل.",
        "structures_heading": "البنى السبع عشرة",
        "structures_intro": "كل فئة تصل إلى صفحتها المرجعية الكاملة. التسميات والتعريفات أدناه مأخوذة مباشرة من مجموعة بيانات الأنطولوجيا: هذه الصفحة تعرض مصدر الحقيقة ولا تعيد صياغته.",
        "citation_label": "الاستشهاد",
    },
    "fr": {
        "title": "Ontologie des structures de voyage (TSO) v1",
        "lead": "La classification canonique des dix-sept structures de voyage utilisées dans tout le système de référence TourVsTravel.",
        "core_statement": "Une structure de voyage est une structure de décision au sens opérationnel stable, non une étiquette marketing. Cette ontologie définit les classes, les axes sur lesquels elles sont mesurées et les règles qui maintiennent la stabilité des deux.",
        "meta_description": "L'ontologie des structures de voyage (TSO) v1 est la classification canonique et versionnée des dix-sept structures de voyage utilisées par TourVsTravel, avec six axes structurels déclarés et un accès lisible par machine.",
        "sections": [
            {"heading": "Ce qu'est cette ontologie", "paragraphs": [
                "L'ontologie des structures de voyage définit les dix-sept structures que TourVsTravel utilise pour classer la manière dont un voyage est construit. Chaque page de comparaison, outil de décision et document de référence du système renvoie à ces classes. L'ontologie est la source de vérité du système : les pages l'appliquent, elles ne la réinterprètent pas.",
                "Chaque classe est définie par ce qu'elle est, ce qu'elle n'est pas, et son comportement selon les critères de comparaison du système. Les classes portent des identifiants stables dont le sens ne change jamais.",
            ]},
            {"heading": "Comment lire les scores de référence", "paragraphs": [
                "Les scores de référence sont des a priori structurels, non des verdicts. Ils décrivent le comportement tendanciel d'une structure avant l'application du contexte de destination et de voyageur. Toute comparaison publiée doit les contextualiser ; l'ontologie interdit de traiter un a priori comme une réponse universelle.",
            ]},
            {"heading": "Versionnage et citation", "paragraphs": [
                "L'ontologie fonctionne en ajout seul. Les classes et les axes ne sont jamais renommés ni supprimés en silence ; tout changement substantiel est versionné et consigné dans le journal des modifications public. Citez une classe ainsi : TSO v1 / guided-group-tour.",
            ]},
            {"heading": "Accès lisible par machine", "paragraphs": [
                "L'ontologie complète est publiée comme artefact JSON versionné à /ontology/tso-v1.json, et chaque classe à /api/structures/{slug}.json. La couche machine reflète ces pages une pour une : agents et humains lisent la même vérité.",
            ]},
        ],
        "axes_heading": "Les six axes structurels",
        "axes_intro": "Chaque structure est profilée sur six axes aux échelles déclarées. Les axes sont le système de coordonnées de la catégorie : ils rendent deux formes de voyage comparables sans les réduire à une préférence.",
        "structures_heading": "Les dix-sept structures",
        "structures_intro": "Chaque classe renvoie à sa page de référence complète. Les libellés et définitions ci-dessous proviennent directement du jeu de données de l'ontologie : cette page rend la source de vérité, elle ne la paraphrase pas.",
        "citation_label": "Citer comme",
    },
    "es": {
        "title": "Ontología de estructuras de viaje (TSO) v1",
        "lead": "La clasificación canónica de las diecisiete estructuras de viaje utilizadas en todo el sistema de referencia TourVsTravel.",
        "core_statement": "Una estructura de viaje es una estructura de decisión con significado operativo estable, no una etiqueta de marketing. Esta ontología define las clases, los ejes sobre los que se miden y las reglas que mantienen estables ambas cosas.",
        "meta_description": "La ontología de estructuras de viaje (TSO) v1 es la clasificación canónica y versionada de las diecisiete estructuras de viaje utilizadas por TourVsTravel, con seis ejes estructurales declarados y acceso legible por máquina.",
        "sections": [
            {"heading": "Qué es esta ontología", "paragraphs": [
                "La ontología de estructuras de viaje define las diecisiete estructuras que TourVsTravel usa para clasificar cómo se construye un viaje. Cada página de comparación, herramienta de decisión y documento de referencia del sistema se resuelve en estas clases. La ontología es la fuente de verdad del sistema: las páginas la aplican, no la reinterpretan.",
                "Cada clase se define por lo que es, lo que no es y cómo se comporta bajo los criterios de comparación del sistema. Las clases llevan identificadores estables cuyo significado nunca cambia.",
            ]},
            {"heading": "Cómo leer las puntuaciones de base", "paragraphs": [
                "Las puntuaciones de base son priores estructurales, no veredictos. Describen cómo tiende a comportarse una estructura antes de aplicar el contexto de destino y de viajero. Toda comparación publicada debe contextualizarlas; la ontología prohíbe tratar un prior como respuesta universal.",
            ]},
            {"heading": "Versionado y cita", "paragraphs": [
                "La ontología es de solo adición. Las clases y los ejes nunca se renombran ni se eliminan en silencio; todo cambio sustancial se versiona y se registra en el registro de cambios público. Cite una clase así: TSO v1 / guided-group-tour.",
            ]},
            {"heading": "Acceso legible por máquina", "paragraphs": [
                "La ontología completa se publica como artefacto JSON versionado en /ontology/tso-v1.json, y cada clase en /api/structures/{slug}.json. La capa máquina refleja estas páginas una a una: agentes y humanos leen la misma verdad.",
            ]},
        ],
        "axes_heading": "Los seis ejes estructurales",
        "axes_intro": "Cada estructura se perfila en seis ejes con escalas declaradas. Los ejes son el sistema de coordenadas de la categoría: hacen comparables dos formas de viajar sin reducirlas a preferencia.",
        "structures_heading": "Las diecisiete estructuras",
        "structures_intro": "Cada clase enlaza a su página de referencia completa. Las etiquetas y definiciones siguientes se toman directamente del conjunto de datos de la ontología: esta página presenta la fuente de verdad, no la parafrasea.",
        "citation_label": "Citar como",
    },
    "de": {
        "title": "Ontologie der Reisestrukturen (TSO) v1",
        "lead": "Die kanonische Klassifikation der siebzehn Reisestrukturen, die im gesamten TourVsTravel-Referenzsystem verwendet werden.",
        "core_statement": "Eine Reisestruktur ist eine Entscheidungsstruktur mit stabiler operativer Bedeutung, kein Marketing-Etikett. Diese Ontologie definiert die Klassen, die Achsen, an denen sie gemessen werden, und die Regeln, die beides stabil halten.",
        "meta_description": "Die Ontologie der Reisestrukturen (TSO) v1 ist die kanonische, versionierte Klassifikation der siebzehn von TourVsTravel verwendeten Reisestrukturen, mit sechs deklarierten Strukturachsen und maschinenlesbarem Zugang.",
        "sections": [
            {"heading": "Was diese Ontologie ist", "paragraphs": [
                "Die Ontologie der Reisestrukturen definiert die siebzehn Strukturen, mit denen TourVsTravel klassifiziert, wie eine Reise gebaut ist. Jede Vergleichsseite, jedes Entscheidungswerkzeug und jedes Referenzdokument des Systems löst sich in diese Klassen auf. Die Ontologie ist die Quelle der Wahrheit des Systems: Seiten setzen sie um, sie deuten sie nicht neu.",
                "Jede Klasse ist definiert durch das, was sie ist, was sie nicht ist, und wie sie sich unter den Vergleichskriterien des Systems verhält. Klassen tragen stabile Kennungen, deren Bedeutung sich niemals ändert.",
            ]},
            {"heading": "Wie Basiswerte zu lesen sind", "paragraphs": [
                "Basiswerte sind strukturelle Prioren, keine Urteile. Sie beschreiben, wie sich eine Struktur tendenziell verhält, bevor Ziel- und Reisendenkontext angewendet werden. Jeder veröffentlichte Vergleich muss sie kontextualisieren; die Ontologie verbietet es, einen Prior als universelle Antwort zu behandeln.",
            ]},
            {"heading": "Versionierung und Zitation", "paragraphs": [
                "Die Ontologie ist append-only. Klassen und Achsen werden niemals stillschweigend umbenannt oder gelöscht; jede wesentliche Änderung wird versioniert und im öffentlichen Änderungsprotokoll festgehalten. Zitieren Sie eine Klasse so: TSO v1 / guided-group-tour.",
            ]},
            {"heading": "Maschinenlesbarer Zugang", "paragraphs": [
                "Die vollständige Ontologie wird als versioniertes JSON-Artefakt unter /ontology/tso-v1.json veröffentlicht, jede Klasse unter /api/structures/{slug}.json. Die Maschinenebene spiegelt diese Seiten eins zu eins: Agenten und Menschen lesen dieselbe Wahrheit.",
            ]},
        ],
        "axes_heading": "Die sechs Strukturachsen",
        "axes_intro": "Jede Struktur wird auf sechs Achsen mit deklarierten Skalen profiliert. Die Achsen sind das Koordinatensystem der Kategorie: Sie machen zwei Reiseformen vergleichbar, ohne sie auf Vorlieben zu reduzieren.",
        "structures_heading": "Die siebzehn Strukturen",
        "structures_intro": "Jede Klasse verlinkt auf ihre vollständige Referenzseite. Die folgenden Bezeichnungen und Definitionen stammen direkt aus dem Ontologie-Datensatz: Diese Seite rendert die Quelle der Wahrheit, sie paraphrasiert sie nicht.",
        "citation_label": "Zitieren als",
    },
    "zh": {
        "title": "旅行结构本体（TSO）v1",
        "lead": "TourVsTravel 参考系统全域使用的十七种旅行结构的规范分类。",
        "core_statement": "旅行结构是具有稳定操作含义的决策结构，而不是营销标签。本体定义了这些类别、衡量它们的轴，以及使两者保持稳定的规则。",
        "meta_description": "旅行结构本体（TSO）v1 是 TourVsTravel 使用的十七种旅行结构的规范化、版本化分类，具有六个明确声明的结构轴和机器可读访问。",
        "sections": [
            {"heading": "这个本体是什么", "paragraphs": [
                "旅行结构本体定义了 TourVsTravel 用于分类旅行构建方式的十七种结构。系统中的每个比较页面、决策工具和参考文档都归结到这些类别。本体是系统的事实源：页面执行它，而不是重新解释它。",
                "每个类别都由它是什么、不是什么，以及在系统比较标准下如何表现来定义。类别携带稳定的标识符，其含义永不改变。",
            ]},
            {"heading": "如何解读基线分数", "paragraphs": [
                "基线分数是结构性先验，不是结论。它们描述在应用目的地和旅行者情境之前，一种结构倾向于如何表现。每个公开发布的比较都必须将其置于情境中；本体禁止把先验当作普适答案。",
            ]},
            {"heading": "版本与引用", "paragraphs": [
                "本体只增不改。类别和轴永远不会被悄悄重命名或删除；每项实质性更改都会版本化并记录在公开更新日志中。引用类别的格式为：TSO v1 / guided-group-tour。",
            ]},
            {"heading": "机器可读访问", "paragraphs": [
                "完整本体作为版本化 JSON 工件发布于 /ontology/tso-v1.json，每个类别发布于 /api/structures/{slug}.json。机器层与这些页面一一对应：代理和人类读取同一事实。",
            ]},
        ],
        "axes_heading": "六个结构轴",
        "axes_intro": "每种结构都在六个具有明确刻度的轴上建立特征。这些轴是该类别的坐标系：它们使两种旅行形式可以比较，而不把比较简化为偏好。",
        "structures_heading": "十七种结构",
        "structures_intro": "每个类别都链接到其完整参考页面。以下标签与定义直接取自本体数据集：本页呈现事实源，而不是转述它。",
        "citation_label": "引用格式",
    },
    "ja": {
        "title": "旅行構造オントロジー（TSO）v1",
        "lead": "TourVsTravel リファレンスシステム全体で使用される17の旅行構造の正規分類。",
        "core_statement": "旅行構造とは、安定した運用上の意味を持つ意思決定構造であり、マーケティングのラベルではない。このオントロジーは、クラス、それらを測定する軸、そして両者を安定に保つ規則を定義する。",
        "meta_description": "旅行構造オントロジー（TSO）v1 は、TourVsTravel が使用する17の旅行構造の正規かつバージョン管理された分類であり、6つの宣言された構造軸と機械可読アクセスを備える。",
        "sections": [
            {"heading": "このオントロジーとは", "paragraphs": [
                "旅行構造オントロジーは、旅がどのように構築されるかを分類するために TourVsTravel が使用する17の構造を定義する。システム内のすべての比較ページ、意思決定ツール、参照文書はこれらのクラスに帰着する。オントロジーはシステムの真実の源であり、ページはそれを実装するのであって、再解釈するのではない。",
                "各クラスは、それが何であるか、何でないか、そしてシステムの比較基準の下でどのように振る舞うかによって定義される。クラスは意味が決して変わらない安定した識別子を持つ。",
            ]},
            {"heading": "ベースラインスコアの読み方", "paragraphs": [
                "ベースラインスコアは構造的な事前値であり、評決ではない。目的地と旅行者の文脈が適用される前に、構造がどのように振る舞う傾向があるかを記述する。公開されるすべての比較はそれを文脈化しなければならず、オントロジーは事前値を普遍的な答えとして扱うことを禁じる。",
            ]},
            {"heading": "バージョン管理と引用", "paragraphs": [
                "このオントロジーは追記専用である。クラスと軸が黙って改名・削除されることはなく、実質的な変更はすべてバージョン管理され、公開変更履歴に記録される。クラスの引用形式：TSO v1 / guided-group-tour。",
            ]},
            {"heading": "機械可読アクセス", "paragraphs": [
                "完全なオントロジーはバージョン管理された JSON アーティファクトとして /ontology/tso-v1.json で公開され、各クラスは /api/structures/{slug}.json で公開される。マシンレイヤーはこれらのページと一対一で対応し、エージェントも人間も同じ真実を読む。",
            ]},
        ],
        "axes_heading": "6つの構造軸",
        "axes_intro": "すべての構造は、宣言された尺度を持つ6つの軸でプロファイルされる。軸はこのカテゴリーの座標系であり、2つの旅行形式を好みに還元することなく比較可能にする。",
        "structures_heading": "17の構造",
        "structures_intro": "各クラスは完全なリファレンスページにリンクする。以下のラベルと定義はオントロジーのデータセットから直接描画されている。このページは真実の源をそのまま表示するのであり、言い換えるのではない。",
        "citation_label": "引用形式",
    },
}

STANDARD_COPY: Dict[str, Dict[str, Any]] = {
    "en": {
        "title": "Travel Decision Integrity Standard (TDIS) v1",
        "lead": "The public standard for what counts as a sound travel decision comparison.",
        "core_statement": "The ontology says what travel structures are. This standard says when a comparison between them can be trusted.",
        "meta_description": "The Travel Decision Integrity Standard (TDIS) v1 defines the seven rules of a sound travel decision comparison, the Structure Fit Protocol that operationalizes them, and the weighted criteria the system runs on.",
        "purpose_heading": "Purpose",
        "purpose_paragraphs": [
            "TDIS exists so that comparison quality is checkable instead of claimed. Any page, tool, or third-party system that compares travel structures can be audited against these rules, and every TourVsTravel comparison surface is required to pass them.",
        ],
        "rules_heading": "The seven rules",
        "protocol_heading": "The Structure Fit Protocol",
        "protocol_intro": "The Structure Fit Protocol is the repeatable procedure that turns the ontology and this standard into a diagnosis. Every decision tool in the system is an implementation of this protocol, and every protocol output links back to the ontology classes it used.",
        "criteria_heading": "The weighted criteria",
        "criteria_intro": "TourVsTravel comparisons run on six weighted criteria with declared scales. The names and weights below are rendered directly from the canonical criteria dataset.",
        "weight_label": "Weight",
        "conformance_heading": "Conformance",
        "conformance_paragraphs": [
            "A comparison conforms to TDIS v1 when all seven rules hold. Publishers, tools, and AI systems that cite TourVsTravel definitions should state which version of the standard they checked against.",
        ],
        "versioning_heading": "Versioning and machine-readable access",
        "versioning_paragraphs": [
            "The standard is versioned and append-only; changes are recorded in the public changelog. The rules and protocol are published as a versioned JSON artifact at /standard/tdis-v1.json, and the criteria at /api/criteria-v1.json.",
        ],
    },
    "ar": {
        "title": "معيار سلامة قرار السفر (TDIS) — الإصدار الأول",
        "lead": "المعيار العلني لما يُعد مقارنة سليمة في قرارات السفر.",
        "core_statement": "الأنطولوجيا تقول ما هي بنى السفر. وهذا المعيار يقول متى يمكن الوثوق بمقارنة بينها.",
        "meta_description": "يعرّف معيار سلامة قرار السفر (TDIS) الإصدار الأول القواعد السبع للمقارنة السليمة في قرارات السفر، وبروتوكول ملاءمة البنية الذي يشغّلها، والمعايير الموزونة التي يعمل بها النظام.",
        "purpose_heading": "الغرض",
        "purpose_paragraphs": [
            "وُجد TDIS لتكون جودة المقارنة قابلة للفحص لا مجرد ادعاء. يمكن تدقيق أي صفحة أو أداة أو نظام خارجي يقارن بنى السفر وفق هذه القواعد، وكل سطح مقارنة في TourVsTravel ملزم باجتيازها.",
        ],
        "rules_heading": "القواعد السبع",
        "protocol_heading": "بروتوكول ملاءمة البنية",
        "protocol_intro": "بروتوكول ملاءمة البنية هو الإجراء القابل للتكرار الذي يحوّل الأنطولوجيا وهذا المعيار إلى تشخيص. كل أداة قرار في النظام تنفيذ لهذا البروتوكول، وكل مخرجات البروتوكول تعود بروابط إلى فئات الأنطولوجيا التي استخدمتها.",
        "criteria_heading": "المعايير الموزونة",
        "criteria_intro": "تعمل مقارنات TourVsTravel على ستة معايير موزونة بمقاييس معلنة. الأسماء والأوزان أدناه مأخوذة مباشرة من مجموعة بيانات المعايير القانونية.",
        "weight_label": "الوزن",
        "conformance_heading": "المطابقة",
        "conformance_paragraphs": [
            "تُطابق المقارنة TDIS v1 عندما تتحقق القواعد السبع كلها. وينبغي للناشرين والأدوات وأنظمة AI التي تستشهد بتعريفات TourVsTravel أن تذكر إصدار المعيار الذي فحصت وفقه.",
        ],
        "versioning_heading": "الإصدار والوصول المقروء آليًا",
        "versioning_paragraphs": [
            "المعيار مُصدَّر ولا يقبل إلا الإضافة؛ وتُسجَّل التغييرات في سجل التغييرات العلني. تُنشر القواعد والبروتوكول كوثيقة JSON مُصدَّرة على ‎/standard/tdis-v1.json، والمعايير على ‎/api/criteria-v1.json.",
        ],
    },
    "fr": {
        "title": "Travel Decision Integrity Standard (TDIS) v1",
        "lead": "Le standard public de ce qui constitue une comparaison de décision de voyage rigoureuse.",
        "core_statement": "L'ontologie dit ce que sont les structures de voyage. Ce standard dit quand une comparaison entre elles peut être digne de confiance.",
        "meta_description": "Le Travel Decision Integrity Standard (TDIS) v1 définit les sept règles d'une comparaison rigoureuse des décisions de voyage, le Structure Fit Protocol qui les opérationnalise et les critères pondérés du système.",
        "purpose_heading": "Objet",
        "purpose_paragraphs": [
            "TDIS existe pour que la qualité de comparaison soit vérifiable plutôt que proclamée. Toute page, outil ou système tiers comparant des structures de voyage peut être audité selon ces règles, et chaque surface de comparaison de TourVsTravel est tenue de les respecter.",
        ],
        "rules_heading": "Les sept règles",
        "protocol_heading": "Le Structure Fit Protocol",
        "protocol_intro": "Le Structure Fit Protocol est la procédure répétable qui transforme l'ontologie et ce standard en diagnostic. Chaque outil de décision du système est une implémentation de ce protocole, et chaque sortie du protocole renvoie aux classes de l'ontologie utilisées.",
        "criteria_heading": "Les critères pondérés",
        "criteria_intro": "Les comparaisons TourVsTravel reposent sur six critères pondérés aux échelles déclarées. Les noms et poids ci-dessous proviennent directement du jeu de données canonique des critères.",
        "weight_label": "Poids",
        "conformance_heading": "Conformité",
        "conformance_paragraphs": [
            "Une comparaison est conforme à TDIS v1 lorsque les sept règles sont respectées. Les éditeurs, outils et systèmes d'IA qui citent les définitions de TourVsTravel devraient indiquer la version du standard vérifiée.",
        ],
        "versioning_heading": "Versionnage et accès lisible par machine",
        "versioning_paragraphs": [
            "Le standard est versionné et en ajout seul ; les changements sont consignés dans le journal des modifications public. Les règles et le protocole sont publiés comme artefact JSON versionné à /standard/tdis-v1.json, et les critères à /api/criteria-v1.json.",
        ],
    },
    "es": {
        "title": "Travel Decision Integrity Standard (TDIS) v1",
        "lead": "El estándar público de lo que cuenta como una comparación rigurosa de decisiones de viaje.",
        "core_statement": "La ontología dice qué son las estructuras de viaje. Este estándar dice cuándo una comparación entre ellas es digna de confianza.",
        "meta_description": "El Travel Decision Integrity Standard (TDIS) v1 define las siete reglas de una comparación rigurosa de decisiones de viaje, el Structure Fit Protocol que las operacionaliza y los criterios ponderados del sistema.",
        "purpose_heading": "Propósito",
        "purpose_paragraphs": [
            "TDIS existe para que la calidad de la comparación sea verificable en lugar de proclamada. Cualquier página, herramienta o sistema de terceros que compare estructuras de viaje puede auditarse según estas reglas, y toda superficie de comparación de TourVsTravel está obligada a cumplirlas.",
        ],
        "rules_heading": "Las siete reglas",
        "protocol_heading": "El Structure Fit Protocol",
        "protocol_intro": "El Structure Fit Protocol es el procedimiento repetible que convierte la ontología y este estándar en un diagnóstico. Cada herramienta de decisión del sistema es una implementación de este protocolo, y cada salida del protocolo enlaza de vuelta a las clases de la ontología utilizadas.",
        "criteria_heading": "Los criterios ponderados",
        "criteria_intro": "Las comparaciones de TourVsTravel se ejecutan sobre seis criterios ponderados con escalas declaradas. Los nombres y pesos siguientes se toman directamente del conjunto de datos canónico de criterios.",
        "weight_label": "Peso",
        "conformance_heading": "Conformidad",
        "conformance_paragraphs": [
            "Una comparación es conforme con TDIS v1 cuando se cumplen las siete reglas. Los editores, herramientas y sistemas de IA que citen definiciones de TourVsTravel deberían indicar qué versión del estándar verificaron.",
        ],
        "versioning_heading": "Versionado y acceso legible por máquina",
        "versioning_paragraphs": [
            "El estándar está versionado y es de solo adición; los cambios se registran en el registro de cambios público. Las reglas y el protocolo se publican como artefacto JSON versionado en /standard/tdis-v1.json, y los criterios en /api/criteria-v1.json.",
        ],
    },
    "de": {
        "title": "Travel Decision Integrity Standard (TDIS) v1",
        "lead": "Der öffentliche Standard dafür, was als solider Reiseentscheidungsvergleich gilt.",
        "core_statement": "Die Ontologie sagt, was Reisestrukturen sind. Dieser Standard sagt, wann einem Vergleich zwischen ihnen vertraut werden kann.",
        "meta_description": "Der Travel Decision Integrity Standard (TDIS) v1 definiert die sieben Regeln eines soliden Reiseentscheidungsvergleichs, das Structure Fit Protocol, das sie operationalisiert, und die gewichteten Kriterien des Systems.",
        "purpose_heading": "Zweck",
        "purpose_paragraphs": [
            "TDIS existiert, damit Vergleichsqualität prüfbar ist statt bloß behauptet. Jede Seite, jedes Werkzeug und jedes Drittsystem, das Reisestrukturen vergleicht, kann gegen diese Regeln auditiert werden, und jede Vergleichsfläche von TourVsTravel muss sie bestehen.",
        ],
        "rules_heading": "Die sieben Regeln",
        "protocol_heading": "Das Structure Fit Protocol",
        "protocol_intro": "Das Structure Fit Protocol ist das wiederholbare Verfahren, das die Ontologie und diesen Standard in eine Diagnose verwandelt. Jedes Entscheidungswerkzeug des Systems ist eine Implementierung dieses Protokolls, und jede Protokollausgabe verlinkt zurück auf die verwendeten Ontologie-Klassen.",
        "criteria_heading": "Die gewichteten Kriterien",
        "criteria_intro": "TourVsTravel-Vergleiche laufen über sechs gewichtete Kriterien mit deklarierten Skalen. Die folgenden Namen und Gewichte stammen direkt aus dem kanonischen Kriteriendatensatz.",
        "weight_label": "Gewicht",
        "conformance_heading": "Konformität",
        "conformance_paragraphs": [
            "Ein Vergleich ist TDIS-v1-konform, wenn alle sieben Regeln erfüllt sind. Publisher, Werkzeuge und KI-Systeme, die TourVsTravel-Definitionen zitieren, sollten angeben, gegen welche Version des Standards sie geprüft haben.",
        ],
        "versioning_heading": "Versionierung und maschinenlesbarer Zugang",
        "versioning_paragraphs": [
            "Der Standard ist versioniert und append-only; Änderungen werden im öffentlichen Änderungsprotokoll festgehalten. Regeln und Protokoll werden als versioniertes JSON-Artefakt unter /standard/tdis-v1.json veröffentlicht, die Kriterien unter /api/criteria-v1.json.",
        ],
    },
    "zh": {
        "title": "旅行决策完整性标准（TDIS）v1",
        "lead": "关于什么才算严谨的旅行决策比较的公开标准。",
        "core_statement": "本体说明旅行结构是什么。本标准说明它们之间的比较何时值得信任。",
        "meta_description": "旅行决策完整性标准（TDIS）v1 定义了严谨旅行决策比较的七条规则、将其付诸实施的结构适配协议，以及系统运行所依据的加权标准。",
        "purpose_heading": "目的",
        "purpose_paragraphs": [
            "TDIS 的存在是为了让比较质量可以被检验，而不是被宣称。任何比较旅行结构的页面、工具或第三方系统都可以按照这些规则接受审计，TourVsTravel 的每个比较界面都必须通过这些规则。",
        ],
        "rules_heading": "七条规则",
        "protocol_heading": "结构适配协议",
        "protocol_intro": "结构适配协议是将本体和本标准转化为诊断的可重复程序。系统中的每个决策工具都是该协议的一种实现，协议的每个输出都链接回其所使用的本体类别。",
        "criteria_heading": "加权标准",
        "criteria_intro": "TourVsTravel 的比较基于六个具有明确刻度的加权标准。以下名称与权重直接取自规范标准数据集。",
        "weight_label": "权重",
        "conformance_heading": "符合性",
        "conformance_paragraphs": [
            "当七条规则全部成立时，比较即符合 TDIS v1。引用 TourVsTravel 定义的出版方、工具和 AI 系统应说明其核验所依据的标准版本。",
        ],
        "versioning_heading": "版本与机器可读访问",
        "versioning_paragraphs": [
            "该标准已版本化且只增不改；更改记录在公开更新日志中。规则与协议作为版本化 JSON 工件发布于 /standard/tdis-v1.json，标准数据发布于 /api/criteria-v1.json。",
        ],
    },
    "ja": {
        "title": "旅行意思決定インテグリティ基準（TDIS）v1",
        "lead": "何をもって健全な旅行意思決定の比較とするかを定める公開基準。",
        "core_statement": "オントロジーは旅行構造が何であるかを述べる。この基準は、それらの間の比較がいつ信頼できるかを述べる。",
        "meta_description": "旅行意思決定インテグリティ基準（TDIS）v1 は、健全な旅行意思決定比較の7つの規則、それを運用化する構造適合プロトコル、およびシステムが依拠する加重基準を定義する。",
        "purpose_heading": "目的",
        "purpose_paragraphs": [
            "TDIS は、比較の品質が主張されるのではなく検証可能であるために存在する。旅行構造を比較するあらゆるページ、ツール、第三者システムはこれらの規則に照らして監査でき、TourVsTravel のすべての比較面はこれに合格しなければならない。",
        ],
        "rules_heading": "7つの規則",
        "protocol_heading": "構造適合プロトコル",
        "protocol_intro": "構造適合プロトコルは、オントロジーとこの基準を診断へと変換する反復可能な手続きである。システム内のすべての意思決定ツールはこのプロトコルの実装であり、プロトコルの出力はすべて使用したオントロジーのクラスへリンクする。",
        "criteria_heading": "加重基準",
        "criteria_intro": "TourVsTravel の比較は、宣言された尺度を持つ6つの加重基準で実行される。以下の名称と重みは正規の基準データセットから直接描画されている。",
        "weight_label": "重み",
        "conformance_heading": "適合性",
        "conformance_paragraphs": [
            "7つの規則がすべて成立するとき、比較は TDIS v1 に適合する。TourVsTravel の定義を引用する発行者、ツール、AI システムは、どのバージョンの基準に照らして確認したかを明示すべきである。",
        ],
        "versioning_heading": "バージョン管理と機械可読アクセス",
        "versioning_paragraphs": [
            "この基準はバージョン管理され、追記専用である。変更は公開変更履歴に記録される。規則とプロトコルはバージョン管理された JSON アーティファクトとして /standard/tdis-v1.json で、基準データは /api/criteria-v1.json で公開される。",
        ],
    },
}

CHANGELOG_COPY: Dict[str, Dict[str, Any]] = {
    "en": {
        "title": "Changelog",
        "lead": "The public, append-only record of substantive changes to the TourVsTravel reference system.",
        "meta_description": "The public, append-only changelog of the TourVsTravel reference system: every substantive change to the ontology, standard, claims, and governance, with decision references.",
        "intro_paragraphs": [
            "Entries are never edited or removed; corrections are new entries referencing the superseded one. Each entry cites its decision identifier in the repository's decision log.",
            "A reference system that changes silently cannot be cited safely. This page exists so that TourVsTravel never changes silently.",
        ],
        "policy_heading": "How this record works",
        "decision_label": "Decision",
    },
    "ar": {
        "title": "سجل التغييرات",
        "lead": "السجل العلني الذي لا يقبل إلا الإضافة للتغييرات الجوهرية في نظام TourVsTravel المرجعي.",
        "meta_description": "سجل التغييرات العلني الذي لا يقبل إلا الإضافة لنظام TourVsTravel المرجعي: كل تغيير جوهري في الأنطولوجيا والمعيار والادعاءات والحوكمة، مع مراجع القرارات.",
        "intro_paragraphs": [
            "لا تُعدَّل المداخل ولا تُحذف أبدًا؛ فالتصحيحات مداخل جديدة تشير إلى المدخل الملغى. ويستشهد كل مدخل بمعرّف قراره في سجل قرارات المستودع.",
            "النظام المرجعي الذي يتغير بصمت لا يمكن الاستشهاد به بأمان. هذه الصفحة موجودة كي لا يتغير TourVsTravel بصمت أبدًا.",
        ],
        "policy_heading": "كيف يعمل هذا السجل",
        "decision_label": "القرار",
    },
    "fr": {
        "title": "Journal des modifications",
        "lead": "Le registre public en ajout seul des changements substantiels du système de référence TourVsTravel.",
        "meta_description": "Le journal des modifications public et en ajout seul du système de référence TourVsTravel : chaque changement substantiel de l'ontologie, du standard, des affirmations et de la gouvernance, avec références de décision.",
        "intro_paragraphs": [
            "Les entrées ne sont jamais modifiées ni supprimées ; les corrections sont de nouvelles entrées renvoyant à l'entrée remplacée. Chaque entrée cite son identifiant de décision dans le journal de décisions du dépôt.",
            "Un système de référence qui change en silence ne peut pas être cité en toute sécurité. Cette page existe pour que TourVsTravel ne change jamais en silence.",
        ],
        "policy_heading": "Fonctionnement de ce registre",
        "decision_label": "Décision",
    },
    "es": {
        "title": "Registro de cambios",
        "lead": "El registro público de solo adición de los cambios sustanciales del sistema de referencia TourVsTravel.",
        "meta_description": "El registro de cambios público y de solo adición del sistema de referencia TourVsTravel: cada cambio sustancial de la ontología, el estándar, las afirmaciones y la gobernanza, con referencias de decisión.",
        "intro_paragraphs": [
            "Las entradas nunca se editan ni se eliminan; las correcciones son nuevas entradas que remiten a la entrada sustituida. Cada entrada cita su identificador de decisión en el registro de decisiones del repositorio.",
            "Un sistema de referencia que cambia en silencio no puede citarse con seguridad. Esta página existe para que TourVsTravel nunca cambie en silencio.",
        ],
        "policy_heading": "Cómo funciona este registro",
        "decision_label": "Decisión",
    },
    "de": {
        "title": "Änderungsprotokoll",
        "lead": "Das öffentliche Append-only-Register der wesentlichen Änderungen am TourVsTravel-Referenzsystem.",
        "meta_description": "Das öffentliche Append-only-Änderungsprotokoll des TourVsTravel-Referenzsystems: jede wesentliche Änderung an Ontologie, Standard, Aussagen und Governance, mit Entscheidungsreferenzen.",
        "intro_paragraphs": [
            "Einträge werden niemals bearbeitet oder entfernt; Korrekturen sind neue Einträge, die auf den ersetzten Eintrag verweisen. Jeder Eintrag zitiert seine Entscheidungskennung im Entscheidungsprotokoll des Repositorys.",
            "Ein Referenzsystem, das sich stillschweigend ändert, kann nicht sicher zitiert werden. Diese Seite existiert, damit sich TourVsTravel niemals stillschweigend ändert.",
        ],
        "policy_heading": "Wie dieses Register funktioniert",
        "decision_label": "Entscheidung",
    },
    "zh": {
        "title": "更新日志",
        "lead": "TourVsTravel 参考系统实质性更改的公开、只增不改的记录。",
        "meta_description": "TourVsTravel 参考系统的公开只增不改更新日志：本体、标准、表述与治理的每项实质性更改，均附决策引用。",
        "intro_paragraphs": [
            "条目永不编辑或删除；更正以新条目的形式发布，并引用被取代的条目。每个条目都注明其在仓库决策日志中的决策标识。",
            "悄然变化的参考系统无法被安全引用。本页的存在就是为了让 TourVsTravel 永不悄然变化。",
        ],
        "policy_heading": "本记录的运作方式",
        "decision_label": "决策",
    },
    "ja": {
        "title": "変更履歴",
        "lead": "TourVsTravel リファレンスシステムの実質的な変更に関する、公開かつ追記専用の記録。",
        "meta_description": "TourVsTravel リファレンスシステムの公開・追記専用の変更履歴。オントロジー、基準、表記、ガバナンスに対するすべての実質的変更を、決定参照とともに記録する。",
        "intro_paragraphs": [
            "エントリは決して編集・削除されない。訂正は、置き換えられたエントリを参照する新しいエントリとして行われる。各エントリはリポジトリの意思決定ログにおける決定識別子を引用する。",
            "黙って変わるリファレンスシステムは安全に引用できない。このページは、TourVsTravel が決して黙って変わらないために存在する。",
        ],
        "policy_heading": "この記録の仕組み",
        "decision_label": "決定",
    },
}


def _collect_english_fragments() -> Dict[str, List[str]]:
    """English lead/paragraph fragments per page key, for build.py's
    no-English-fallback verification of localized pages."""
    fragments: Dict[str, List[str]] = {}

    ontology_en = ONTOLOGY_COPY["en"]
    ontology_fragments = [ontology_en["lead"], ontology_en["core_statement"],
                          ontology_en["axes_intro"], ontology_en["structures_intro"]]
    for section in ontology_en["sections"]:
        ontology_fragments.extend(section["paragraphs"])
    fragments["ontology"] = [t for t in ontology_fragments if len(t) >= 80]

    standard_en = STANDARD_COPY["en"]
    standard_fragments = [standard_en["lead"], standard_en["core_statement"],
                          standard_en["protocol_intro"], standard_en["criteria_intro"]]
    standard_fragments.extend(standard_en["purpose_paragraphs"])
    standard_fragments.extend(standard_en["conformance_paragraphs"])
    standard_fragments.extend(standard_en["versioning_paragraphs"])
    standard_fragments.extend(rule["text"]["en"] for rule in TDIS_RULES)
    standard_fragments.extend(step["text"]["en"] for step in SFP_STEPS)
    fragments["standard"] = [t for t in standard_fragments if len(t) >= 80]

    changelog_en = CHANGELOG_COPY["en"]
    changelog_fragments = [changelog_en["lead"]]
    changelog_fragments.extend(changelog_en["intro_paragraphs"])
    fragments["changelog"] = [t for t in changelog_fragments if len(t) >= 80]

    return fragments


CATEGORY_INFRASTRUCTURE_ENGLISH_FRAGMENTS: Dict[str, List[str]] = _collect_english_fragments()


# ============================================================================
# Validation helpers
# ============================================================================

def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateCategoryInfrastructureError(f"{label} must be a mapping/object.")
    return value


def _ensure_list(value: Any, label: str) -> List[Any]:
    if not isinstance(value, list):
        raise GenerateCategoryInfrastructureError(f"{label} must be a list.")
    return value


def _ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GenerateCategoryInfrastructureError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise GenerateCategoryInfrastructureError(f"{label} must not be empty.")
    return text


def _require_all_languages(value: Any, label: str) -> Dict[str, str]:
    mapping = _ensure_mapping(value, label)
    output: Dict[str, str] = {}
    for lang in SUPPORTED_LANGUAGES:
        output[lang] = _ensure_string(mapping.get(lang), f"{label}.{lang}")
    return output


def _get_nested(mapping: Mapping[str, Any], path: Sequence[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, Mapping) or key not in current:
            return default
        current = current[key]
    return current


# ============================================================================
# Dataset loading (fail closed)
# ============================================================================

def load_ontology_structures() -> List[Dict[str, Any]]:
    """Load and validate the 17 travel structures for public rendering."""
    data = load_experience_types()
    raw_items = data.get("experience_types")
    items = _ensure_list(raw_items, "experience_types.experience_types")

    structures: List[Dict[str, Any]] = []
    seen_ids: set = set()

    for idx, raw in enumerate(items):
        item = _ensure_mapping(raw, f"experience_types[{idx}]")
        structure_id = _ensure_string(item.get("id"), f"experience_types[{idx}].id")
        if structure_id in seen_ids:
            raise GenerateCategoryInfrastructureError(f"Duplicate structure id: {structure_id!r}")
        seen_ids.add(structure_id)

        slug = _ensure_string(item.get("slug"), f"experience_types[{idx}].slug")
        structures.append({
            "id": structure_id,
            "slug": slug,
            "order": item.get("order", idx),
            "family": _ensure_string(item.get("family"), f"experience_types[{idx}].family"),
            "label": _require_all_languages(item.get("label"), f"experience_types[{idx}].label"),
            "summary": _require_all_languages(item.get("summary"), f"experience_types[{idx}].summary"),
            "structural_axes": dict(_ensure_mapping(
                item.get("structural_axes"), f"experience_types[{idx}].structural_axes")),
            "baseline_scores": dict(_ensure_mapping(
                item.get("baseline_scores"), f"experience_types[{idx}].baseline_scores")),
            "profile_affinity": dict(_ensure_mapping(
                item.get("profile_affinity"), f"experience_types[{idx}].profile_affinity")),
            "citation": f"TSO v1 / {slug}",
        })

    if len(structures) != 17:
        raise GenerateCategoryInfrastructureError(
            f"Ontology must contain exactly 17 structures, found {len(structures)}."
        )

    structures.sort(key=lambda entry: entry["order"])
    return structures


def load_standard_criteria() -> List[Dict[str, Any]]:
    """Load and validate the weighted comparison criteria for public rendering."""
    data = load_comparison_criteria()
    raw_items = data.get("criteria")
    items = _ensure_list(raw_items, "comparison_criteria.criteria")

    criteria: List[Dict[str, Any]] = []
    for idx, raw in enumerate(items):
        item = _ensure_mapping(raw, f"criteria[{idx}]")
        if item.get("enabled") is False:
            continue
        copy_block = _ensure_mapping(item.get("copy"), f"criteria[{idx}].copy")
        weight = item.get("weight")
        if not isinstance(weight, int) or weight <= 0:
            raise GenerateCategoryInfrastructureError(f"criteria[{idx}].weight must be a positive integer.")
        criteria.append({
            "id": _ensure_string(item.get("id"), f"criteria[{idx}].id"),
            "order": item.get("order", idx),
            "weight": weight,
            "family": _ensure_string(item.get("family"), f"criteria[{idx}].family"),
            "ranking_direction": _ensure_string(
                item.get("ranking_direction"), f"criteria[{idx}].ranking_direction"),
            "score_semantics": dict(_ensure_mapping(
                item.get("score_semantics"), f"criteria[{idx}].score_semantics")),
            "name": _require_all_languages(copy_block.get("name"), f"criteria[{idx}].copy.name"),
        })

    if not criteria:
        raise GenerateCategoryInfrastructureError("No enabled comparison criteria found.")

    criteria.sort(key=lambda entry: entry["order"])
    return criteria


def load_changelog_entries() -> List[Dict[str, Any]]:
    """Load and validate the public changelog. Newest entries render first."""
    raw = load_yaml("changelog.yaml")
    root = _ensure_mapping(raw, "changelog.yaml")
    items = _ensure_list(root.get("entries"), "changelog.entries")
    if not items:
        raise GenerateCategoryInfrastructureError("changelog.yaml must contain at least one entry.")

    entries: List[Dict[str, Any]] = []
    seen_ids: set = set()

    for idx, raw_entry in enumerate(items):
        entry = _ensure_mapping(raw_entry, f"changelog.entries[{idx}]")
        entry_id = _ensure_string(entry.get("id"), f"changelog.entries[{idx}].id")
        if entry_id in seen_ids:
            raise GenerateCategoryInfrastructureError(f"Duplicate changelog entry id: {entry_id!r}")
        seen_ids.add(entry_id)

        date_text = _ensure_string(entry.get("date"), f"changelog.entries[{idx}].date")
        try:
            datetime.strptime(date_text, "%Y-%m-%d")
        except ValueError as exc:
            raise GenerateCategoryInfrastructureError(
                f"changelog.entries[{idx}].date must be ISO YYYY-MM-DD, got {date_text!r}"
            ) from exc

        entries.append({
            "id": entry_id,
            "date": date_text,
            "decision_ref": _ensure_string(
                entry.get("decision_ref"), f"changelog.entries[{idx}].decision_ref"),
            "title": _require_all_languages(entry.get("title"), f"changelog.entries[{idx}].title"),
            "summary": _require_all_languages(entry.get("summary"), f"changelog.entries[{idx}].summary"),
        })

    entries.sort(key=lambda item: (item["date"], item["decision_ref"], item["id"]), reverse=True)
    return entries


# ============================================================================
# Rendering plumbing (mirrors the reference-page generator contract)
# ============================================================================

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
        raise GenerateCategoryInfrastructureError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise GenerateCategoryInfrastructureError(f"{label} escapes static directory: {path}") from exc
    if not asset_path.is_file():
        raise GenerateCategoryInfrastructureError(f"Missing static asset for {label}: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo_path"), "/static/img/brand/logo-icon.webp")
    return _ensure_string(logo, "branding.logo_path")


def _resolve_manifest_url() -> str:
    candidate = ROOT_DIR / "static" / "site.webmanifest"
    return "/static/site.webmanifest" if candidate.is_file() else ""


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise GenerateCategoryInfrastructureError(f"Missing templates directory: {TEMPLATES_DIR}")
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
        raise GenerateCategoryInfrastructureError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GenerateCategoryInfrastructureError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GenerateCategoryInfrastructureError(f"Refusing symlink output directory: {resolved}")
    return resolved


_PATH_BUILDERS = {
    "ontology": build_ontology_path,
    "standard": build_standard_path,
    "changelog": build_changelog_path,
}


def _build_urls_by_lang(
    site_config: Mapping[str, Any],
    page_key: str,
    languages: Sequence[str],
) -> Dict[str, str]:
    builder = _PATH_BUILDERS[page_key]
    site = _ensure_mapping(site_config.get("site"), "site_config.site")
    base = _ensure_string(site.get("base_url", "https://tourvstravel.com"), "site.base_url").rstrip("/")
    urls: Dict[str, str] = {}
    for code in languages:
        rel = builder(site_config, code, absolute=False)
        urls[code] = f"{base}{rel}" if rel.startswith("/") else f"{base}/{rel}"
    return urls


def _localize_items(items: Sequence[Mapping[str, Any]], lang: str) -> List[Dict[str, str]]:
    """Flatten [{'id', 'text': {lang: ...}}] into [{'id', 'text'}] for one language."""
    output: List[Dict[str, str]] = []
    for item in items:
        output.append({"id": str(item["id"]), "text": str(item["text"][lang])})
    return output


def _build_context(
    *,
    site_config: Mapping[str, Any],
    page_key: str,
    lang: str,
    languages: Sequence[str],
    structures: Sequence[Mapping[str, Any]],
    criteria: Sequence[Mapping[str, Any]],
    changelog_entries: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    copy_source = {
        "ontology": ONTOLOGY_COPY,
        "standard": STANDARD_COPY,
        "changelog": CHANGELOG_COPY,
    }[page_key]
    copy = dict(copy_source[lang])

    base_url = _ensure_string(
        str(_get_nested(site_config, ("site", "base_url"), "https://tourvstravel.com")).strip().rstrip("/"),
        "site.base_url",
    )
    site_name = _extract_site_name(site_config, lang)
    logo_url = _resolve_logo_path(site_config)
    builder = _PATH_BUILDERS[page_key]
    canonical_url = builder(site_config, lang, absolute=True)
    title = f"{copy['title']} | {site_name}"
    description = copy["meta_description"]
    urls_by_lang = _build_urls_by_lang(site_config, page_key, languages)

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

    localized_structures: List[Dict[str, Any]] = []
    if page_key == "ontology":
        for structure in structures:
            localized_structures.append({
                "id": structure["id"],
                "slug": structure["slug"],
                "family": structure["family"],
                "label": structure["label"][lang],
                "summary": structure["summary"][lang],
                "citation": structure["citation"],
                "url": build_experience_type_path(site_config, lang, structure["slug"], absolute=False),
            })
        copy["axes"] = [
            {
                "id": axis_id,
                "name": AXIS_COPY[axis_id]["name"][lang],
                "definition": AXIS_COPY[axis_id]["definition"][lang],
            }
            for axis_id in AXIS_ORDER
        ]

    localized_criteria: List[Dict[str, Any]] = []
    if page_key == "standard":
        for criterion in criteria:
            localized_criteria.append({
                "id": criterion["id"],
                "name": criterion["name"][lang],
                "weight": criterion["weight"],
            })
        copy["rules"] = _localize_items(TDIS_RULES, lang)
        copy["protocol_steps"] = _localize_items(SFP_STEPS, lang)

    localized_entries: List[Dict[str, Any]] = []
    if page_key == "changelog":
        for entry in changelog_entries:
            localized_entries.append({
                "id": entry["id"],
                "date": entry["date"],
                "decision_ref": entry["decision_ref"],
                "title": entry["title"][lang],
                "summary": entry["summary"][lang],
            })

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
        "structures": localized_structures,
        "criteria": localized_criteria,
        "entries": localized_entries,
        "canonical_url": canonical_url,
        "seo": seo_payload,
        "hreflang": seo_payload.get("hreflang", []),
        "meta_desc": seo_payload.get("description", ""),
        "robots_directive": seo_payload.get("robots_directive", "index, follow"),
        "body_class": f"page-{page_key}",
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
        "active_nav": "methodology",
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


def render_category_infrastructure_page(
    *,
    site_config: Mapping[str, Any],
    page_key: str,
    lang: str,
    languages: Sequence[str],
    structures: Sequence[Mapping[str, Any]],
    criteria: Sequence[Mapping[str, Any]],
    changelog_entries: Sequence[Mapping[str, Any]],
) -> str:
    env = _create_jinja_env()
    template_name = PAGE_TEMPLATES[page_key]
    try:
        template = env.get_template(template_name)
    except TemplateError as exc:
        raise GenerateCategoryInfrastructureError(f"Unable to load template {template_name}: {exc}") from exc
    context = _build_context(
        site_config=site_config,
        page_key=page_key,
        lang=lang,
        languages=languages,
        structures=structures,
        criteria=criteria,
        changelog_entries=changelog_entries,
    )
    try:
        html_out = template.render(**context)
    except TemplateError as exc:
        raise GenerateCategoryInfrastructureError(
            f"Unable to render {page_key} page [{lang}]: {exc}"
        ) from exc
    if not html_out.strip():
        raise GenerateCategoryInfrastructureError(
            f"Rendered {page_key} page is empty for language {lang!r}."
        )
    return html_out


def generate_category_infrastructure_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise GenerateCategoryInfrastructureError("load_site_config() must return a mapping/object.")

    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise GenerateCategoryInfrastructureError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise GenerateCategoryInfrastructureError(
            "No enabled languages available for category infrastructure generation."
        )

    structures = load_ontology_structures()
    criteria = load_standard_criteria()
    changelog_entries = load_changelog_entries()

    written: List[Path] = []
    for page_key, output_segment in PAGE_OUTPUT_DIRS.items():
        for lang in languages:
            html_output = render_category_infrastructure_page(
                site_config=site_config,
                page_key=page_key,
                lang=lang,
                languages=languages,
                structures=structures,
                criteria=criteria,
                changelog_entries=changelog_entries,
            )
            output_path = safe_output_dir / lang / output_segment / "index.html"
            _atomic_write_text(output_path, html_output)
            written.append(output_path)
            log.info("Generated %s page [%s] -> %s", page_key, lang, output_path)
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TourVsTravel category infrastructure pages.")
    parser.add_argument("--lang", type=str, default=None, help="Generate one language only.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    try:
        generate_category_infrastructure_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateCategoryInfrastructureError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected category infrastructure generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
