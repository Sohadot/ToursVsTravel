#!/usr/bin/env python3
"""
TourVsTravel — Acquire pages
=============================
Generates:
  output/{lang}/acquire/index.html
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

log = logging.getLogger("generate_acquire")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/acquire.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

PAGE_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "title": "Acquire TourVsTravel",
        "lead": "TourVsTravel.com is a structured reference system built around the distinction between touring and traveling as different trip architectures. This page describes the asset for organizations evaluating acquisition.",
        "asset_label": "The Asset",
        "asset_body": "TourVsTravel.com is a static multilingual website covering six content areas: methodology, destination comparisons, trip-planning tools, destination guides, a reference report, and trust pages. The site is built on a Python-based static generator, deployed to GitHub Pages, and structured for multilingual SEO across seven languages. The domain captures a specific and semantically clear category distinction.",
        "name_label": "Name Value",
        "name_body": "The domain name expresses a binary category distinction that many travelers encounter but few reference systems address directly. It is noun-versus-noun, search-intent-aligned, and language-independent in meaning, which gives it utility for both direct search traffic and AI-assisted retrieval contexts.",
        "buyers_label": "Buyer Categories",
        "buyers_body": "Organizations that may have strategic interest include: travel content publishers expanding into structured reference formats; travel technology companies building trip-planning or itinerary tools; tourism boards seeking multilingual content infrastructure; academic or research entities focused on travel behavior classification.",
        "use_cases_label": "Use Cases",
        "use_cases_body": "Potential use cases include: retaining and extending the reference content under the existing domain; licensing the content structure and methodology for integration into a larger platform; redirecting domain equity into a related property; or using the multilingual infrastructure as a foundation for a new product.",
        "included_label": "What’s Included",
        "included_body": "The acquisition includes: the domain name (tourvstravel.com); the static site codebase including Python generators, Jinja2 templates, and build pipeline; the structured multilingual PAGE_COPY content in seven languages; the source policy, editorial standards, and methodology documentation; and the GitHub repository as structured.",
        "not_claimed_label": "What Is Not Claimed",
        "not_claimed_body": "No revenue, user volume, market share, or external endorsement is claimed or implied. The site is a structured reference build, not a monetized product. Traffic, ranking, and domain authority metrics should be independently verified by the buyer. No existing partnerships, affiliate arrangements, or data licensing agreements are in place.",
        "inquiry_label": "Qualified Inquiry Only",
        "inquiry_body": "Acquisition inquiries are accepted via the contact page. Please describe your organization type and intended use case. Speculative or undescribed inquiries will not receive a response.",
        "next_label": "Before You Reach Out",
        "ln_methodology": "Methodology",
        "ln_contact": "Contact",
    },
    "ar": {
        "title": "استحواذ TourVsTravel",
        "lead": "TourVsTravel.com نظام مرجعي منظم مبني على التمييز بين الجولات السياحية والسفر الحر كبنيتين مختلفتين للرحلات. تصف هذه الصفحة الأصل للمؤسسات التي تقيّم الاستحواذ.",
        "asset_label": "الأصل",
        "asset_body": "TourVsTravel.com موقع إلكتروني ثابت متعدد اللغات يغطي ستة مجالات للمحتوى: المنهجية، ومقارنات الوجهات، وأدوات التخطيط للرحلات، وأدلة الوجهات، وتقرير مرجعي، وصفحات الثقة. يُبنى الموقع على مولّد ثابت بلغة Python، ومنشور على GitHub Pages، ومهيكل لتحسين محركات البحث متعدد اللغات في سبع لغات. يعبّر اسم النطاق عن تمييز فئوي محدد وواضح دلالياً.",
        "name_label": "قيمة الاسم",
        "name_body": "يعبّر اسم النطاق عن تمييز فئوي ثنائي يواجهه كثير من المسافرين لكن قليلاً من الأنظمة المرجعية تتناوله مباشرةً. إنه اسم في مقابل اسم، متوافق مع نية البحث، ومعناه مستقل عن اللغة، مما يمنحه فائدة لكل من حركة البحث المباشر وسياقات الاسترجاع بمساعدة الذكاء الاصطناعي.",
        "buyers_label": "فئات المشترين",
        "buyers_body": "المؤسسات ذات الاهتمام الاستراتيجي المحتمل تشمل: ناشري محتوى السفر المتوسعين في تنسيقات المراجع المنظمة؛ وشركات تكنولوجيا السفر التي تبني أدوات تخطيط الرحلات؛ ومكاتب السياحة الساعية إلى بنية تحتية للمحتوى متعدد اللغات؛ والكيانات الأكاديمية أو البحثية المعنية بتصنيف سلوك السفر.",
        "use_cases_label": "حالات الاستخدام",
        "use_cases_body": "تشمل حالات الاستخدام المحتملة: الحفاظ على المحتوى المرجعي وتوسيعه تحت النطاق الحالي؛ أو ترخيص بنية المحتوى والمنهجية للتكامل مع منصة أكبر؛ أو إعادة توجيه رأس مال النطاق نحو عقار ذي صلة؛ أو استخدام البنية التحتية متعددة اللغات كأساس لمنتج جديد.",
        "included_label": "ما يشمله العرض",
        "included_body": "يشمل الاستحواذ: اسم النطاق (tourvstravel.com)؛ وقاعدة كود الموقع الثابت بما في ذلك مولدات Python وقوالب Jinja2 وخط أنابيب البناء؛ ومحتوى PAGE_COPY المنظم متعدد اللغات في سبع لغات؛ وسياسة المصادر ومعايير التحرير وتوثيق المنهجية؛ ومستودع GitHub كما هو منظم.",
        "not_claimed_label": "ما لا يُدّعى",
        "not_claimed_body": "لا يُدّعى أو يُلمح إلى أي إيرادات أو حجم مستخدمين أو حصة سوقية أو تأييد خارجي. الموقع بناء مرجعي منظم وليس منتجاً مدرّاً للدخل. يجب على المشتري التحقق بشكل مستقل من مقاييس حركة المرور والترتيب وسلطة النطاق. لا توجد شراكات قائمة أو ترتيبات تابعة أو اتفاقيات ترخيص بيانات.",
        "inquiry_label": "الاستفسارات المؤهلة فقط",
        "inquiry_body": "تُقبل استفسارات الاستحواذ عبر صفحة الاتصال. يرجى وصف نوع مؤسستك وحالة الاستخدام المقصودة. لن تتلقى الاستفسارات غير الموصوفة أو التكهنية أي رد.",
        "next_label": "قبل التواصل",
        "ln_methodology": "المنهجية",
        "ln_contact": "اتصل بنا",
    },
    "fr": {
        "title": "Acquérir TourVsTravel",
        "lead": "TourVsTravel.com est un système de référence structuré construit autour de la distinction entre les circuits organisés et les voyages libres comme deux architectures de voyage distinctes. Cette page décrit l'actif pour les organisations évaluant l'acquisition.",
        "asset_label": "L'actif",
        "asset_body": "TourVsTravel.com est un site web statique multilingue couvrant six domaines de contenu : méthodologie, comparaisons de destinations, outils de planification de voyage, guides de destinations, rapport de référence et pages de confiance. Le site est construit sur un générateur statique en Python, déployé sur GitHub Pages et structuré pour le référencement multilingue dans sept langues. Le nom de domaine capture une distinction de catégorie spécifique et sémantiquement claire.",
        "name_label": "Valeur du nom",
        "name_body": "Le nom de domaine exprime une distinction binaire de catégorie que de nombreux voyageurs rencontrent mais que peu de systèmes de référence abordent directement. C'est nom contre nom, aligné sur l'intention de recherche, et de sens indépendant de la langue, ce qui lui confère une utilité tant pour le trafic de recherche direct que pour les contextes de récupération assistée par IA.",
        "buyers_label": "Catégories d'acheteurs",
        "buyers_body": "Les organisations susceptibles d'avoir un intérêt stratégique comprennent : les éditeurs de contenu de voyage s'étendant aux formats de référence structurée ; les entreprises de technologie de voyage construisant des outils de planification d'itinéraires ; les offices de tourisme recherchant une infrastructure de contenu multilingue ; les entités académiques ou de recherche axées sur la classification du comportement de voyage.",
        "use_cases_label": "Cas d'utilisation",
        "use_cases_body": "Les cas d'utilisation potentiels comprennent : conserver et étendre le contenu de référence sous le domaine existant ; licencier la structure de contenu et la méthodologie pour l'intégration dans une plateforme plus grande ; réorienter l'équité du domaine vers une propriété connexe ; ou utiliser l'infrastructure multilingue comme fondation pour un nouveau produit.",
        "included_label": "Ce qui est inclus",
        "included_body": "L'acquisition comprend : le nom de domaine (tourvstravel.com) ; la base de code du site statique incluant les générateurs Python, les modèles Jinja2 et le pipeline de construction ; le contenu PAGE_COPY multilingue structuré dans sept langues ; la politique des sources, les normes éditoriales et la documentation méthodologique ; et le dépôt GitHub tel que structuré.",
        "not_claimed_label": "Ce qui n'est pas revendiqué",
        "not_claimed_body": "Aucun revenu, volume d'utilisateurs, part de marché ou approbation externe n'est revendiqué ou impliqué. Le site est une construction de référence structurée, non un produit monétisé. Les métriques de trafic, de classement et d'autorité de domaine doivent être vérifiées indépendamment par l'acheteur. Aucun partenariat existant, arrangement d'affiliation ou accord de licence de données n'est en place.",
        "inquiry_label": "Demandes qualifiées uniquement",
        "inquiry_body": "Les demandes d'acquisition sont acceptées via la page de contact. Veuillez décrire le type de votre organisation et le cas d'utilisation prévu. Les demandes spéculatives ou non décrites ne recevront pas de réponse.",
        "next_label": "Avant de nous contacter",
        "ln_methodology": "Méthodologie",
        "ln_contact": "Contact",
    },
    "es": {
        "title": "Adquirir TourVsTravel",
        "lead": "TourVsTravel.com es un sistema de referencia estructurado construido en torno a la distinción entre hacer un tour y viajar libremente como dos arquitecturas de viaje diferentes. Esta página describe el activo para las organizaciones que evalúan la adquisición.",
        "asset_label": "El activo",
        "asset_body": "TourVsTravel.com es un sitio web estático multilingüe que cubre seis áreas de contenido: metodología, comparaciones de destinos, herramientas de planificación de viajes, guías de destinos, informe de referencia y páginas de confianza. El sitio está construido sobre un generador estático en Python, desplegado en GitHub Pages y estructurado para SEO multilingüe en siete idiomas. El nombre de dominio captura una distinción de categoría específica y semánticamente clara.",
        "name_label": "Valor del nombre",
        "name_body": "El nombre de dominio expresa una distinción de categoría binaria que muchos viajeros encuentran pero que pocos sistemas de referencia abordan directamente. Es sustantivo contra sustantivo, alineado con la intención de búsqueda, y de significado independiente del idioma, lo que le confíere utilidad tanto para el tráfico de búsqueda directo como para los contextos de recuperación asistida por IA.",
        "buyers_label": "Categorías de compradores",
        "buyers_body": "Las organizaciones que pueden tener interés estratégico incluyen: editores de contenido de viajes que se expanden a formatos de referencia estructurados; empresas de tecnología de viajes que construyen herramientas de planificación de itinerarios; oficinas de turismo que buscan infraestructura de contenido multilingüe; entidades académicas o de investigación centradas en la clasificación del comportamiento de viaje.",
        "use_cases_label": "Casos de uso",
        "use_cases_body": "Los casos de uso potenciales incluyen: retener y ampliar el contenido de referencia bajo el dominio existente; licenciar la estructura de contenido y la metodología para integrarla en una plataforma mayor; redirigir el capital del dominio hacia una propiedad relacionada; o utilizar la infraestructura multilingüe como base para un nuevo producto.",
        "included_label": "Qué se incluye",
        "included_body": "La adquisición incluye: el nombre de dominio (tourvstravel.com); la base de código del sitio estático, incluidos los generadores Python, las plantillas Jinja2 y el pipeline de construcción; el contenido PAGE_COPY multilingüe estructurado en siete idiomas; la política de fuentes, los estándares editoriales y la documentación metodológica; y el repositorio de GitHub tal como está estructurado.",
        "not_claimed_label": "Lo que no se reclama",
        "not_claimed_body": "No se reclama ni implica ningún ingreso, volumen de usuarios, cuota de mercado o respaldo externo. El sitio es una construcción de referencia estructurada, no un producto monetizado. El comprador debe verificar de forma independiente las métricas de tráfico, clasificación y autoridad del dominio. No existen asociaciones, acuerdos de afiliación o contratos de licencia de datos.",
        "inquiry_label": "Solo consultas calificadas",
        "inquiry_body": "Las consultas de adquisición se aceptan a través de la página de contacto. Por favor, describa el tipo de su organización y el caso de uso previsto. Las consultas especulativas o sin descripción no recibirán respuesta.",
        "next_label": "Antes de contactarnos",
        "ln_methodology": "Metodología",
        "ln_contact": "Contacto",
    },
    "de": {
        "title": "TourVsTravel erwerben",
        "lead": "TourVsTravel.com ist ein strukturiertes Referenzsystem, das auf der Unterscheidung zwischen organisierten Touren und freiem Reisen als zwei verschiedenen Reisearchitekturen aufgebaut ist. Diese Seite beschreibt das Asset für Organisationen, die einen Erwerb prüfen.",
        "asset_label": "Das Asset",
        "asset_body": "TourVsTravel.com ist eine statische mehrsprachige Website, die sechs Inhaltsbereiche abdeckt: Methodik, Zielortvergleiche, Reiseplanungstools, Zielortsführer, Referenzbericht und Vertrauensseiten. Die Website basiert auf einem in Python entwickelten statischen Generator, ist auf GitHub Pages bereitgestellt und für mehrsprachiges SEO in sieben Sprachen strukturiert. Der Domainname erfässt eine spezifische und semantisch klare Kategorienunterscheidung.",
        "name_label": "Namenswert",
        "name_body": "Der Domainname drückt eine binäre Kategorienunterscheidung aus, mit der viele Reisende konfrontiert sind, die jedoch kaum ein Referenzsystem direkt adressiert. Es ist Substantiv gegen Substantiv, suchintentionskonform und bedeutungsmäßig sprachunabhängig, was ihm Nutzen sowohl für direkten Suchverkehr als auch für KI-gestützte Abrufkontexte verleiht.",
        "buyers_label": "Käuferkategorien",
        "buyers_body": "Organisationen mit möglichem strategischem Interesse sind: Reiseinhalts-Publisher, die strukturierte Referenzformate ausbauen; Reise-Technologieunternehmen, die Reiseplanungs- oder Itinerary-Tools entwickeln; Tourismusbüros, die mehrsprachige Inhaltsinfrastruktur suchen; akademische oder Forschungseinrichtungen mit Fokus auf Reiseverhaltensklassifikation.",
        "use_cases_label": "Anwendungsfälle",
        "use_cases_body": "Mögliche Anwendungsfälle umfassen: Beibehaltung und Erweiterung des Referenzinhalts unter der bestehenden Domain; Lizenzierung der Inhaltsstruktur und Methodik zur Integration in eine größere Plattform; Umleitung des Domain-Werts auf eine verwandte Eigenschaft; oder Nutzung der mehrsprachigen Infrastruktur als Grundlage für ein neues Produkt.",
        "included_label": "Was enthalten ist",
        "included_body": "Der Erwerb umfasst: den Domainnamen (tourvstravel.com); die statische Site-Codebasis einschließlich Python-Generatoren, Jinja2-Templates und Build-Pipeline; den strukturierten mehrsprachigen PAGE_COPY-Inhalt in sieben Sprachen; die Quellenrichtlinie, redaktionelle Standards und Methodikdokumentation; sowie das GitHub-Repository in seiner strukturierten Form.",
        "not_claimed_label": "Was nicht beansprucht wird",
        "not_claimed_body": "Es werden keine Einnahmen, Benutzervolumen, Marktanteile oder externe Bestätigungen beansprucht oder impliziert. Die Website ist ein strukturierter Referenz-Build, kein monetarisiertes Produkt. Traffic-, Ranking- und Domain-Authority-Metriken müssen vom Käufer unabhängig verifiziert werden. Es bestehen keine Partnerschaften, Affiliate-Vereinbarungen oder Datenlizenzverträge.",
        "inquiry_label": "Nur qualifizierte Anfragen",
        "inquiry_body": "Erwerbsanfragen werden über die Kontaktseite entgegengenommen. Bitte beschreiben Sie Ihren Organisationstyp und den beabsichtigten Anwendungsfall. Spekulative oder unbeschriebene Anfragen werden nicht beantwortet.",
        "next_label": "Bevor Sie sich melden",
        "ln_methodology": "Methodik",
        "ln_contact": "Kontakt",
    },
    "zh": {
        "title": "获取 TourVsTravel",
        "lead": "TourVsTravel.com 是一个结构化参考系统，建立在将跳团游与自由行作为两种不同旅行架构进行区分的基础上。本页面向评估收购事宜的机构描述该资产。",
        "asset_label": "资产描述",
        "asset_body": "TourVsTravel.com 是一个涵盖六个内容领域的静态多语言网站：方法论、目的地比较、旅行规划工具、目的地指南、参考报告及信任页面。该网站基于 Python 静态生成器构建，部署于 GitHub Pages，并针对七种语言的多语言 SEO 进行了结构化设计。域名捕捉了一个具体且语义清晰的类别区分。",
        "name_label": "名称价值",
        "name_body": "该域名表达了一种二元类别区分——许多旅行者都会遇到，但很少有参考系统直接处理。它是名词对名词、与搜索意图高度契合，且含义不依赖语言，这使其在直接搜索流量和 AI 辅助检索场景中均具有实用价值。",
        "buyers_label": "买家类别",
        "buyers_body": "可能具有战略兴趣的机构包括：扩展结构化参考格式的旅行内容发布商；构建行程规划工具的旅游科技公司；寻求多语言内容基础设施的旅游局；专注于旅行行为分类的学术或研究机构。",
        "use_cases_label": "使用场景",
        "use_cases_body": "潜在使用场景包括：在现有域名下保留并扩展参考内容；将内容结构和方法论授权集成到更大的平台；将域名权益引导至相关资产；或将多语言基础设施用作新产品的基础。",
        "included_label": "包含内容",
        "included_body": "收购包含：域名（tourvstravel.com）；静态网站代码库，包括 Python 生成器、Jinja2 模板和构建管道；七种语言的结构化多语言 PAGE_COPY 内容；来源政策、编辑标准和方法论文档；以及结构化的 GitHub 仓库。",
        "not_claimed_label": "不作声明的内容",
        "not_claimed_body": "不声明或暗示任何收入、用户量、市场份额或外部背书。本网站是结构化参考构建，而非变现产品。流量、排名和域名权威性指标应由买方独立核实。目前不存在任何合作伙伴关系、联盟安排或数据许可头张。",
        "inquiry_label": "仅接受合格询盘",
        "inquiry_body": "收购询盘请通过联系页面提交。请说明您的机构类型和预期使用场景。不描述具体意图的投机性询盘将不予回复。",
        "next_label": "联系我们之前",
        "ln_methodology": "方法论",
        "ln_contact": "联系我们",
    },
    "ja": {
        "title": "TourVsTravel の取得",
        "lead": "TourVsTravel.com は、ツアーと自由旅行を 2 つの異なる旅行設計として区別することを軸に構築された構造化参照システムです。このページは、取得を検討する組織向けにアセットを説明します。",
        "asset_label": "アセットの説明",
        "asset_body": "TourVsTravel.com は、6 つのコンテンツ領域をカバーする静的な多言語ウェブサイトです：方法論、目的地比較、旅行計画ツール、目的地ガイド、参照レポート、トラストページ。サイトは Python ベースの静的ジェネレーターで構築され、GitHub Pages にデプロイされ、7 言語での多言語 SEO に最適化された構造を持ちます。ドメイン名は、具体的かつ意味的に明確なカテゴリ区別を捕えています。",
        "name_label": "名前の価値",
        "name_body": "ドメイン名は、多くの旅行者が直面するにもかかわらず、ほとんどの参照システムが直接扱わない二項対立のカテゴリ区別を表しています。名詞対名詞の形式で、検索意図に沺い、意味が言語に依存しないため、直接検索トラフィックと AI 支援の検索コンテキストの両方で有用性を発揮します。",
        "buyers_label": "購入者カテゴリ",
        "buyers_body": "戰略的関心を持つ可能性のある組織には以下が含まれます：構造化参照形式に最展する旅行コンテンツパブリッシャー；旅程計画ツールを構築する旅行テクノロジー会社；多言語コンテンツインフラを求める観光局；旅行行動の分類に焦点を当てた学術・研究機関。",
        "use_cases_label": "ユースケース",
        "use_cases_body": "潜在的なユースケースには以下が含まれます：既存ドメインの下で参照コンテンツを維持・拡張する；コンテンツ構造と方法論をより大きなプラットフォームへの統合のためにライセンスする；ドメイン資産を関連資産に誘導する；または多言語インフラを新製品の基盤として活用する。",
        "included_label": "含まれる内容",
        "included_body": "取得には以下が含まれます：ドメイン名（tourvstravel.com）；Python ジェネレーター、Jinja2 テンプレート、ビルドパイプラインを含む静的サイトコードベース；7 言語の構造化多言語 PAGE_COPY コンテンツ；ソースポリシー、編集基準、方法論ドキュメント；および構造化された GitHub リポジトリ。",
        "not_claimed_label": "主張しないこと",
        "not_claimed_body": "収益、ユーザー数、市場シェア、外部推薦はいかなるものも主張・示唠しません。このサイトは構造化参照ビルドであり、収益化された製品ではありません。トラフィック、ランキング、ドメイン権威性指標は購入者が独自に検証してください。既存のパートナーシップ、アフィリエイト契約、データライセンス契約は存在しません。",
        "inquiry_label": "適格な問い合わせのみ",
        "inquiry_body": "取得に関するお問い合わせはコンタクトページから受け付けています。組織の種類と想定する使用目的をお記載ください。目的が不明確な投機的なお問い合わせにはお答えしません。",
        "next_label": "ご連絡の前に",
        "ln_methodology": "方法論",
        "ln_contact": "お問い合わせ",
    },
}


class GenerateAcquireError(Exception):
    pass


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateAcquireError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GenerateAcquireError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise GenerateAcquireError(f"{label} must not be empty.")
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
        raise GenerateAcquireError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise GenerateAcquireError(f"{label} escapes static directory: {path}") from exc
    if not asset_path.is_file():
        raise GenerateAcquireError(f"Missing static asset for {label}: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo_path"), "/static/img/brand/logo-icon.webp")
    return _ensure_string(logo, "branding.logo_path")


def _resolve_manifest_url() -> str:
    candidate = ROOT_DIR / "static" / "site.webmanifest"
    return "/static/site.webmanifest" if candidate.is_file() else ""


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise GenerateAcquireError(f"Missing templates directory: {TEMPLATES_DIR}")
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
        raise GenerateAcquireError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GenerateAcquireError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GenerateAcquireError(f"Refusing symlink output directory: {resolved}")
    return resolved


def _build_urls_by_lang(site_config: Mapping[str, Any], languages: Sequence[str]) -> Dict[str, str]:
    urls: Dict[str, str] = {}
    site = _ensure_mapping(site_config.get("site"), "site_config.site")
    raw_base = site.get("base_url", "https://tourvstravel.com")
    base = _ensure_string(raw_base, "site.base_url").rstrip("/")
    for code in languages:
        rel = build_acquire_path(site_config, code, absolute=False)
        urls[code] = f"{base}{rel}" if rel.startswith("/") else f"{base}/{rel}"
    return urls


def _build_context(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    copy = PAGE_COPY.get(lang, PAGE_COPY["en"])
    base_url = _ensure_string(
        _get_nested(site_config, ("site", "base_url"), "https://tourvstravel.com").strip().rstrip("/"),
        "site.base_url",
    )
    site_name = _extract_site_name(site_config, lang)
    logo_url = _resolve_logo_path(site_config)
    canonical_url = build_acquire_path(site_config, lang, absolute=True)
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
        "canonical_url": canonical_url,
        "seo": seo_payload,
        "hreflang": seo_payload.get("hreflang", []),
        "meta_desc": seo_payload.get("description", ""),
        "robots_directive": seo_payload.get("robots_directive", "index, follow"),
        "body_class": "page-acquire",
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
    }


def render_acquire_page(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise GenerateAcquireError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc
    context = _build_context(site_config=site_config, lang=lang, languages=languages)
    try:
        html_out = template.render(**context)
    except TemplateError as exc:
        raise GenerateAcquireError(f"Unable to render acquire page [{lang}]: {exc}") from exc
    if not html_out.strip():
        raise GenerateAcquireError(f"Rendered acquire page is empty for language {lang!r}.")
    return html_out


def generate_acquire_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise GenerateAcquireError("load_site_config() must return a mapping/object.")
    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise GenerateAcquireError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise GenerateAcquireError("No enabled languages available for acquire generation.")
    written: List[Path] = []
    for lang in languages:
        html_output = render_acquire_page(site_config=site_config, lang=lang, languages=languages)
        output_path = safe_output_dir / lang / "acquire" / "index.html"
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated acquire page [%s] -> %s", lang, output_path)
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TourVsTravel acquire pages.")
    parser.add_argument("--lang", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    try:
        generate_acquire_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateAcquireError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected acquire generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
