#!/usr/bin/env python3
"""
TourVsTravel — Editorial standards pages
==========================================
Generates:
  output/{lang}/methodology/editorial-standards/index.html
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

log = logging.getLogger("generate_editorial_standards")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/editorial_standards.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

PAGE_COPY: Dict[str, Dict[str, Any]] = {
    "en": {
        "title": "Editorial Standards",
        "lead": "The principles that govern how TourVsTravel researches, writes, and publishes travel experience comparisons.",
        "neutrality_label": "Commercial neutrality",
        "neutrality_body": "TourVsTravel does not accept payment, sponsored placement, affiliate arrangements, or any commercial relationship that could influence the framing or ranking of any travel product, operator, or destination. Content is not produced for any party with a financial interest in the outcome.",
        "comparison_label": "Structural comparison, not ranking",
        "comparison_body": "Comparisons on this site describe structural differences between travel forms—what changes when you choose a group tour versus independent travel for the same destination. The site does not produce ranked lists of operators, destinations, or products. Structural analysis does not require ranking.",
        "constraint_label": "Stated constraints and scope",
        "constraint_body": "Each comparison page states what it covers and what it does not cover. Where a comparison is limited to a specific destination type, time period, or traveler profile, that limitation is disclosed. Overgeneralization is treated as an editorial error.",
        "no_best_label": "No 'best' claims",
        "no_best_body": "This site does not publish 'best of' lists, rankings, or recommendations. Travel form comparisons are structural: they describe what each option changes for a given trip, not which option is superior. The site does not resolve traveler preferences on behalf of the reader.",
        "tradeoffs_label": "Trade-off documentation",
        "tradeoffs_body": "Where a travel form offers an advantage in one dimension—cost, flexibility, depth of access, social experience—it typically involves a trade-off in another. This site documents both sides of each trade-off rather than presenting advantages without corresponding constraints.",
        "limits_label": "Acknowledged limits",
        "limits_body": "The site does not claim complete coverage of all destinations, travel forms, or traveler contexts. Where comparisons are based on a limited source base or apply only to a specific context, that is noted. Absence of coverage is not implied absence of relevance.",
        "ai_label": "AI and machine-readability",
        "ai_body": "TourVsTravel is structured to be interpretable by AI travel planning systems. Content is written for both human and machine readers. Source attribution, classification labels, and structured uncertainty disclosures are intentional to support AI retrieval contexts where content may be extracted without editorial framing.",
        "multilingual_label": "Multilingual equivalence",
        "multilingual_body": "Content is produced in seven languages. Translations are reviewed for substantive equivalence, not literal word-for-word translation. Where a term in one language does not have a direct equivalent in another, the closest structurally equivalent concept is used with a note where the divergence is material.",
        "see_also_label": "See also",
        "sections": [],
        "related_links": [
            ("Source policy", "url_source_policy"),
            ("Methodology", "url_methodology"),
            ("About", "url_about"),
            ("Contact", "url_contact"),
        ],
    },
    "ar": {
        "title": "معايير التحرير",
        "lead": "المبادئ التي تحكم كيفية بحث TourVsTravel وكتابة ونشر مقارنات تجارب السفر.",
        "neutrality_label": "الحياد التجاري",
        "neutrality_body": "لا يقبل TourVsTravel أي مدفوعات أو مواضع مموَّلة أو ترتيبات عمولة أو أي علاقة تجارية قد تؤثّر في صياغة أو ترتيب أي منتج سفر أو مشغّل أو وجهة. لا يُنتج المحتوى لأي طرف له مصلحة مالية في النتيجة.",
        "comparison_label": "مقارنة هيكلية وليس تصنيفاً",
        "comparison_body": "تصف المقارنات في هذا الموقع الفروقات الهيكلية بين أشكال السفر—ما الذي يتغيّر عند اختيار جولة جماعية مقابل السفر المستقل لنفس الوجهة. لا يُنتج الموقع قوائم مرتّبة من المشغّلين أو الوجهات أو المنتجات.",
        "constraint_label": "القيود والنطاق المُصرَّح به",
        "constraint_body": "تُوضح كل صفحة مقارنة ما تغطيه وما لا تغطيه. حيث تقتصر المقارنة على نوع وجهة محددة أو فترة زمنية أو ملف تعريف مسافر، يُكشف عن هذا القيد. يُعدّ التعميم المفرط خطأً تحريرياً.",
        "no_best_label": "لا ادعاءات بـ'الأفضل'",
        "no_best_body": "لا ينشر هذا الموقع قوائم 'الأفضل' أو تصنيفات أو توصيات. مقارنات أشكال السفر هيكلية: تصف ما يغيّره كل خيار في رحلة معينة، لا أيها أفضل. لا يحسم الموقع تفضيلات المسافرين نيابةً عن القارئ.",
        "tradeoffs_label": "توثيق المقايضات",
        "tradeoffs_body": "حيث يوفّر شكل سفر ميزةً في بُعد ما—التكلفة أو المرونة أو عمق الوصول أو التجربة الاجتماعية—فإن ذلك يستلزم عادةً مقايضةً في بُعد آخر. يوثّق هذا الموقع الجانبين لكل مقايضة.",
        "limits_label": "القيود المُعترف بها",
        "limits_body": "لا يدّعي الموقع التغطية الكاملة لجميع الوجهات أو أشكال السفر أو سياقات المسافرين. حيث تستند المقارنات إلى قاعدة مصادر محدودة أو تنطبق على سياق محدد، يُشار إلى ذلك.",
        "ai_label": "الذكاء الاصطناعي وقابلية القراءة الآلية",
        "ai_body": "هُيكِل TourVsTravel ليكون قابلاً للتفسير من أنظمة تخطيط السفر بالذكاء الاصطناعي. يُكتب المحتوى للقرّاء البشريين والآليين على حدٍّ سواء. إسناد المصادر وتسميات التصنيف وإفصاحات عدم اليقين المهيكلة مقصودة لدعم سياقات الاسترجاع بالذكاء الاصطناعي.",
        "multilingual_label": "التكافؤ متعدد اللغات",
        "multilingual_body": "يُنتج المحتوى بسبع لغات. تُراجَع الترجمات للتكافؤ الجوهري وليس الترجمة الحرفية. حيث لا يوجد لمصطلح في لغة ما مقابل مباشر في لغة أخرى، يُستخدم المفهوم المكافئ هيكلياً الأقرب مع ملاحظة حيثما يكون الاختلاف جوهرياً.",
        "see_also_label": "انظر أيضًا",
        "sections": [],
        "related_links": [
            ("سياسة المصادر", "url_source_policy"),
            ("المنهجية", "url_methodology"),
            ("حول الموقع", "url_about"),
            ("اتصل بنا", "url_contact"),
        ],
    },
    "fr": {
        "title": "Normes éditoriales",
        "lead": "Les principes qui régissent la façon dont TourVsTravel recherche, rédige et publie les comparaisons d’expériences de voyage.",
        "neutrality_label": "Neutralité commerciale",
        "neutrality_body": "TourVsTravel n’accepte pas de paiement, de placement sponsorisé, d’arrangements d’affiliation ou toute relation commerciale susceptible d’influencer le cadrage ou le classement d’un produit de voyage, d’un opérateur ou d’une destination. Le contenu n’est pas produit pour une partie ayant un intérêt financier dans le résultat.",
        "comparison_label": "Comparaison structurelle, pas de classement",
        "comparison_body": "Les comparaisons sur ce site décrivent les différences structurelles entre les formes de voyage—ce qui change lorsque vous choisissez un tour en groupe plutôt qu’un voyage indépendant pour la même destination. Le site ne produit pas de listes classées d’opérateurs, de destinations ou de produits.",
        "constraint_label": "Contraintes et portée déclarées",
        "constraint_body": "Chaque page de comparaison indique ce qu’elle couvre et ce qu’elle ne couvre pas. Lorsqu’une comparaison est limitée à un type de destination, une période ou un profil de voyageur, cette limitation est divulguée. La surgénéralisation est traitée comme une erreur éditoriale.",
        "no_best_label": "Pas de revendications ‘meilleur’",
        "no_best_body": "Ce site ne publie pas de listes ‘meilleur de’, de classements ou de recommandations. Les comparaisons de formes de voyage sont structurelles : elles décrivent ce que chaque option change pour un voyage donné, pas laquelle est supérieure. Le site ne résout pas les préférences des voyageurs au nom du lecteur.",
        "tradeoffs_label": "Documentation des compromis",
        "tradeoffs_body": "Lorsqu’une forme de voyage offre un avantage dans une dimension—coût, flexibilité, profondeur d’accès, expérience sociale—elle implique généralement un compromis dans une autre. Ce site documente les deux côtés de chaque compromis.",
        "limits_label": "Limites reconnues",
        "limits_body": "Le site ne prétend pas à une couverture complète de toutes les destinations, formes de voyage ou contextes de voyageurs. Lorsque les comparaisons sont basées sur une base de sources limitée ou s’appliquent uniquement à un contexte spécifique, cela est noté.",
        "ai_label": "IA et lisibilité machine",
        "ai_body": "TourVsTravel est structuré pour être interprétable par les systèmes de planification de voyage IA. Le contenu est rédigé pour les lecteurs humains et machines. L’attribution de sources, les étiquettes de classification et les divulgations d’incertitude structurées sont intentionnelles pour soutenir les contextes de récupération IA.",
        "multilingual_label": "Équivalence multilingue",
        "multilingual_body": "Le contenu est produit dans sept langues. Les traductions sont vérifiées pour une équivalence substantielle, pas une traduction mot à mot littérale. Lorsqu’un terme n’a pas d’équivalent direct dans une autre langue, le concept structurellement équivalent le plus proche est utilisé.",
        "see_also_label": "Voir aussi",
        "sections": [],
        "related_links": [
            ("Politique de sources", "url_source_policy"),
            ("Méthodologie", "url_methodology"),
            ("À propos", "url_about"),
            ("Contact", "url_contact"),
        ],
    },
    "es": {
        "title": "Estándares editoriales",
        "lead": "Los principios que rigen cómo TourVsTravel investiga, escribe y publica comparaciones de experiencias de viaje.",
        "neutrality_label": "Neutralidad comercial",
        "neutrality_body": "TourVsTravel no acepta pagos, colocaciones patrocinadas, acuerdos de afiliados ni ninguna relación comercial que pueda influir en el encuadre o la clasificación de cualquier producto de viaje, operador o destino. El contenido no se produce para ninguna parte con interés financiero en el resultado.",
        "comparison_label": "Comparación estructural, no clasificación",
        "comparison_body": "Las comparaciones en este sitio describen las diferencias estructurales entre las formas de viaje—qué cambia cuando se elige un tour en grupo frente a un viaje independiente para el mismo destino. El sitio no produce listas clasificadas de operadores, destinos o productos.",
        "constraint_label": "Restricciones y alcance declarados",
        "constraint_body": "Cada página de comparación indica lo que cubre y lo que no cubre. Cuando una comparación está limitada a un tipo de destino, período de tiempo o perfil de viajero, esa limitación se divulga. La sobregeneralización se trata como un error editorial.",
        "no_best_label": "Sin afirmaciones de 'mejor'",
        "no_best_body": "Este sitio no publica listas de 'lo mejor de', clasificaciones ni recomendaciones. Las comparaciones de formas de viaje son estructurales: describen qué cambia cada opción para un viaje dado, no cuál es superior. El sitio no resuelve las preferencias de los viajeros en nombre del lector.",
        "tradeoffs_label": "Documentación de compensaciones",
        "tradeoffs_body": "Cuando una forma de viaje ofrece una ventaja en una dimensión—costo, flexibilidad, profundidad de acceso, experiencia social—generalmente implica una compensación en otra. Este sitio documenta ambos lados de cada compensación.",
        "limits_label": "Límites reconocidos",
        "limits_body": "El sitio no reclama cobertura completa de todos los destinos, formas de viaje o contextos de viajeros. Donde las comparaciones se basan en una base de fuentes limitada o se aplican solo a un contexto específico, se indica.",
        "ai_label": "IA y legibilidad por máquina",
        "ai_body": "TourVsTravel está estructurado para ser interpretable por sistemas de planificación de viajes con IA. El contenido está escrito para lectores humanos y de máquinas. La atribución de fuentes, las etiquetas de clasificación y las divulgaciones de incertidumbre estructuradas apoyan los contextos de recuperación de IA.",
        "multilingual_label": "Equivalencia multilingüe",
        "multilingual_body": "El contenido se produce en siete idiomas. Las traducciones se revisan para equivalencia sustantiva, no traducción literal. Cuando un término en un idioma no tiene un equivalente directo en otro, se usa el concepto estructuralmente equivalente más cercano.",
        "see_also_label": "Véase también",
        "sections": [],
        "related_links": [
            ("Política de fuentes", "url_source_policy"),
            ("Metodología", "url_methodology"),
            ("Acerca de", "url_about"),
            ("Contacto", "url_contact"),
        ],
    },
    "de": {
        "title": "Redaktionelle Standards",
        "lead": "Die Grundsätze, die regeln, wie TourVsTravel Reiseerfahrungsvergleiche recherchiert, schreibt und veröffentlicht.",
        "neutrality_label": "Kommerzielle Neutralität",
        "neutrality_body": "TourVsTravel akzeptiert keine Zahlungen, gesponserten Platzierungen, Affiliate-Vereinbarungen oder andere kommerzielle Beziehungen, die das Framing oder Ranking von Reiseprodukten, Betreibern oder Reisezielen beeinflussen könnten. Inhalte werden nicht für Parteien mit finanziellem Interesse am Ergebnis produziert.",
        "comparison_label": "Struktureller Vergleich, kein Ranking",
        "comparison_body": "Vergleiche auf dieser Website beschreiben strukturelle Unterschiede zwischen Reiseformen—was sich ändert, wenn man für dasselbe Reiseziel eine Gruppenreise statt einer individuellen Reise wählt. Die Website erstellt keine Ranglisten von Betreibern, Reisezielen oder Produkten.",
        "constraint_label": "Dargelegte Einschränkungen und Umfang",
        "constraint_body": "Jede Vergleichsseite gibt an, was sie abdeckt und was nicht. Wenn ein Vergleich auf einen bestimmten Zielorttyp, Zeitraum oder Reisendenprofil beschränkt ist, wird diese Einschränkung offengelegt. Übergeneralisierung wird als redaktioneller Fehler behandelt.",
        "no_best_label": "Keine 'Besten'-Behauptungen",
        "no_best_body": "Diese Website veröffentlicht keine 'Besten'-Listen, Rankings oder Empfehlungen. Reiseformvergleiche sind strukturell: Sie beschreiben, was jede Option für eine gegebene Reise verändert, nicht welche Option überlegen ist. Die Website löst keine Reisendenpräferenzen im Namen des Lesers.",
        "tradeoffs_label": "Dokumentation von Kompromissen",
        "tradeoffs_body": "Wenn eine Reiseform einen Vorteil in einer Dimension bietet—Kosten, Flexibilität, Zugriffstiefe, soziale Erfahrung—geht dies typischerweise mit einem Kompromiss in einer anderen einher. Diese Website dokumentiert beide Seiten jedes Kompromisses.",
        "limits_label": "Anerkannte Grenzen",
        "limits_body": "Die Website erhebt keinen Anspruch auf vollständige Abdeckung aller Reiseziele, Reiseformen oder Reisendenkontexte. Wenn Vergleiche auf einer begrenzten Quellenbasis basieren oder nur für einen spezifischen Kontext gelten, wird dies angemerkt.",
        "ai_label": "KI und Maschinenlesbarkeit",
        "ai_body": "TourVsTravel ist strukturiert, um von KI-Reiseplanungssystemen interpretierbar zu sein. Inhalte werden für menschliche und maschinelle Leser geschrieben. Quellenattribuierung, Klassifizierungslabels und strukturierte Unsicherheitsoffenlegungen unterstützen KI-Abrufkontexte.",
        "multilingual_label": "Mehrsprachige Äquivalenz",
        "multilingual_body": "Inhalte werden in sieben Sprachen produziert. Übersetzungen werden auf sachliche Äquivalenz geprüft, nicht auf wörtliche Übersetzung. Wenn ein Begriff in einer Sprache kein direktes Äquivalent hat, wird das strukturell nächstäquivalente Konzept verwendet.",
        "see_also_label": "Siehe auch",
        "sections": [],
        "related_links": [
            ("Quellenrichtlinie", "url_source_policy"),
            ("Methodik", "url_methodology"),
            ("Über uns", "url_about"),
            ("Kontakt", "url_contact"),
        ],
    },
    "zh": {
        "title": "编辑标准",
        "lead": "规范 TourVsTravel 研究、撰写和发布旅行体验比较内容的原则。",
        "neutrality_label": "商业中立性",
        "neutrality_body": "TourVsTravel 不接受任何可能影响旅行产品、运营商或目的地排名或呈现方式的付款、赞助展示、联盟安排或其他商业关系。内容不为结果有财务利益的任何方面制作。",
        "comparison_label": "结构比较，而非排名",
        "comparison_body": "本站的比较描述旅行形式之间的结构差异——当你为同一目的地选择跟团游而非自由行时，什么会发生变化。本站不生成运营商、目的地或产品的排名列表。",
        "constraint_label": "已声明的限制和范围",
        "constraint_body": "每个比较页面都说明其涵盖的内容和不涵盖的内容。若比较仅限于特定目的地类型、时间段或旅行者档案，该限制将予以披露。过度概括被视为编辑错误。",
        "no_best_label": "无'最佳'声明",
        "no_best_body": "本站不发布'最佳'列表、排名或建议。旅行形式比较是结构性的：描述每种选择对特定旅行的改变，而非哪种更优越。本站不代读者决定旅行者偏好。",
        "tradeoffs_label": "权衡文档",
        "tradeoffs_body": "当某种旅行形式在某一维度上提供优势——费用、灵活性、访问深度、社交体验——通常在另一维度上涉及权衡。本站记录每个权衡的两面。",
        "limits_label": "已承认的局限",
        "limits_body": "本站不声称对所有目的地、旅行形式或旅行者背景的完整覆盖。若比较基于有限的信息来源或仅适用于特定背景，将予以注明。",
        "ai_label": "AI与机器可读性",
        "ai_body": "TourVsTravel 的结构设计便于 AI 旅行规划系统解读。内容同时面向人类读者和机器读者撰写。来源归属、分类标签和结构化的不确定性披露支持 AI 检索背景下的内容提取。",
        "multilingual_label": "多语言等效性",
        "multilingual_body": "内容以七种语言制作。翻译经过实质等效性审查，而非逐字直译。若某语言中的术语在另一语言中没有直接对应词，则使用结构上最接近的等效概念。",
        "see_also_label": "另见",
        "sections": [],
        "related_links": [
            ("信息来源政策", "url_source_policy"),
            ("方法论", "url_methodology"),
            ("关于我们", "url_about"),
            ("联系我们", "url_contact"),
        ],
    },
    "ja": {
        "title": "編集基準",
        "lead": "TourVsTravel が旅行体験比較を調査・執筆・公開する方法を規定する原則について。",
        "neutrality_label": "商業的中立性",
        "neutrality_body": "TourVsTravel は、旅行商品・オペレーター・目的地のフレーミングやランキングに影響しうる支払い、スポンサード掲載、アフィリエイト契約、その他の商業的関係を一切受け付けません。コンテンツは、結果に財務的利害を持つ当事者のために制作されません。",
        "comparison_label": "構造的比較、ランキングではない",
        "comparison_body": "このサイトの比較は、旅行形態間の構造的な違いを説明します――同じ目的地でグループツアーと個人旅行を選んだ場合に何が変わるかを示します。このサイトはオペレーター、目的地、商品のランキングリストを作成しません。",
        "constraint_label": "明示された制約と適用範囲",
        "constraint_body": "各比較ページは、対象範囲と対象外を明示しています。比較が特定の目的地タイプ、時期、旅行者プロフィールに限定される場合、その制限は開示されます。過度な一般化は編集上の誤りとして扱われます。",
        "no_best_label": "「最高」の主張なし",
        "no_best_body": "このサイトは「ベスト」リスト、ランキング、推薦を公開しません。旅行形態の比較は構造的なものです：特定の旅行において各選択肢が何を変えるかを説明するものであり、どちらが優れているかを示すものではありません。",
        "tradeoffs_label": "トレードオフの文書化",
        "tradeoffs_body": "ある旅行形態がある側面で優位性を持つ場合——費用、柔軟性、アクセスの深さ、社会的体験——通常は別の側面でのトレードオフを伴います。このサイトは各トレードオフの両面を文書化します。",
        "limits_label": "認められた限界",
        "limits_body": "このサイトは、すべての目的地、旅行形態、旅行者の文脈を完全にカバーすることを主張しません。比較が限られた情報源に基づいている、または特定の文脈にのみ適用される場合、その旨を記載します。",
        "ai_label": "AIと機械可読性",
        "ai_body": "TourVsTravel は、AI旅行計画システムで解釈可能な構造を持っています。コンテンツは人間と機械の両方の読者向けに書かれています。情報源の帰属、分類ラベル、構造化された不確実性の開示はAI検索コンテキストをサポートします。",
        "multilingual_label": "多言語の等価性",
        "multilingual_body": "コンテンツは7言語で制作されています。翻訳は逐語的な翻訳ではなく、実質的な等価性についてレビューされます。ある言語の用語が別の言語に直接対応する表現がない場合、構造的に最も近い等価概念を使用します。",
        "see_also_label": "関連情報",
        "sections": [],
        "related_links": [
            ("情報源ポリシー", "url_source_policy"),
            ("方法論", "url_methodology"),
            ("私たちについて", "url_about"),
            ("お問い合わせ", "url_contact"),
        ],
    },
}


_REQUIRED_COPY_KEYS = (
    "title", "lead",
    "neutrality_label", "neutrality_body",
    "comparison_label", "comparison_body",
    "constraint_label", "constraint_body",
    "no_best_label", "no_best_body",
    "tradeoffs_label", "tradeoffs_body",
    "limits_label", "limits_body",
    "ai_label", "ai_body",
    "multilingual_label", "multilingual_body",
    "see_also_label", "sections", "related_links",
)


class GenerateEditorialStandardsError(Exception):
    pass


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateEditorialStandardsError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GenerateEditorialStandardsError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise GenerateEditorialStandardsError(f"{label} must not be empty.")
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
        raise GenerateEditorialStandardsError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise GenerateEditorialStandardsError(f"{label} escapes static directory: {path}") from exc
    if not asset_path.is_file():
        raise GenerateEditorialStandardsError(f"Missing static asset for {label}: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo_path"), "/static/img/brand/logo-icon.webp")
    return _ensure_string(logo, "branding.logo_path")


def _resolve_manifest_url() -> str:
    candidate = ROOT_DIR / "static" / "site.webmanifest"
    return "/static/site.webmanifest" if candidate.is_file() else ""


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise GenerateEditorialStandardsError(f"Missing templates directory: {TEMPLATES_DIR}")
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
        raise GenerateEditorialStandardsError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GenerateEditorialStandardsError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GenerateEditorialStandardsError(f"Refusing symlink output directory: {resolved}")
    return resolved


def _validate_copy(copy: Dict[str, Any], lang: str) -> None:
    for key in _REQUIRED_COPY_KEYS:
        if key not in copy:
            raise GenerateEditorialStandardsError(f"editorial standards page content missing {key!r} for {lang!r}")


def _build_urls_by_lang(site_config: Mapping[str, Any], languages: Sequence[str]) -> Dict[str, str]:
    urls: Dict[str, str] = {}
    site = _ensure_mapping(site_config.get("site"), "site_config.site")
    raw_base = site.get("base_url", "https://tourvstravel.com")
    base = _ensure_string(raw_base, "site.base_url").rstrip("/")
    for code in languages:
        rel = build_editorial_standards_path(site_config, code, absolute=False)
        urls[code] = f"{base}{rel}" if rel.startswith("/") else f"{base}/{rel}"
    return urls


def _build_context(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    copy = PAGE_COPY.get(lang, PAGE_COPY["en"])
    _validate_copy(copy, lang)
    base_url = _ensure_string(
        _get_nested(site_config, ("site", "base_url"), "https://tourvstravel.com").strip().rstrip("/"),
        "site.base_url",
    )
    site_name = _extract_site_name(site_config, lang)
    logo_url = _resolve_logo_path(site_config)
    canonical_url = build_editorial_standards_path(site_config, lang, absolute=True)
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
        "body_class": "page-editorial-standards",
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
            "url_source_policy": build_source_policy_path(site_config, lang, absolute=False),
            "url_methodology": build_methodology_path(site_config, lang, absolute=False),
            "url_about": build_about_path(site_config, lang, absolute=False),
            "url_contact": build_contact_path(site_config, lang, absolute=False),
        },
    }
    context.update(localized_ui_context(lang))
    return context


def render_editorial_standards_page(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise GenerateEditorialStandardsError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc
    context = _build_context(site_config=site_config, lang=lang, languages=languages)
    try:
        html_out = template.render(**context)
    except TemplateError as exc:
        raise GenerateEditorialStandardsError(f"Unable to render editorial standards page [{lang}]: {exc}") from exc
    if not html_out.strip():
        raise GenerateEditorialStandardsError(f"Rendered editorial standards page is empty for language {lang!r}.")
    return html_out


def generate_editorial_standards_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise GenerateEditorialStandardsError("load_site_config() must return a mapping/object.")
    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise GenerateEditorialStandardsError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise GenerateEditorialStandardsError("No enabled languages available for editorial standards generation.")
    written: List[Path] = []
    for lang in languages:
        html_output = render_editorial_standards_page(site_config=site_config, lang=lang, languages=languages)
        output_path = safe_output_dir / lang / "methodology" / "editorial-standards" / "index.html"
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated editorial standards page [%s] -> %s", lang, output_path)
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TourVsTravel editorial standards pages.")
    parser.add_argument("--lang", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    try:
        generate_editorial_standards_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateEditorialStandardsError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected editorial standards generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
