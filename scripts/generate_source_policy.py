#!/usr/bin/env python3
"""
TourVsTravel — Source policy pages
====================================
Generates:
  output/{lang}/methodology/source-policy/index.html
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

log = logging.getLogger("generate_source_policy")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/source_policy.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

PAGE_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "title": "Source Policy",
        "lead": "How TourVsTravel selects, evaluates, and cites information used in travel experience comparisons. This page distinguishes between factual sources, editorial classification, and interpretive judgment.",
        "accepted_label": "Accepted Sources",
        "accepted_body": "Accepted sources include: official tourism authority statistics and published government data; peer-reviewed academic research on travel behavior, destination planning, and tourism economics; publicly documented operator specifications (group size limits, itinerary structures, included services); and independently verifiable infrastructure data such as transport schedules and entry requirements from primary government sources.",
        "rejected_label": "Rejected Sources",
        "rejected_body": "The following are excluded from factual claims: unverifiable traveler anecdotes presented as general fact; marketing copy from tour operators or travel brands; sponsored or affiliate-linked content that cannot be independently corroborated; user review aggregates used without methodological context; and any source where commercial interest cannot be ruled out as a bias factor.",
        "claim_types_label": "Four Claim Types",
        "claim_types_body": "TourVsTravel distinguishes four types of claims, each treated differently: (1) Factual claims, sourced from verifiable primary data and cited explicitly; (2) Editorial classification, where the site assigns a label or category based on documented criteria; (3) Interpretive judgment, where the site draws a conclusion from multiple sources and flags it as such; (4) Acknowledged uncertainty, where the evidence is limited or conflicting and the page says so directly.",
        "destination_label": "Destination Claims",
        "destination_body": "Claims about specific destinations rely on primary sources: national tourism board data, peer-reviewed destination studies, and published infrastructure specifications. Where primary sources conflict, both positions are noted. Outdated data is flagged with a disclosure date.",
        "classification_label": "Classification Claims",
        "classification_body": "When TourVsTravel classifies a trip type, itinerary structure, or destination category, that classification reflects the site’s editorial framework, not an external standard. The methodology page documents the classification criteria. Classification is not presented as objective fact.",
        "uncertainty_label": "Uncertainty Handling",
        "uncertainty_body": "When evidence is limited, conflicting, or context-dependent, pages say so directly rather than presenting a false consensus. Comparative statements about traveler preferences or behavioral tendencies carry the caveat that individual outcomes vary and the site does not generalize from small or unrepresentative samples.",
        "update_label": "Updates and Corrections",
        "update_body": "Source data can become outdated. Pages that rely on time-sensitive data include a last-reviewed date where feasible. Corrections to factual errors are made when reported through the contact page. The correction does not delete the original claim but supersedes it with an explanation.",
        "no_affiliate_label": "No Affiliate Commitment",
        "no_affiliate_body": "TourVsTravel does not participate in affiliate programs, sponsored placements, or commercial partnerships that influence content. No operator, brand, or tourism authority has paid for inclusion, ranking, or favorable framing. This commitment applies to all content areas including comparisons, tools, and destination guides.",
        "see_also_label": "See also",
        "ln_methodology": "Methodology",
        "ln_editorial_standards": "Editorial Standards",
    },
    "ar": {
        "title": "سياسة المصادر",
        "lead": "كيف يختار TourVsTravel المعلومات المستخدمة في مقارنات تجارب السفر ويقيّمها ويستشهد بها. تُميّز هذه الصفحة بين المصادر الواقعية والتصنيف التحريري والحكم التفسيري.",
        "accepted_label": "المصادر المقبولة",
        "accepted_body": "تشمل المصادر المقبولة: إحصاءات هيئات السياحة الرسمية وبيانات الحكومة المنشورة؛ والأبحاث الأكاديمية المحكّمة حول سلوك السفر والتخطيط للوجهات؛ ومواصفات المشغّلين الموثقة علناً؛ وبيانات البنية التحتية القابلة للتحقّق من مصادر حكومية أولية.",
        "rejected_label": "المصادر المرفوضة",
        "rejected_body": "يُستثنى من الادعاءات الواقعية: الشهادات غير القابلة للتحقّق المقدّمة بوصفها حقيقة عامة؛ ومحتوى تسويقي من شركات الجولات أو علامات السفر؛ والمحتوى المدفوع أو المرتبط بعلاقات تسويق بالعمولة؛ وتجميعات التقييمات دون سياق منهجي.",
        "claim_types_label": "أربعة أنواع من الادعاءات",
        "claim_types_body": "يُميّز TourVsTravel بين أربعة أنواع من الادعاءات: (1) الادعاءات الواقعية، المستندة إلى بيانات أولية قابلة للتحقّق ومما يتم الاستشهاد بها صراحةً؛ (2) التصنيف التحريري، حيث يعيّن الموقع تسميةً أو فئةً بناءً على معايير موثقة؛ (3) الحكم التفسيري، حيث يستخلص الموقع نتيجةً من مصادر متعددة ويُشير إلى ذلك؛ (4) عدم اليقين، حيث تكون الأدلة محدودة أو متضاربة وتُفصح الصفحة عن ذلك مباشرةً.",
        "destination_label": "ادعاءات الوجهات",
        "destination_body": "تعتمد ادعاءات الوجهات المحددة على مصادر أولية: بيانات الهيئات السياحية الوطنية، ودراسات الوجهات المحكّمة، ومواصفات البنية التحتية المنشورة. عند تضارب المصادر الأولية، تُذكر كلا الموقفين. تتضمّن البيانات القديمة إفصاحًا بتاريخ الإفصاح.",
        "classification_label": "ادعاءات التصنيف",
        "classification_body": "عندما يُصنّف TourVsTravel نوع رحلة أو بنية جدول أعمال أو فئة وجهة، يعكس هذا التصنيف الإطار التحريري للموقع، وليس معيارًا خارجياً. تُوثّق صفحة المنهجية معايير التصنيف. لا يُقدّم التصنيف بوصفه حقيقة موضوعية.",
        "uncertainty_label": "التعامل مع عدم اليقين",
        "uncertainty_body": "عندما تكون الأدلة محدودة أو متضاربة أو تعتمد على السياق، تقول الصفحات ذلك صراحةً بدلاً من تقديم توافق زائف. تحمل التصريحات المقارنة حول تفضيلات المسافرين تحذيرًا بأن النتائج الفردية تتفاوت.",
        "update_label": "التحديثات والتصحيحات",
        "update_body": "قد تتقادم بيانات المصادر. تتضمّن الصفحات التي تعتمد على بيانات حساسة للوقت تاريخ آخر مراجعة حيثما أمكن. يُجرى تصحيح الأخطاء الواقعية عند الإبلاغ عنها عبر صفحة الاتصال. لا يحذف التصحيح الادعاء الأصلي بل يحل محله بتفسير.",
        "no_affiliate_label": "التزام عدم العمولة",
        "no_affiliate_body": "TourVsTravel لا يشارك في برامج العمولة أو المواضع المدفوعة أو الشراكات التجارية التي تؤثّر على المحتوى. لم يدفع أي مشغّل أو علامة أو هيئة سياحية مقابل إدراجها أو ترتيبها أو تأطيرها بصورة إيجابية. يسري هذا الالتزام على جميع مجالات المحتوى.",
        "see_also_label": "انظر أيضًا",
        "ln_methodology": "المنهجية",
        "ln_editorial_standards": "معايير التحرير",
    },
    "fr": {
        "title": "Politique de sources",
        "lead": "Comment TourVsTravel sélectionne, évalue et cite les informations utilisées dans les comparaisons d’expériences de voyage. Cette page distingue les sources factuelles, la classification éditoriale et le jugement interprétatif.",
        "accepted_label": "Sources acceptées",
        "accepted_body": "Les sources acceptées comprennent : les statistiques officielles des autorités touristiques et les données gouvernementales publiées ; la recherche académique évaluée par des pairs sur le comportement de voyage ; les spécifications d’opérateurs documentées publiquement ; et les données d’infrastructure vérifiables de sources gouvernementales primaires.",
        "rejected_label": "Sources refusées",
        "rejected_body": "Sont exclus des affirmations factuelles : les témoignages invérifiables présentés comme fait général ; le contenu marketing de voyagistes ou marques de voyage ; le contenu sponsorisé ou lié à des affiliations ne pouvant être corroboré indépendamment ; et les agrégats d’avis utilisés sans contexte méthodologique.",
        "claim_types_label": "Quatre types d’affirmations",
        "claim_types_body": "TourVsTravel distingue quatre types d’affirmations : (1) Affirmations factuelles, issues de données primaires vérifiables et citées explicitement ; (2) Classification éditoriale, où le site attribue une étiquette selon des critères documentés ; (3) Jugement interprétatif, où le site tire une conclusion de plusieurs sources et le signale ; (4) Incertitude reconnue, où les preuves sont limitées ou contradictoires et la page le dit directement.",
        "destination_label": "Affirmations sur les destinations",
        "destination_body": "Les affirmations sur des destinations spécifiques s’appuient sur des sources primaires : données des offices du tourisme nationaux, études de destinations évaluées par des pairs, et spécifications d’infrastructure publiées. En cas de conflit entre sources, les deux positions sont notées. Les données périmées sont signalées avec une date de divulgation.",
        "classification_label": "Affirmations de classification",
        "classification_body": "Lorsque TourVsTravel classe un type de voyage, une structure d’itinéraire ou une catégorie de destination, cette classification reflète le cadre éditorial du site, non un standard externe. La page de méthodologie documente les critères de classification. La classification n’est pas présentée comme un fait objectif.",
        "uncertainty_label": "Gestion de l’incertitude",
        "uncertainty_body": "Lorsque les preuves sont limitées, contradictoires ou dépendantes du contexte, les pages le disent directement plutôt que de présenter un faux consensus. Les affirmations comparatives sur les préférences des voyageurs portent la mise en garde que les résultats individuels varient.",
        "update_label": "Mises à jour et corrections",
        "update_body": "Les données sources peuvent devenir périmées. Les pages dépendant de données sensibles au temps incluent une date de dernière révision. Les corrections d’erreurs factuelles sont effectuées lorsqu’elles sont signalées via la page de contact. La correction ne supprime pas l’affirmation originale mais la remplace avec une explication.",
        "no_affiliate_label": "Engagement sans affiliation",
        "no_affiliate_body": "TourVsTravel ne participe à aucun programme d’affiliation, placement sponsorisé ou partenariat commercial influençant le contenu. Aucun opérateur, marque ou autorité touristique n’a payé pour une inclusion, un classement ou un cadrage favorable. Cet engagement s’applique à tous les domaines de contenu.",
        "see_also_label": "Voir aussi",
        "ln_methodology": "Méthodologie",
        "ln_editorial_standards": "Normes éditoriales",
    },
    "es": {
        "title": "Política de fuentes",
        "lead": "Cómo TourVsTravel selecciona, evalúa y cita la información utilizada en las comparaciones de experiencias de viaje. Esta página distingue entre fuentes factuales, clasificación editorial y juicio interpretativo.",
        "accepted_label": "Fuentes aceptadas",
        "accepted_body": "Las fuentes aceptadas incluyen: estadísticas oficiales de autoridades turísticas y datos gubernamentales publicados; investigación académica revisada por pares sobre comportamiento de viaje; especificaciones de operadores documentadas públicamente; y datos de infraestructura verificables de fuentes gubernamentales primarias.",
        "rejected_label": "Fuentes rechazadas",
        "rejected_body": "Se excluyen de las afirmaciones factuales: testimonios no verificables presentados como hecho general; contenido de marketing de operadores o marcas de viaje; contenido patrocinado o vinculado a afiliados que no puede corroborarse independientemente; y agregados de reseñas sin contexto metodológico.",
        "claim_types_label": "Cuatro tipos de afirmaciones",
        "claim_types_body": "TourVsTravel distingue cuatro tipos de afirmaciones: (1) Afirmaciones factuales, basadas en datos primarios verificables y citadas explícitamente; (2) Clasificación editorial, donde el sitio asigna una etiqueta según criterios documentados; (3) Juicio interpretativo, donde el sitio extrae una conclusión de múltiples fuentes y lo señala; (4) Incertidumbre reconocida, donde las pruebas son limitadas o contradictorias y la página lo dice directamente.",
        "destination_label": "Afirmaciones sobre destinos",
        "destination_body": "Las afirmaciones sobre destinos específicos se apoyan en fuentes primarias: datos de las juntas de turismo nacionales, estudios de destinos revisados por pares y especificaciones de infraestructura publicadas. Cuando las fuentes primarias entran en conflicto, se anotan ambas posiciones. Los datos desactualizados se señalan con una fecha de divulgación.",
        "classification_label": "Afirmaciones de clasificación",
        "classification_body": "Cuando TourVsTravel clasifica un tipo de viaje, una estructura de itinerario o una categoría de destino, esa clasificación refleja el marco editorial del sitio, no un estándar externo. La página de metodología documenta los criterios de clasificación. La clasificación no se presenta como hecho objetivo.",
        "uncertainty_label": "Manejo de la incertidumbre",
        "uncertainty_body": "Cuando las pruebas son limitadas, contradictorias o dependientes del contexto, las páginas lo dicen directamente en lugar de presentar un falso consenso. Las afirmaciones comparativas sobre preferencias de los viajeros llevan la advertencia de que los resultados individuales varían.",
        "update_label": "Actualizaciones y correcciones",
        "update_body": "Los datos de fuentes pueden quedar desactualizados. Las páginas que dependen de datos sensibles al tiempo incluyen una fecha de última revisión. Las correcciones de errores factuales se realizan cuando se informan a través de la página de contacto. La corrección no elimina la afirmación original sino que la reemplaza con una explicación.",
        "no_affiliate_label": "Compromiso sin afiliados",
        "no_affiliate_body": "TourVsTravel no participa en programas de afiliados, colocaciones patrocinadas ni asociaciones comerciales que influyan en el contenido. Ningún operador, marca o autoridad turística ha pagado por inclusión, clasificación o encuadre favorable. Este compromiso se aplica a todas las áreas de contenido.",
        "see_also_label": "Véase también",
        "ln_methodology": "Metodología",
        "ln_editorial_standards": "Estándares editoriales",
    },
    "de": {
        "title": "Quellenrichtlinie",
        "lead": "Wie TourVsTravel Informationen für Reiseerfahrungsvergleiche auswählt, bewertet und zitiert. Diese Seite unterscheidet zwischen faktischen Quellen, redaktioneller Klassifizierung und interpretativer Beurteilung.",
        "accepted_label": "Akzeptierte Quellen",
        "accepted_body": "Akzeptierte Quellen umfassen: offizielle Statistiken von Tourismusbehörden und veröffentlichte Regierungsdaten; von Experten begutachtete akademische Forschung zum Reiseverhalten; öffentlich dokumentierte Betreiberspezifikationen; und überprüfbare Infrastrukturdaten aus primären Regierungsquellen.",
        "rejected_label": "Abgelehnte Quellen",
        "rejected_body": "Von Tatsachenbehauptungen ausgeschlossen sind: nicht überprüfbare anekdotische Berichte, die als allgemeine Tatsache präsentiert werden; Marketinginhalte von Tourveranstaltern oder Reisemarken; gesponserte oder mit Affiliate-Links verbundene Inhalte, die nicht unabhängig bestätigt werden können; und Bewertungsaggregate ohne methodischen Kontext.",
        "claim_types_label": "Vier Behauptungstypen",
        "claim_types_body": "TourVsTravel unterscheidet vier Behauptungstypen: (1) Tatsächliche Behauptungen, aus überprüfbaren Primärdaten und explizit zitiert; (2) Redaktionelle Klassifizierung, bei der die Website anhand dokumentierter Kriterien eine Kategorie vergibt; (3) Interpretative Beurteilung, bei der die Website aus mehreren Quellen eine Schlussfolgerung zieht und dies kennzeichnet; (4) Anerkannte Unsicherheit, bei der die Beweise begrenzt oder widersprüchlich sind und die Seite dies direkt mitteilt.",
        "destination_label": "Zielortbezogene Behauptungen",
        "destination_body": "Behauptungen über spezifische Reiseziele stützen sich auf Primärquellen: Daten nationaler Tourismusbehörden, von Experten begutachtete Zielortsstudien und veröffentlichte Infrastrukturspezifikationen. Bei Konflikten zwischen Primärquellen werden beide Positionen vermerkt. Veraltete Daten werden mit einem Offenlegungsdatum gekennzeichnet.",
        "classification_label": "Klassifizierungsbehauptungen",
        "classification_body": "Wenn TourVsTravel einen Reisetyp, eine Reiseplanstruktur oder eine Zielortskategorie klassifiziert, spiegelt diese Klassifizierung den redaktionellen Rahmen der Website wider, keinen externen Standard. Die Methodikseite dokumentiert die Klassifizierungskriterien. Klassifizierungen werden nicht als objektive Tatsachen präsentiert.",
        "uncertainty_label": "Umgang mit Unsicherheit",
        "uncertainty_body": "Wenn Belege begrenzt, widersprüchlich oder kontextabhängig sind, sagen die Seiten dies direkt, anstatt einen falschen Konsens zu präsentieren. Vergleichende Aussagen über Reisendenpräferenzen tragen den Hinweis, dass individuelle Ergebnisse variieren.",
        "update_label": "Aktualisierungen und Korrekturen",
        "update_body": "Quelldaten können veralten. Seiten, die auf zeitkritischen Daten basieren, enthalten ein Datum der letzten Überprüfung. Korrekturen sachlicher Fehler werden vorgenommen, wenn sie über die Kontaktseite gemeldet werden. Die Korrektur löscht nicht die ursprüngliche Behauptung, sondern ersetzt sie mit einer Erklärung.",
        "no_affiliate_label": "Keine-Affiliate-Verpflichtung",
        "no_affiliate_body": "TourVsTravel nimmt nicht an Affiliate-Programmen, gesponserten Platzierungen oder kommerziellen Partnerschaften teil, die Inhalte beeinflussen. Kein Betreiber, keine Marke und keine Tourismusbehörde hat für Aufnahme, Ranking oder vorteilhafte Darstellung bezahlt. Diese Verpflichtung gilt für alle Inhaltsbereiche.",
        "see_also_label": "Siehe auch",
        "ln_methodology": "Methodik",
        "ln_editorial_standards": "Redaktionelle Standards",
    },
    "zh": {
        "title": "信息来源政策",
        "lead": "TourVsTravel 如何筛选、评估和引用旅行体验比较中使用的信息。本页区分事实性来源、编辑分类和解释性判断。",
        "accepted_label": "接受的来源",
        "accepted_body": "接受的来源包括：官方旅游局统计数据和政府公布数据；关于旅行行为的同行评审学术研究；公开记录的运营商规格；以及可从政府主要来源核实的基础设施数据。",
        "rejected_label": "拒绝的来源",
        "rejected_body": "以下内容被排除在事实性声明之外：以一般事实呼加但无法核实的轶事透露；旅游运营商或旅行品牌的营销文案；无法独立佐证的赞助或联盟内容；以及缺乏方法论背景的评分汇总。",
        "claim_types_label": "四种声明类型",
        "claim_types_body": "TourVsTravel 区分四种声明类型：（1）事实性声明，来自可核实的一手数据并明确引用；（2）编辑分类，网站根据有记录的标准指定标签或类别；（3）解释性判断，网站从多个来源得出结论并加以标注；（4）承认的不确定性，其中证据有限或相互矛盾，页面会直接说明这一点。",
        "destination_label": "目的地相关声明",
        "destination_body": "关于特定目的地的声明依赖一手来源：国家旅游局数据、同行评审目的地研究和已公布的基础设施规格。若一手来源冲突，两种立场均会注明。过时数据将伴随公开日期加以标注。",
        "classification_label": "分类声明",
        "classification_body": "当 TourVsTravel 对旅行类型、行程结构或目的地类别进行分类时，该分类反映网站的编辑框架，而非外部标准。方法论页面记录分类标准。分类不以客观事实的形式呈现。",
        "uncertainty_label": "不确定性处理",
        "uncertainty_body": "当证据有限、相互矛盾或依赖于背景时，页面会直接说明，而不是呈现虚假的共识。关于旅行者偏好的比较性陈述均附有警示，说明个体结果因人而异。",
        "update_label": "更新与勃正",
        "update_body": "来源数据可能过时。依赖时间敏感数据的页面尽可能注明最近审查日期。通过联系页面举报的事实性错误将得到勃正。勃正不会删除原始声明，而是附加说明加以更换。",
        "no_affiliate_label": "无联盟承诺",
        "no_affiliate_body": "TourVsTravel 不参与任何影响内容的联盟计划、赞助展示或商业合作。任何运营商、品牌或旅游局均未付费进行内容收录、排名或有利呈现。此承诺适用于所有内容领域。",
        "see_also_label": "另见",
        "ln_methodology": "方法论",
        "ln_editorial_standards": "编辑标准",
    },
    "ja": {
        "title": "情報源ポリシー",
        "lead": "TourVsTravel が旅行体验比較に使用する情報をどのように選択・評価・引用するかについて。このページは、事実情報源、編集分類、解釈的判断を区別します。",
        "accepted_label": "接受される情報源",
        "accepted_body": "接受される情報源には以下が含まれます：公式観光局の統計データおよび政府公開データ；旅行行動に関する査読済み学術研究；公開されたオペレーター仕様；および政府の一次情報源から検証可能なインフラデータ。",
        "rejected_label": "拒否される情報源",
        "rejected_body": "事実的主張から除外されるもの：一般的事実として提示される検証不能な軳話的証言；ツアー会示または旅行ブランドのマーケティングコピー；独立した補譌できないスポンサーまたはアフィリエイトコンテンツ；方法論的背景のないレビュー集計。",
        "claim_types_label": "4つの主張タイプ",
        "claim_types_body": "TourVsTravel は 4 つの主張タイプを区別します：（1）事実的主張 — 検証可能な一次データに基づき明示的に引用；（2）編集分類 — 文書化された基準に基づいてサイトがラベルまたはカテゴリを割り当てる；（3）解釈的判断 — サイトが複数の情報源から結論を導きその旨を示す；（4）承認された不確実性 — 証拠が限られたり矛盾したりする場合にページが直接その旨を伝える。",
        "destination_label": "目的地に関する主張",
        "destination_body": "特定の目的地に関する主張は一次情報源に依拠します：国家観光局データ、査読済み目的地研究、および公開されたインフラ仕様。一次情報源が矛盾する場合、両方の立場を記載します。古いデータには開示日付を追記します。",
        "classification_label": "分類に関する主張",
        "classification_body": "TourVsTravel が旅行タイプ、旅程構造、または目的地カテゴリを分類する際、その分類はサイトの編集フレームワークを反映しており、外部標準ではありません。方法論ページに分類基準を記載しています。分類は客観的事実として提示されません。",
        "uncertainty_label": "不確実性の扱い",
        "uncertainty_body": "証拠が限られた、矛盾する、または文脈依存型の場合、ページは虚假の共同認識を示すのではなく直接その旨を伝えます。旅行者の奇揮についての比較的記述には、個人の結果は異なるという注意事項を伴います。",
        "update_label": "更新と訂正",
        "update_body": "情報源データは古くなることがあります。時間に敗感なデータに依拠するページには、可能な限り最終確認日を記載します。事実誤りの訂正はコンタクトページから報告された際に行われます。訂正は元の主張を削除せず、説明を付けて置き換えます。",
        "no_affiliate_label": "アフィリエイトなしのコミットメント",
        "no_affiliate_body": "TourVsTravel はコンテンツに影響を与えるアフィリエイトプログラム、スポンサード掘載、商業的パートナーシップに参加していません。いかなるオペレーター、ブランド、観光局も掃載、ランキング、好意的な枠組みに対して对価を支払っていません。このコミットメントはすべてのコンテンツ領域に適用されます。",
        "see_also_label": "関連情報",
        "ln_methodology": "方法論",
        "ln_editorial_standards": "編集基準",
    },
}


class GenerateSourcePolicyError(Exception):
    pass


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GenerateSourcePolicyError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GenerateSourcePolicyError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise GenerateSourcePolicyError(f"{label} must not be empty.")
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
        raise GenerateSourcePolicyError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise GenerateSourcePolicyError(f"{label} escapes static directory: {path}") from exc
    if not asset_path.is_file():
        raise GenerateSourcePolicyError(f"Missing static asset for {label}: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo_path"), "/static/img/brand/logo-icon.webp")
    return _ensure_string(logo, "branding.logo_path")


def _resolve_manifest_url() -> str:
    candidate = ROOT_DIR / "static" / "site.webmanifest"
    return "/static/site.webmanifest" if candidate.is_file() else ""


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise GenerateSourcePolicyError(f"Missing templates directory: {TEMPLATES_DIR}")
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
        raise GenerateSourcePolicyError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GenerateSourcePolicyError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GenerateSourcePolicyError(f"Refusing symlink output directory: {resolved}")
    return resolved


def _build_urls_by_lang(site_config: Mapping[str, Any], languages: Sequence[str]) -> Dict[str, str]:
    urls: Dict[str, str] = {}
    site = _ensure_mapping(site_config.get("site"), "site_config.site")
    raw_base = site.get("base_url", "https://tourvstravel.com")
    base = _ensure_string(raw_base, "site.base_url").rstrip("/")
    for code in languages:
        rel = build_source_policy_path(site_config, code, absolute=False)
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
    canonical_url = build_source_policy_path(site_config, lang, absolute=True)
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
        "body_class": "page-source-policy",
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


def render_source_policy_page(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise GenerateSourcePolicyError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc
    context = _build_context(site_config=site_config, lang=lang, languages=languages)
    try:
        html_out = template.render(**context)
    except TemplateError as exc:
        raise GenerateSourcePolicyError(f"Unable to render source policy page [{lang}]: {exc}") from exc
    if not html_out.strip():
        raise GenerateSourcePolicyError(f"Rendered source policy page is empty for language {lang!r}.")
    return html_out


def generate_source_policy_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise GenerateSourcePolicyError("load_site_config() must return a mapping/object.")
    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise GenerateSourcePolicyError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise GenerateSourcePolicyError("No enabled languages available for source policy generation.")
    written: List[Path] = []
    for lang in languages:
        html_output = render_source_policy_page(site_config=site_config, lang=lang, languages=languages)
        output_path = safe_output_dir / lang / "methodology" / "source-policy" / "index.html"
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated source policy page [%s] -> %s", lang, output_path)
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TourVsTravel source policy pages.")
    parser.add_argument("--lang", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    try:
        generate_source_policy_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GenerateSourcePolicyError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected source policy generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
