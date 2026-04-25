#!/usr/bin/env python3
"""
TourVsTravel — Find Your Match Generator
========================================

Generate the first real static decision tool:

    /{lang}/tools/find-your-match/

The page is multilingual, frontend-driven, and grounded in the existing
experience type ontology. It makes no booking, backend, or fake AI claims.
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
log = logging.getLogger("generate_find_your_match")


ROOT_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = ROOT_DIR / "static"
TEMPLATES_DIR = ROOT_DIR / "templates"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/find_your_match.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")


class GenerateFindYourMatchError(Exception):
    """Raised when Find Your Match generation fails."""


class FindMatchConfigError(GenerateFindYourMatchError):
    """Raised when configuration is invalid."""


class FindMatchRenderError(GenerateFindYourMatchError):
    """Raised when rendering fails."""


class FindMatchWriteError(GenerateFindYourMatchError):
    """Raised when writing fails."""


PAGE_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "eyebrow": "Find Your Match · Travel Fit Tool · Structured Decision",
        "title": "Find the Travel Style That Fits You",
        "lead": "Answer six questions about structure, autonomy, support, complexity, depth, and predictability. The tool maps your answers to the closest travel styles inside the TourVsTravel reference system.",
        "compare_action": "Open Compare",
        "styles_action": "Explore Styles",
        "tools_action": "Back to Tools",
        "methodology_action": "Read Methodology",
        "panel_label": "Find Your Match signals",
        "panel_card_1_label": "Decision mode",
        "panel_card_1_value": "Preference translated into fit.",
        "panel_card_2_label": "Style universe",
        "panel_card_2_value": "travel styles available.",
        "panel_card_3_label": "Output",
        "panel_card_3_value": "One strongest match plus alternatives.",
        "tool_kicker": "Decision instrument",
        "tool_title": "Answer the six fit questions",
        "tool_lead": "The result is not a booking recommendation. It is a structured starting point for understanding which form of travel deserves your attention.",
        "progress_label": "Question completion progress",
        "progress_initial": "0 of 6 questions answered",
        "submit_label": "Calculate My Match",
        "reset_label": "Reset",
        "incomplete_notice": "Answer every question before calculating your match.",
        "noscript_title": "JavaScript is required for the interactive result.",
        "noscript_body": "You can still use the Compare and Styles pages to evaluate travel styles manually.",
        "results_kicker": "Your match",
        "results_title": "Recommended travel styles",
        "results_lead": "These results are directional. Open each reference page to understand the tradeoffs behind the match.",
        "method_kicker": "Method",
        "method_title": "How the match is calculated",
        "method_lead": "Your answers are translated into criteria weights. The tool scores each travel style using its baseline profile, structural axes, and decision characteristics.",
        "final_kicker": "Next step",
        "final_title": "Use the result as a decision path",
        "final_lead": "A strong match is not an instruction. It is a starting point for comparing structure, burden, support, cost logic, and experience depth.",
        "score_label": "Match score",
        "open_label": "Open reference page",
        "progress_template": "{answered} of {total} questions answered",
    },
    "ar": {
        "eyebrow": "اعرف الأنسب لك · أداة ملاءمة السفر · قرار منظم",
        "title": "اعرف نمط السفر الأنسب لك",
        "lead": "أجب عن ستة أسئلة حول البنية، الاستقلالية، الدعم، التعقيد، عمق التجربة، وقابلية التوقع. ستحوّل الأداة إجاباتك إلى أقرب أنماط سفر داخل نظام TourVsTravel.",
        "compare_action": "افتح المقارنة",
        "styles_action": "استكشف الأنماط",
        "tools_action": "العودة إلى الأدوات",
        "methodology_action": "اقرأ المنهجية",
        "panel_label": "إشارات أداة الملاءمة",
        "panel_card_1_label": "نمط القرار",
        "panel_card_1_value": "تحويل التفضيل إلى ملاءمة.",
        "panel_card_2_label": "عالم الأنماط",
        "panel_card_2_value": "نمط سفر متاح.",
        "panel_card_3_label": "المخرج",
        "panel_card_3_value": "أفضل تطابق مع بدائل قريبة.",
        "tool_kicker": "أداة قرار",
        "tool_title": "أجب عن أسئلة الملاءمة الستة",
        "tool_lead": "النتيجة ليست توصية حجز. إنها نقطة بداية منظمة لفهم شكل السفر الذي يستحق انتباهك.",
        "progress_label": "تقدم الإجابة",
        "progress_initial": "0 من 6 أسئلة تمت الإجابة عنها",
        "submit_label": "احسب النمط الأنسب",
        "reset_label": "إعادة",
        "incomplete_notice": "أجب عن كل الأسئلة قبل حساب النتيجة.",
        "noscript_title": "تحتاج الأداة إلى JavaScript لإظهار النتيجة التفاعلية.",
        "noscript_body": "يمكنك استعمال صفحات المقارنة والأنماط لتقييم الأنماط يدويًا.",
        "results_kicker": "نتيجتك",
        "results_title": "أنماط السفر المقترحة",
        "results_lead": "هذه النتائج اتجاهية. افتح كل صفحة مرجعية لفهم المفاضلات خلف النتيجة.",
        "method_kicker": "المنهج",
        "method_title": "كيف تُحسب الملاءمة",
        "method_lead": "تُحوَّل إجاباتك إلى أوزان معيارية، ثم تُقيّم الأداة كل نمط سفر حسب ملفه الأساسي ومحاوره البنيوية.",
        "final_kicker": "الخطوة التالية",
        "final_title": "استعمل النتيجة كمسار قرار",
        "final_lead": "التطابق القوي ليس أمرًا نهائيًا. إنه نقطة بداية لمقارنة البنية والعبء والدعم وعمق التجربة.",
        "score_label": "درجة الملاءمة",
        "open_label": "افتح الصفحة المرجعية",
        "progress_template": "{answered} من {total} أسئلة تمت الإجابة عنها",
    },
    "fr": {
        "eyebrow": "Trouver mon style · outil d’adéquation · décision structurée",
        "title": "Trouvez le style de voyage qui vous correspond",
        "lead": "Répondez à six questions sur la structure, l’autonomie, le soutien, la complexité, la profondeur et la prévisibilité.",
        "compare_action": "Ouvrir la comparaison",
        "styles_action": "Explorer les styles",
        "tools_action": "Retour aux outils",
        "methodology_action": "Lire la méthodologie",
        "panel_label": "Signaux de l’outil",
        "panel_card_1_label": "Mode de décision",
        "panel_card_1_value": "Préférence traduite en adéquation.",
        "panel_card_2_label": "Univers des styles",
        "panel_card_2_value": "styles disponibles.",
        "panel_card_3_label": "Sortie",
        "panel_card_3_value": "Un meilleur match et des alternatives.",
        "tool_kicker": "Instrument de décision",
        "tool_title": "Répondez aux six questions",
        "tool_lead": "Le résultat est un point de départ structuré, pas une recommandation de réservation.",
        "progress_label": "Progression",
        "progress_initial": "0 question sur 6 répondue",
        "submit_label": "Calculer mon match",
        "reset_label": "Réinitialiser",
        "incomplete_notice": "Répondez à toutes les questions avant de calculer.",
        "noscript_title": "JavaScript est requis pour le résultat interactif.",
        "noscript_body": "Vous pouvez utiliser les pages Comparer et Styles manuellement.",
        "results_kicker": "Votre résultat",
        "results_title": "Styles de voyage recommandés",
        "results_lead": "Ces résultats sont directionnels. Ouvrez chaque page pour comprendre les arbitrages.",
        "method_kicker": "Méthode",
        "method_title": "Comment le match est calculé",
        "method_lead": "Vos réponses deviennent des poids appliqués aux profils des styles de voyage.",
        "final_kicker": "Étape suivante",
        "final_title": "Utiliser le résultat comme chemin de décision",
        "final_lead": "Un match fort est un point de départ pour comparer structure, charge, soutien et profondeur.",
        "score_label": "Score d’adéquation",
        "open_label": "Ouvrir la page",
        "progress_template": "{answered} question(s) sur {total} répondue(s)",
    },
}

QUESTION_COPY: Dict[str, List[Dict[str, Any]]] = {
    "en": [
        {
            "id": "structure",
            "label": "How much structure do you want?",
            "hint": "Structure determines whether the trip feels planned, flexible, or fully self-directed.",
            "options": [
                {"id": "high", "label": "High structure", "description": "I want a defined plan, route, or operating frame."},
                {"id": "balanced", "label": "Balanced structure", "description": "I want structure, but not rigidity."},
                {"id": "low", "label": "Low structure", "description": "I want freedom to shape the trip as it unfolds."},
            ],
        },
        {
            "id": "autonomy",
            "label": "How much autonomy do you want?",
            "hint": "Autonomy measures how much control you want over timing, movement, and decisions.",
            "options": [
                {"id": "guided", "label": "Low autonomy", "description": "I prefer someone else to handle many decisions."},
                {"id": "mixed", "label": "Shared autonomy", "description": "I want guidance but still want meaningful choice."},
                {"id": "high", "label": "High autonomy", "description": "I want to control the experience directly."},
            ],
        },
        {
            "id": "support",
            "label": "How much support do you need?",
            "hint": "Support includes logistics, safety, translation, local access, and problem-solving.",
            "options": [
                {"id": "high", "label": "High support", "description": "I want strong assistance and reduced friction."},
                {"id": "medium", "label": "Moderate support", "description": "I can manage some things, but not everything."},
                {"id": "low", "label": "Low support", "description": "I am comfortable solving problems myself."},
            ],
        },
        {
            "id": "complexity",
            "label": "How much complexity can you manage?",
            "hint": "Some styles require planning, adaptation, uncertainty, and operational effort.",
            "options": [
                {"id": "low", "label": "Low complexity", "description": "I want the trip to be easy to operate."},
                {"id": "medium", "label": "Moderate complexity", "description": "I can handle some moving parts."},
                {"id": "high", "label": "High complexity", "description": "I can handle uncertainty, planning, and adaptation."},
            ],
        },
        {
            "id": "depth",
            "label": "How deep do you want the experience to be?",
            "hint": "Depth measures whether the trip is primarily comfortable, balanced, or immersive.",
            "options": [
                {"id": "surface", "label": "Light experience", "description": "I want comfort, ease, and selected highlights."},
                {"id": "balanced", "label": "Balanced experience", "description": "I want both comfort and meaningful exposure."},
                {"id": "deep", "label": "Deep experience", "description": "I want immersion, texture, and direct contact with place."},
            ],
        },
        {
            "id": "predictability",
            "label": "How predictable should the trip feel?",
            "hint": "Predictability affects comfort, risk, flexibility, and emotional load.",
            "options": [
                {"id": "high", "label": "Highly predictable", "description": "I want clarity before I commit."},
                {"id": "medium", "label": "Moderately predictable", "description": "I accept some uncertainty."},
                {"id": "low", "label": "Low predictability", "description": "I welcome discovery, ambiguity, and change."},
            ],
        },
    ],
    "ar": [
        {
            "id": "structure",
            "label": "ما مقدار البنية التي تريدها في الرحلة؟",
            "hint": "البنية تحدد هل تبدو الرحلة مخططة، مرنة، أم موجهة بالكامل من طرفك.",
            "options": [
                {"id": "high", "label": "بنية عالية", "description": "أريد خطة واضحة أو مسارًا محددًا أو إطارًا منظّمًا."},
                {"id": "balanced", "label": "بنية متوازنة", "description": "أريد تنظيمًا يساعدني، لكن دون صرامة زائدة."},
                {"id": "low", "label": "بنية منخفضة", "description": "أريد حرية تشكيل الرحلة حسب ما يحدث في الطريق."},
            ],
        },
        {
            "id": "autonomy",
            "label": "ما مقدار الاستقلالية التي تريدها؟",
            "hint": "الاستقلالية تعني مقدار التحكم الذي تريده في الوقت والحركة والقرارات.",
            "options": [
                {"id": "guided", "label": "استقلالية منخفضة", "description": "أفضل أن يتولى شخص أو نظام آخر جزءًا كبيرًا من القرارات."},
                {"id": "mixed", "label": "استقلالية مشتركة", "description": "أريد توجيهًا واضحًا مع بقاء مساحة حقيقية للاختيار."},
                {"id": "high", "label": "استقلالية عالية", "description": "أريد التحكم المباشر في التجربة ومسارها."},
            ],
        },
        {
            "id": "support",
            "label": "ما مقدار الدعم الذي تحتاجه؟",
            "hint": "الدعم يشمل اللوجستيك، السلامة، اللغة، الوصول المحلي، وحل المشاكل.",
            "options": [
                {"id": "high", "label": "دعم عالٍ", "description": "أريد مساعدة قوية وتقليل الاحتكاك والتعقيد."},
                {"id": "medium", "label": "دعم متوسط", "description": "أستطيع تدبير بعض الأمور، لكن لا أريد تحمل كل شيء وحدي."},
                {"id": "low", "label": "دعم منخفض", "description": "أنا مرتاح في حل المشاكل والتعامل مع المواقف بنفسي."},
            ],
        },
        {
            "id": "complexity",
            "label": "ما مقدار التعقيد الذي تستطيع تحمّله؟",
            "hint": "بعض أنماط السفر تحتاج تخطيطًا، تكيّفًا، عدم يقين، وجهدًا تشغيليًا.",
            "options": [
                {"id": "low", "label": "تعقيد منخفض", "description": "أريد رحلة سهلة التشغيل وقليلة المشاكل."},
                {"id": "medium", "label": "تعقيد متوسط", "description": "أستطيع التعامل مع بعض التفاصيل المتحركة."},
                {"id": "high", "label": "تعقيد عالٍ", "description": "أستطيع تحمل عدم اليقين والتخطيط والتكيّف المستمر."},
            ],
        },
        {
            "id": "depth",
            "label": "ما عمق التجربة الذي تريده؟",
            "hint": "عمق التجربة يحدد هل تبحث عن راحة، توازن، أم انغماس مباشر في المكان.",
            "options": [
                {"id": "surface", "label": "تجربة خفيفة", "description": "أريد راحة وسهولة وأبرز النقاط المختارة."},
                {"id": "balanced", "label": "تجربة متوازنة", "description": "أريد راحة مع تعرض حقيقي ومعنى أعمق."},
                {"id": "deep", "label": "تجربة عميقة", "description": "أريد انغماسًا واحتكاكًا مباشرًا بالمكان وتفاصيله."},
            ],
        },
        {
            "id": "predictability",
            "label": "إلى أي درجة يجب أن تكون الرحلة قابلة للتوقع؟",
            "hint": "قابلية التوقع تؤثر على الراحة، المخاطرة، المرونة، والضغط النفسي.",
            "options": [
                {"id": "high", "label": "قابلية توقع عالية", "description": "أريد وضوحًا كبيرًا قبل الالتزام."},
                {"id": "medium", "label": "قابلية توقع متوسطة", "description": "أقبل قدرًا محدودًا من عدم اليقين."},
                {"id": "low", "label": "قابلية توقع منخفضة", "description": "أرحب بالاكتشاف والغموض والتغير."},
            ],
        },
    ],
    "fr": [
        {
            "id": "structure",
            "label": "Quel niveau de structure souhaitez-vous ?",
            "hint": "La structure détermine si le voyage est planifié, flexible ou entièrement autonome.",
            "options": [
                {"id": "high", "label": "Structure élevée", "description": "Je veux un plan, un itinéraire ou un cadre clair."},
                {"id": "balanced", "label": "Structure équilibrée", "description": "Je veux de la structure, mais sans rigidité excessive."},
                {"id": "low", "label": "Structure faible", "description": "Je veux façonner le voyage au fur et à mesure."},
            ],
        },
        {
            "id": "autonomy",
            "label": "Quel niveau d’autonomie souhaitez-vous ?",
            "hint": "L’autonomie mesure le contrôle voulu sur le temps, les déplacements et les décisions.",
            "options": [
                {"id": "guided", "label": "Faible autonomie", "description": "Je préfère que beaucoup de décisions soient prises pour moi."},
                {"id": "mixed", "label": "Autonomie partagée", "description": "Je veux être guidé tout en gardant de vrais choix."},
                {"id": "high", "label": "Forte autonomie", "description": "Je veux contrôler directement l’expérience."},
            ],
        },
        {
            "id": "support",
            "label": "De quel niveau de soutien avez-vous besoin ?",
            "hint": "Le soutien inclut la logistique, la sécurité, la langue, l’accès local et la résolution de problèmes.",
            "options": [
                {"id": "high", "label": "Soutien élevé", "description": "Je veux une assistance forte et moins de friction."},
                {"id": "medium", "label": "Soutien modéré", "description": "Je peux gérer certaines choses, mais pas tout."},
                {"id": "low", "label": "Soutien faible", "description": "Je suis à l’aise pour résoudre les problèmes moi-même."},
            ],
        },
        {
            "id": "complexity",
            "label": "Quel niveau de complexité pouvez-vous gérer ?",
            "hint": "Certains styles demandent planification, adaptation, incertitude et effort opérationnel.",
            "options": [
                {"id": "low", "label": "Complexité faible", "description": "Je veux un voyage facile à gérer."},
                {"id": "medium", "label": "Complexité modérée", "description": "Je peux gérer quelques éléments mouvants."},
                {"id": "high", "label": "Complexité élevée", "description": "Je peux gérer incertitude, planification et adaptation."},
            ],
        },
        {
            "id": "depth",
            "label": "Quelle profondeur d’expérience recherchez-vous ?",
            "hint": "La profondeur indique si le voyage est confortable, équilibré ou immersif.",
            "options": [
                {"id": "surface", "label": "Expérience légère", "description": "Je veux confort, simplicité et points forts sélectionnés."},
                {"id": "balanced", "label": "Expérience équilibrée", "description": "Je veux à la fois confort et exposition significative."},
                {"id": "deep", "label": "Expérience profonde", "description": "Je veux immersion, texture et contact direct avec le lieu."},
            ],
        },
        {
            "id": "predictability",
            "label": "À quel point le voyage doit-il être prévisible ?",
            "hint": "La prévisibilité influence le confort, le risque, la flexibilité et la charge émotionnelle.",
            "options": [
                {"id": "high", "label": "Très prévisible", "description": "Je veux de la clarté avant de m’engager."},
                {"id": "medium", "label": "Modérément prévisible", "description": "J’accepte une part d’incertitude."},
                {"id": "low", "label": "Peu prévisible", "description": "J’accueille découverte, ambiguïté et changement."},
            ],
        },
    ],
    "es": [
        {
            "id": "structure",
            "label": "¿Cuánta estructura quieres?",
            "hint": "La estructura determina si el viaje se siente planificado, flexible o completamente autodirigido.",
            "options": [
                {"id": "high", "label": "Alta estructura", "description": "Quiero un plan, ruta o marco definido."},
                {"id": "balanced", "label": "Estructura equilibrada", "description": "Quiero estructura, pero sin rigidez."},
                {"id": "low", "label": "Baja estructura", "description": "Quiero libertad para moldear el viaje sobre la marcha."},
            ],
        },
        {
            "id": "autonomy",
            "label": "¿Cuánta autonomía quieres?",
            "hint": "La autonomía mide cuánto control quieres sobre tiempos, movimientos y decisiones.",
            "options": [
                {"id": "guided", "label": "Baja autonomía", "description": "Prefiero que muchas decisiones las gestione otra persona o sistema."},
                {"id": "mixed", "label": "Autonomía compartida", "description": "Quiero orientación, pero también elecciones reales."},
                {"id": "high", "label": "Alta autonomía", "description": "Quiero controlar directamente la experiencia."},
            ],
        },
        {
            "id": "support",
            "label": "¿Cuánto apoyo necesitas?",
            "hint": "El apoyo incluye logística, seguridad, idioma, acceso local y resolución de problemas.",
            "options": [
                {"id": "high", "label": "Alto apoyo", "description": "Quiero asistencia fuerte y menos fricción."},
                {"id": "medium", "label": "Apoyo moderado", "description": "Puedo manejar algunas cosas, pero no todo."},
                {"id": "low", "label": "Bajo apoyo", "description": "Me siento cómodo resolviendo problemas por mi cuenta."},
            ],
        },
        {
            "id": "complexity",
            "label": "¿Cuánta complejidad puedes manejar?",
            "hint": "Algunos estilos requieren planificación, adaptación, incertidumbre y esfuerzo operativo.",
            "options": [
                {"id": "low", "label": "Baja complejidad", "description": "Quiero un viaje fácil de gestionar."},
                {"id": "medium", "label": "Complejidad moderada", "description": "Puedo manejar algunas partes móviles."},
                {"id": "high", "label": "Alta complejidad", "description": "Puedo manejar incertidumbre, planificación y adaptación."},
            ],
        },
        {
            "id": "depth",
            "label": "¿Qué profundidad de experiencia buscas?",
            "hint": "La profundidad indica si el viaje es cómodo, equilibrado o inmersivo.",
            "options": [
                {"id": "surface", "label": "Experiencia ligera", "description": "Quiero comodidad, facilidad y puntos destacados."},
                {"id": "balanced", "label": "Experiencia equilibrada", "description": "Quiero comodidad y exposición significativa."},
                {"id": "deep", "label": "Experiencia profunda", "description": "Quiero inmersión y contacto directo con el lugar."},
            ],
        },
        {
            "id": "predictability",
            "label": "¿Qué tan predecible debe sentirse el viaje?",
            "hint": "La previsibilidad afecta comodidad, riesgo, flexibilidad y carga emocional.",
            "options": [
                {"id": "high", "label": "Muy predecible", "description": "Quiero claridad antes de comprometerme."},
                {"id": "medium", "label": "Moderadamente predecible", "description": "Acepto algo de incertidumbre."},
                {"id": "low", "label": "Poco predecible", "description": "Acepto descubrimiento, ambigüedad y cambio."},
            ],
        },
    ],
    "de": [
        {
            "id": "structure",
            "label": "Wie viel Struktur möchtest du?",
            "hint": "Struktur bestimmt, ob die Reise geplant, flexibel oder vollständig selbstgesteuert wirkt.",
            "options": [
                {"id": "high", "label": "Hohe Struktur", "description": "Ich möchte einen klaren Plan, eine Route oder einen Rahmen."},
                {"id": "balanced", "label": "Ausgewogene Struktur", "description": "Ich möchte Struktur, aber keine starre Planung."},
                {"id": "low", "label": "Geringe Struktur", "description": "Ich möchte die Reise unterwegs frei gestalten."},
            ],
        },
        {
            "id": "autonomy",
            "label": "Wie viel Autonomie möchtest du?",
            "hint": "Autonomie misst, wie viel Kontrolle du über Zeit, Bewegung und Entscheidungen willst.",
            "options": [
                {"id": "guided", "label": "Geringe Autonomie", "description": "Ich bevorzuge, dass viele Entscheidungen übernommen werden."},
                {"id": "mixed", "label": "Geteilte Autonomie", "description": "Ich möchte Führung, aber weiterhin echte Wahlmöglichkeiten."},
                {"id": "high", "label": "Hohe Autonomie", "description": "Ich möchte die Erfahrung direkt kontrollieren."},
            ],
        },
        {
            "id": "support",
            "label": "Wie viel Unterstützung brauchst du?",
            "hint": "Unterstützung umfasst Logistik, Sicherheit, Sprache, lokalen Zugang und Problemlösung.",
            "options": [
                {"id": "high", "label": "Hohe Unterstützung", "description": "Ich möchte starke Hilfe und weniger Reibung."},
                {"id": "medium", "label": "Mäßige Unterstützung", "description": "Ich kann einiges selbst regeln, aber nicht alles."},
                {"id": "low", "label": "Geringe Unterstützung", "description": "Ich löse Probleme gern selbst."},
            ],
        },
        {
            "id": "complexity",
            "label": "Wie viel Komplexität kannst du bewältigen?",
            "hint": "Einige Stile erfordern Planung, Anpassung, Unsicherheit und operativen Aufwand.",
            "options": [
                {"id": "low", "label": "Geringe Komplexität", "description": "Ich möchte eine leicht zu organisierende Reise."},
                {"id": "medium", "label": "Mittlere Komplexität", "description": "Ich kann einige bewegliche Teile handhaben."},
                {"id": "high", "label": "Hohe Komplexität", "description": "Ich kann Unsicherheit, Planung und Anpassung bewältigen."},
            ],
        },
        {
            "id": "depth",
            "label": "Wie tief soll die Erfahrung sein?",
            "hint": "Tiefe beschreibt, ob die Reise komfortabel, ausgewogen oder immersiv ist.",
            "options": [
                {"id": "surface", "label": "Leichte Erfahrung", "description": "Ich möchte Komfort, Einfachheit und ausgewählte Höhepunkte."},
                {"id": "balanced", "label": "Ausgewogene Erfahrung", "description": "Ich möchte Komfort und sinnvolle Begegnung."},
                {"id": "deep", "label": "Tiefe Erfahrung", "description": "Ich möchte Immersion und direkten Kontakt mit dem Ort."},
            ],
        },
        {
            "id": "predictability",
            "label": "Wie vorhersehbar soll die Reise sein?",
            "hint": "Vorhersehbarkeit beeinflusst Komfort, Risiko, Flexibilität und emotionale Belastung.",
            "options": [
                {"id": "high", "label": "Sehr vorhersehbar", "description": "Ich möchte Klarheit, bevor ich mich festlege."},
                {"id": "medium", "label": "Mäßig vorhersehbar", "description": "Ich akzeptiere etwas Unsicherheit."},
                {"id": "low", "label": "Wenig vorhersehbar", "description": "Ich begrüße Entdeckung, Mehrdeutigkeit und Veränderung."},
            ],
        },
    ],
    "zh": [
        {
            "id": "structure",
            "label": "你希望旅程有多少结构？",
            "hint": "结构决定旅程是计划明确、灵活，还是完全由你自主推动。",
            "options": [
                {"id": "high", "label": "高度结构化", "description": "我希望有明确计划、路线或运行框架。"},
                {"id": "balanced", "label": "平衡结构", "description": "我希望有结构，但不想过度僵化。"},
                {"id": "low", "label": "低结构", "description": "我希望旅程可以随着过程自由展开。"},
            ],
        },
        {
            "id": "autonomy",
            "label": "你希望有多少自主性？",
            "hint": "自主性衡量你想控制时间、移动和决策的程度。",
            "options": [
                {"id": "guided", "label": "低自主性", "description": "我希望很多决策由他人或系统处理。"},
                {"id": "mixed", "label": "共享自主性", "description": "我需要指导，但也希望保留真正选择。"},
                {"id": "high", "label": "高自主性", "description": "我希望直接控制体验本身。"},
            ],
        },
        {
            "id": "support",
            "label": "你需要多少支持？",
            "hint": "支持包括物流、安全、语言、本地接入和问题解决。",
            "options": [
                {"id": "high", "label": "高支持", "description": "我希望有强支持并减少摩擦。"},
                {"id": "medium", "label": "中等支持", "description": "我能处理一些事情，但不想全部自己承担。"},
                {"id": "low", "label": "低支持", "description": "我可以自己解决问题。"},
            ],
        },
        {
            "id": "complexity",
            "label": "你能处理多少复杂度？",
            "hint": "一些旅行方式需要计划、适应、不确定性和操作努力。",
            "options": [
                {"id": "low", "label": "低复杂度", "description": "我希望旅程容易操作。"},
                {"id": "medium", "label": "中等复杂度", "description": "我可以处理一些变化因素。"},
                {"id": "high", "label": "高复杂度", "description": "我可以处理不确定性、计划和适应。"},
            ],
        },
        {
            "id": "depth",
            "label": "你希望体验有多深？",
            "hint": "深度衡量旅程主要是舒适、平衡，还是沉浸式体验。",
            "options": [
                {"id": "surface", "label": "轻度体验", "description": "我想要舒适、轻松和精选亮点。"},
                {"id": "balanced", "label": "平衡体验", "description": "我想兼顾舒适与有意义的接触。"},
                {"id": "deep", "label": "深度体验", "description": "我想要沉浸、细节和与地点直接接触。"},
            ],
        },
        {
            "id": "predictability",
            "label": "旅程需要多可预测？",
            "hint": "可预测性影响舒适、风险、灵活性和情绪负担。",
            "options": [
                {"id": "high", "label": "高度可预测", "description": "我希望在决定前有清晰预期。"},
                {"id": "medium", "label": "中等可预测", "description": "我接受一定不确定性。"},
                {"id": "low", "label": "低可预测", "description": "我欢迎发现、模糊和变化。"},
            ],
        },
    ],
    "ja": [
        {
            "id": "structure",
            "label": "どの程度の構造を望みますか？",
            "hint": "構造は、旅が計画的、柔軟、または完全に自己主導かを決めます。",
            "options": [
                {"id": "high", "label": "高い構造", "description": "明確な計画、ルート、または運用枠組みが欲しい。"},
                {"id": "balanced", "label": "バランス型構造", "description": "構造は欲しいが、硬直的すぎるのは避けたい。"},
                {"id": "low", "label": "低い構造", "description": "旅の流れに合わせて自由に形作りたい。"},
            ],
        },
        {
            "id": "autonomy",
            "label": "どの程度の自律性を望みますか？",
            "hint": "自律性は、時間、移動、意思決定をどれだけ自分で制御したいかを示します。",
            "options": [
                {"id": "guided", "label": "低い自律性", "description": "多くの判断は他者や仕組みに任せたい。"},
                {"id": "mixed", "label": "共有型自律性", "description": "案内は欲しいが、意味のある選択も残したい。"},
                {"id": "high", "label": "高い自律性", "description": "体験を直接コントロールしたい。"},
            ],
        },
        {
            "id": "support",
            "label": "どの程度の支援が必要ですか？",
            "hint": "支援には、物流、安全、言語、現地アクセス、問題解決が含まれます。",
            "options": [
                {"id": "high", "label": "高い支援", "description": "強い支援と少ない摩擦を望む。"},
                {"id": "medium", "label": "中程度の支援", "description": "一部は自分で対応できるが、全部は避けたい。"},
                {"id": "low", "label": "低い支援", "description": "問題を自分で解決することに抵抗がない。"},
            ],
        },
        {
            "id": "complexity",
            "label": "どの程度の複雑さを扱えますか？",
            "hint": "一部のスタイルは、計画、適応、不確実性、運用努力を必要とします。",
            "options": [
                {"id": "low", "label": "低い複雑さ", "description": "運用しやすい旅にしたい。"},
                {"id": "medium", "label": "中程度の複雑さ", "description": "いくつかの変動要素には対応できる。"},
                {"id": "high", "label": "高い複雑さ", "description": "不確実性、計画、適応を扱える。"},
            ],
        },
        {
            "id": "depth",
            "label": "どの程度深い体験を望みますか？",
            "hint": "深度は、旅が快適中心、バランス型、または没入型かを示します。",
            "options": [
                {"id": "surface", "label": "軽い体験", "description": "快適さ、簡単さ、選ばれた見どころを重視したい。"},
                {"id": "balanced", "label": "バランス型体験", "description": "快適さと意味のある接触の両方が欲しい。"},
                {"id": "deep", "label": "深い体験", "description": "没入感、土地の質感、直接的な接触を求めたい。"},
            ],
        },
        {
            "id": "predictability",
            "label": "旅はどの程度予測可能であるべきですか？",
            "hint": "予測可能性は、快適さ、リスク、柔軟性、心理的負荷に影響します。",
            "options": [
                {"id": "high", "label": "高い予測可能性", "description": "決める前に明確さが欲しい。"},
                {"id": "medium", "label": "中程度の予測可能性", "description": "ある程度の不確実性は受け入れられる。"},
                {"id": "low", "label": "低い予測可能性", "description": "発見、曖昧さ、変化を歓迎する。"},
            ],
        },
    ],
}

ANSWER_SCORING: Dict[str, Dict[str, Dict[str, Any]]] = {
    "structure": {
        "high": {"criteria": {"predictability": 2.0, "operational_complexity": 1.5, "constraint_fit": 1.0}, "axes": {"structure_intensity": {"high": 3.0}, "pace_profile": {"fixed": 1.5}, "support_level": {"high": 1.0}}},
        "balanced": {"criteria": {"constraint_fit": 1.4, "traveler_type_fit": 1.2, "predictability": 0.8}, "axes": {"structure_intensity": {"medium": 2.0}, "pace_profile": {"balanced": 1.5}}},
        "low": {"criteria": {"depth_of_experience": 1.7, "control_vs_support": 1.5, "operational_complexity": -1.0}, "axes": {"structure_intensity": {"low": 2.4}, "pace_profile": {"flexible": 1.5}, "autonomy_level": {"high": 1.5}}},
    },
    "autonomy": {
        "guided": {"criteria": {"predictability": 1.6, "operational_complexity": 1.6, "constraint_fit": 1.0}, "axes": {"autonomy_level": {"low": 2.0}, "support_level": {"high": 2.0}}},
        "mixed": {"criteria": {"constraint_fit": 1.4, "traveler_type_fit": 1.2, "control_vs_support": 0.9}, "axes": {"autonomy_level": {"medium": 2.0}, "support_level": {"medium": 1.2}}},
        "high": {"criteria": {"control_vs_support": 2.0, "depth_of_experience": 1.5, "operational_complexity": -1.0}, "axes": {"autonomy_level": {"high": 2.8}, "support_level": {"low": 1.0}}},
    },
    "support": {
        "high": {"criteria": {"operational_complexity": 2.0, "predictability": 1.6, "constraint_fit": 1.2}, "axes": {"support_level": {"high": 2.8}, "predictability_profile": {"high": 1.2}}},
        "medium": {"criteria": {"constraint_fit": 1.4, "traveler_type_fit": 1.1}, "axes": {"support_level": {"medium": 2.0}, "predictability_profile": {"medium": 1.0}}},
        "low": {"criteria": {"control_vs_support": 1.8, "depth_of_experience": 1.4, "operational_complexity": -0.8}, "axes": {"support_level": {"low": 2.2}, "autonomy_level": {"high": 1.2}}},
    },
    "complexity": {
        "low": {"criteria": {"operational_complexity": 2.8, "predictability": 1.4, "constraint_fit": 1.0}, "axes": {"predictability_profile": {"high": 1.4}, "structure_intensity": {"high": 1.0}}},
        "medium": {"criteria": {"constraint_fit": 1.4, "traveler_type_fit": 1.2, "predictability": 0.6}, "axes": {"predictability_profile": {"medium": 1.2}, "structure_intensity": {"medium": 1.0}}},
        "high": {"criteria": {"operational_complexity": -2.0, "depth_of_experience": 1.6, "control_vs_support": 1.4}, "axes": {"pace_profile": {"flexible": 1.2}, "autonomy_level": {"high": 1.2}}},
    },
    "depth": {
        "surface": {"criteria": {"operational_complexity": 1.7, "predictability": 1.4, "constraint_fit": 1.0}, "axes": {"immersion_profile": {"surface": 2.0}, "support_level": {"high": 0.9}}},
        "balanced": {"criteria": {"constraint_fit": 1.3, "traveler_type_fit": 1.3, "depth_of_experience": 0.9}, "axes": {"immersion_profile": {"balanced": 2.0}}},
        "deep": {"criteria": {"depth_of_experience": 2.8, "control_vs_support": 1.2, "operational_complexity": -0.7}, "axes": {"immersion_profile": {"deep": 2.8}, "pace_profile": {"flexible": 0.9}}},
    },
    "predictability": {
        "high": {"criteria": {"predictability": 2.8, "operational_complexity": 1.5, "constraint_fit": 1.1}, "axes": {"predictability_profile": {"high": 2.8}, "structure_intensity": {"high": 0.9}}},
        "medium": {"criteria": {"constraint_fit": 1.4, "traveler_type_fit": 1.2, "predictability": 0.8}, "axes": {"predictability_profile": {"medium": 2.0}}},
        "low": {"criteria": {"depth_of_experience": 1.8, "control_vs_support": 1.5, "predictability": -1.2}, "axes": {"predictability_profile": {"low": 2.5}, "pace_profile": {"flexible": 1.0}}},
    },
}

CRITERIA_DIRECTIONS = {
    "constraint_fit": "higher",
    "operational_complexity": "lower",
    "control_vs_support": "higher",
    "depth_of_experience": "higher",
    "predictability": "higher",
    "traveler_type_fit": "higher",
}


TOOL_UI_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "scoreLabel": "Match score",
        "openLabel": "Open reference page",
        "alsoConsider": "Also consider",
        "progressTemplate": "{answered} of {total} questions answered",
    },
    "ar": {
        "scoreLabel": "درجة الملاءمة",
        "openLabel": "افتح الصفحة المرجعية",
        "alsoConsider": "ضع في الاعتبار أيضًا",
        "progressTemplate": "{answered} من {total} أسئلة تمت الإجابة عنها",
    },
    "fr": {
        "scoreLabel": "Score d’adéquation",
        "openLabel": "Ouvrir la page de référence",
        "alsoConsider": "À considérer aussi",
        "progressTemplate": "{answered} question(s) sur {total} répondue(s)",
    },
    "es": {
        "scoreLabel": "Puntuación de ajuste",
        "openLabel": "Abrir página de referencia",
        "alsoConsider": "También considerar",
        "progressTemplate": "{answered} de {total} preguntas respondidas",
    },
    "de": {
        "scoreLabel": "Passungswert",
        "openLabel": "Referenzseite öffnen",
        "alsoConsider": "Auch erwägen",
        "progressTemplate": "{answered} von {total} Fragen beantwortet",
    },
    "zh": {
        "scoreLabel": "匹配分数",
        "openLabel": "打开参考页面",
        "alsoConsider": "也可考虑",
        "progressTemplate": "已回答 {answered} / {total} 个问题",
    },
    "ja": {
        "scoreLabel": "適合スコア",
        "openLabel": "参照ページを開く",
        "alsoConsider": "こちらも検討",
        "progressTemplate": "{total}問中{answered}問回答済み",
    },
}


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise FindMatchConfigError(f"{label} must be a mapping/object.")
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
        raise FindMatchConfigError(f"site.base_url must be an absolute HTTPS URL. Got: {raw!r}")
    if parsed.query or parsed.fragment or (parsed.path or "") not in ("", "/"):
        raise FindMatchConfigError(f"site.base_url must not contain path, query, or fragment. Got: {raw!r}")
    return f"https://{parsed.netloc.rstrip('/')}"


def _extract_enabled_languages(site_config: Mapping[str, Any]) -> List[str]:
    raw = _get_nested(site_config, ("languages", "supported"), None)
    if not isinstance(raw, list):
        raw = _get_nested(site_config, ("languages", "enabled"), None)
    if not isinstance(raw, list):
        return list(SUPPORTED_LANGUAGES)
    languages: List[str] = []
    for item in raw:
        if isinstance(item, Mapping):
            code = _clean_string(item.get("code"))
            if item.get("enabled", True) is False:
                continue
        else:
            code = _clean_string(item)
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
        raise FindMatchConfigError(f"{label} must start with /static/: {public_path}")
    asset_path = (ROOT_DIR / public_path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise FindMatchConfigError(f"{label} points outside static/: {public_path}") from exc
    if not asset_path.is_file():
        raise FindMatchConfigError(f"{label} points to a missing static asset: {public_path}")
    return public_path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo"), {})
    if not isinstance(logo, Mapping):
        logo = {}
    icon_path = _clean_string(logo.get("icon_path"), default="/static/img/brand/logo-icon.webp")
    return _require_existing_asset(icon_path, "branding.logo.icon_path")


def _resolve_manifest_url() -> Optional[str]:
    return "/static/site.webmanifest" if (STATIC_DIR / "site.webmanifest").is_file() else None


def _fallback_questions(lang: str) -> List[Dict[str, Any]]:
    questions = QUESTION_COPY.get(lang, QUESTION_COPY["en"])
    normalized: List[Dict[str, Any]] = []
    for idx, question in enumerate(questions, start=1):
        q = dict(question)
        q["number"] = f"{idx:02d}"
        normalized.append(q)
    return normalized


def _style_items(payload: Mapping[str, Any]) -> List[Mapping[str, Any]]:
    for key in ("active_experience_types", "experience_types"):
        value = payload.get(key)
        if isinstance(value, list):
            items = [item for item in value if isinstance(item, Mapping)]
            if items:
                return items
    raise FindMatchConfigError("No experience types available for Find Your Match.")


def _normalize_style(item: Mapping[str, Any], lang: str) -> Dict[str, Any]:
    slug = _clean_string(item.get("slug"))
    if not slug:
        raise FindMatchConfigError("Experience type item missing slug.")
    title = _localized(item.get("title") or item.get("name") or item.get("label"), lang, default=slug.replace("-", " ").title())
    summary = _localized(item.get("summary") or item.get("description") or item.get("intro"), lang, default="A travel style inside the TourVsTravel reference system.")
    baseline_scores = item.get("baseline_scores") if isinstance(item.get("baseline_scores"), Mapping) else {}
    structural_axes = item.get("structural_axes") if isinstance(item.get("structural_axes"), Mapping) else {}
    return {
        "id": _clean_string(item.get("id"), default=slug),
        "slug": slug,
        "title": title,
        "summary": summary,
        "href": f"/{lang}/styles/{slug}/",
        "baseline_scores": {
            key: float(value) if isinstance(value, (int, float)) else 3.0
            for key, value in {criterion: baseline_scores.get(criterion, 3) for criterion in CRITERIA_DIRECTIONS}.items()
        },
        "structural_axes": {str(key): _clean_string(value) for key, value in structural_axes.items()},
    }


def _normalize_styles(payload: Mapping[str, Any], lang: str) -> List[Dict[str, Any]]:
    return [_normalize_style(item, lang) for item in _style_items(payload)]


def _method_cards(lang: str) -> List[Dict[str, str]]:
    cards: Dict[str, List[Dict[str, str]]] = {
        "en": [
            {"label": "Criteria", "value": "Answers weight the six TourVsTravel comparison criteria."},
            {"label": "Axes", "value": "Structural traits such as autonomy, support, and predictability refine the match."},
            {"label": "Output", "value": "The strongest style and nearby alternatives are shown with direct reference links."},
        ],
        "ar": [
            {"label": "المعايير", "value": "تمنح الإجابات أوزانًا لمعايير TourVsTravel الستة."},
            {"label": "المحاور", "value": "صفات مثل الاستقلالية والدعم وقابلية التوقع تضبط النتيجة."},
            {"label": "المخرج", "value": "يظهر أقوى نمط مع بدائل قريبة وروابط مرجعية مباشرة."},
        ],
        "fr": [
            {"label": "Critères", "value": "Les réponses pondèrent les six critères de comparaison TourVsTravel."},
            {"label": "Axes", "value": "L’autonomie, le soutien et la prévisibilité affinent le résultat."},
            {"label": "Sortie", "value": "Le style le plus fort et des alternatives proches sont affichés avec des liens directs."},
        ],
        "es": [
            {"label": "Criterios", "value": "Las respuestas ponderan los seis criterios de comparación de TourVsTravel."},
            {"label": "Ejes", "value": "Autonomía, apoyo y previsibilidad refinan el ajuste."},
            {"label": "Resultado", "value": "Se muestra el estilo más fuerte y alternativas cercanas con enlaces directos."},
        ],
        "de": [
            {"label": "Kriterien", "value": "Die Antworten gewichten die sechs TourVsTravel-Vergleichskriterien."},
            {"label": "Achsen", "value": "Autonomie, Unterstützung und Vorhersehbarkeit verfeinern die Passung."},
            {"label": "Ausgabe", "value": "Der stärkste Stil und nahe Alternativen werden mit direkten Referenzlinks gezeigt."},
        ],
        "zh": [
            {"label": "标准", "value": "答案会为 TourVsTravel 的六项比较标准赋予权重。"},
            {"label": "轴线", "value": "自主性、支持和可预测性等结构特征会细化匹配结果。"},
            {"label": "输出", "value": "显示最强匹配以及相近备选项，并提供直接参考链接。"},
        ],
        "ja": [
            {"label": "基準", "value": "回答は TourVsTravel の6つの比較基準に重みを与えます。"},
            {"label": "軸", "value": "自律性、支援、予測可能性などの構造的特徴が一致を調整します。"},
            {"label": "出力", "value": "最も強いスタイルと近い代替案が参照リンク付きで表示されます。"},
        ],
    }

    return cards.get(lang, cards["en"])


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
        raise FindMatchWriteError(f"Unable to write Find Your Match page {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise FindMatchWriteError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise FindMatchWriteError(f"Refusing symlink output directory: {resolved}")
    if resolved.parent.exists() and resolved.parent.is_symlink():
        raise FindMatchWriteError(f"Refusing symlink parent for output directory: {resolved.parent}")
    return resolved


def _build_hreflang(base_url: str, languages: Sequence[str]) -> List[Dict[str, str]]:
    return [{"lang": lang, "url": f"{base_url}/{lang}/tools/find-your-match/"} for lang in languages]


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
    questions = _fallback_questions(lang)
    styles = _normalize_styles(styles_payload, lang)
    tool_ui_copy = TOOL_UI_COPY.get(lang, TOOL_UI_COPY["en"])
    logo_url = _resolve_logo_path(site_config)
    canonical_url = f"{base_url}/{lang}/tools/find-your-match/"
    title = f"{copy['title']} | {site_name}"
    description = copy["lead"]
    seo_payload = _build_seo_payload(site_config=site_config, lang=lang, title=title, description=description, canonical_url=canonical_url, base_url=base_url, site_name=site_name, logo_url=logo_url, languages=languages)
    main_css_url = _require_existing_asset("/static/css/main.css", "main_css_url")
    main_js_url = _require_existing_asset("/static/js/main.js", "main_js_url")
    _require_existing_asset("/static/js/find-your-match.js", "find_match_js")

    return {
        "base_url": base_url,
        "lang": lang,
        "page_lang": lang,
        "current_lang": lang,
        "language": lang,
        "page_dir": _language_direction(site_config, lang),
        "is_rtl": _language_direction(site_config, lang) == "rtl",
        "body_class": "page-find-match",
        "current_year": datetime.now(timezone.utc).year,
        "site_name": site_name,
        "copy": copy,
        "questions": questions,
        "method_cards": _method_cards(lang),
        "style_count": len(styles),
        "tool_config": {
            "lang": lang,
            "copy": tool_ui_copy,
            "criteriaDirections": CRITERIA_DIRECTIONS,
            "answerScoring": ANSWER_SCORING,
            "styles": styles,
            "questionCount": len(questions),
        },
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
        "active_nav": "tools",
        "footer_note": "",
    }


def render_find_your_match_page(*, site_config: Mapping[str, Any], styles_payload: Mapping[str, Any], lang: str, languages: Sequence[str]) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise FindMatchRenderError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc
    try:
        html_output = template.render(**_build_context(site_config, styles_payload, lang, languages))
    except TemplateError as exc:
        raise FindMatchRenderError(f"Unable to render Find Your Match page [{lang}]: {exc}") from exc
    if not html_output.strip():
        raise FindMatchRenderError(f"Rendered Find Your Match page is empty for language {lang!r}.")
    return html_output


def generate_find_your_match_pages(*, requested_lang: Optional[str] = None, output_dir: Path = DEFAULT_OUTPUT_DIR) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise FindMatchConfigError("load_site_config() must return a mapping/object.")
    styles_payload = load_experience_types()
    if not isinstance(styles_payload, Mapping):
        raise FindMatchConfigError("load_experience_types() must return a mapping/object.")
    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise FindMatchConfigError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise FindMatchConfigError("No enabled languages available for Find Your Match generation.")

    rendered: List[tuple[Path, str, str]] = []
    for lang in languages:
        html_output = render_find_your_match_page(site_config=site_config, styles_payload=styles_payload, lang=lang, languages=languages)
        output_path = safe_output_dir / lang / "tools" / "find-your-match" / "index.html"
        rendered.append((output_path, html_output, lang))
    written: List[Path] = []
    for output_path, html_output, lang in rendered:
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated Find Your Match page [%s] -> %s", lang, output_path)
    log.info("Find Your Match generation completed successfully. Files written: %d", len(written))
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate multilingual TourVsTravel Find Your Match tool pages.")
    parser.add_argument("--lang", type=str, default=None, help="Generate one language only.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory root.")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    try:
        generate_find_your_match_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateFindYourMatchError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected Find Your Match generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
