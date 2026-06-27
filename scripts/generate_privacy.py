#!/usr/bin/env python3
"""
TourVsTravel — Privacy pages
=============================
Generates:
  output/{lang}/privacy/index.html
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

log = logging.getLogger("generate_privacy")

ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DEFAULT_OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATE_NAME = "pages/privacy.html"
SUPPORTED_LANGUAGES = ("en", "ar", "fr", "es", "de", "zh", "ja")

PAGE_COPY: Dict[str, Dict[str, str]] = {
    "en": {
        "title": "Privacy",
        "lead": "TourVsTravel is a static reference site. We do not collect personal data, run user accounts, process payments, or operate advertising networks.",
        "static_label": "Static site architecture",
        "static_body": (
            "This site is statically generated from source files and served from GitHub Pages. "
            "There is no application server, no database, no session management, and no server-side "
            "processing of user requests. Every page you receive is a pre-built HTML file."
        ),
        "no_accounts_label": "No accounts",
        "no_accounts_body": (
            "TourVsTravel has no user registration, no login, no saved preferences, and no subscription "
            "system. There is no account of any kind to create or maintain."
        ),
        "no_payment_label": "No transactions",
        "no_payment_body": (
            "This site does not process payments, handle billing information, or connect to payment "
            "gateways. No financial data of any kind passes through this infrastructure."
        ),
        "no_tracking_label": "No tracking or advertising",
        "no_tracking_body": (
            "We do not set tracking cookies, use advertising networks, run analytics pixels, or share "
            "data with third-party ad platforms. Note: GitHub Pages, which hosts this site, is governed "
            "by GitHub’s own privacy policy. Their infrastructure processes HTTP requests to serve "
            "these files, subject to their terms."
        ),
        "tools_label": "Interactive tools",
        "tools_body": (
            "Comparison tools and calculators on this site run entirely in your browser as client-side "
            "JavaScript. No input you provide to these tools is transmitted to any server. Data stays "
            "local to your browser session and is discarded when you navigate away."
        ),
        "future_label": "Future changes",
        "future_body": (
            "If this site’s privacy posture ever changes—for example, if analytics or server-side "
            "features were added—this page will be updated before those changes take effect, not after."
        ),
        "contact_label": "Questions",
        "contact_body": "For privacy-related questions, use the",
        "contact_link": "contact page",
    },
    "ar": {
        "title": "الخصوصية",
        "lead": "TourVsTravel موقع مرجعي ثابت. لا نجمع بيانات شخصية، ولا نشغّل حسابات مستخدمين، ولا نعالج مدفوعات، ولا نشغّل شبكات إعلانية.",
        "static_label": "بنية الموقع الثابت",
        "static_body": (
            "يُنشأ هذا الموقع بشكل ثابت من ملفات المصدر ويُقدَّم من GitHub Pages. "
            "لا يوجد خادم تطبيقات، ولا قاعدة بيانات، ولا إدارة للجلسات، ولا معالجة من جانب الخادم لطلبات المستخدمين. "
            "كل صفحة تتلقاها هي ملف HTML مُنشأ مسبقاً."
        ),
        "no_accounts_label": "لا حسابات",
        "no_accounts_body": (
            "لا يوجد في TourVsTravel تسجيل للمستخدمين، ولا تسجيل دخول، ولا تفضيلات محفوظة، ولا نظام اشتراكات. "
            "لا يوجد أي نوع من الحسابات لإنشائه أو صيانته."
        ),
        "no_payment_label": "لا معاملات مالية",
        "no_payment_body": (
            "لا يعالج هذا الموقع المدفوعات ولا يتعامل مع معلومات الفوترة ولا يتصل ببوابات الدفع. "
            "لا تمر أي بيانات مالية من أي نوع عبر هذه البنية التحتية."
        ),
        "no_tracking_label": "لا تتبع ولا إعلانات",
        "no_tracking_body": (
            "لا نضع ملفات تعريف الارتباط للتتبع، ولا نستخدم شبكات إعلانية، ولا نشغّل وحدات بكسل للتحليلات، ولا نشارك البيانات مع منصات إعلانية تابعة لجهات خارجية. "
            "ملاحظة: GitHub Pages، الذي يستضيف هذا الموقع، يخضع لسياسة خصوصية GitHub الخاصة. "
            "تعالج بنيتها التحتية طلبات HTTP لتقديم هذه الملفات، وفقاً لشروطها."
        ),
        "tools_label": "الأدوات التفاعلية",
        "tools_body": (
            "تعمل أدوات المقارنة والحاسبات الموجودة في هذا الموقع بالكامل في متصفحك كـ JavaScript من جانب العميل. "
            "لا يُرسَل أي إدخال تقدمه لهذه الأدوات إلى أي خادم. "
            "تبقى البيانات محلية في جلسة متصفحك وتُتجاهَل عند الانتقال بعيداً."
        ),
        "future_label": "التغييرات المستقبلية",
        "future_body": (
            "إذا تغيّر موقف هذا الموقع من الخصوصية في أي وقت—على سبيل المثال، إذا أُضيفت تحليلات أو ميزات من جانب الخادم—"
            "سيُحدَّث هذا الصفحة قبل دخول تلك التغييرات حيز التنفيذ، لا بعد ذلك."
        ),
        "contact_label": "الاستفسارات",
        "contact_body": "للأسئلة المتعلقة بالخصوصية، استخدم",
        "contact_link": "صفحة الاتصال",
    },
    "fr": {
        "title": "Confidentialité",
        "lead": "TourVsTravel est un site de référence statique. Nous ne collectons pas de données personnelles, ne gérons pas de comptes utilisateurs, ne traitons pas de paiements et n’exploitons pas de réseaux publicitaires.",
        "static_label": "Architecture de site statique",
        "static_body": (
            "Ce site est généré statiquement à partir de fichiers sources et servi depuis GitHub Pages. "
            "Il n’y a pas de serveur applicatif, pas de base de données, pas de gestion de session et "
            "pas de traitement côté serveur des requêtes utilisateurs. Chaque page que vous recevez est "
            "un fichier HTML pré-construit."
        ),
        "no_accounts_label": "Aucun compte",
        "no_accounts_body": (
            "TourVsTravel ne propose pas d’inscription, de connexion, de préférences enregistrées ni "
            "de système d’abonnement. Il n’existe aucun type de compte à créer ou à maintenir."
        ),
        "no_payment_label": "Aucune transaction",
        "no_payment_body": (
            "Ce site ne traite pas de paiements, ne gère pas d’informations de facturation et ne se "
            "connecte à aucune passerelle de paiement. Aucune donnée financière ne transite par cette "
            "infrastructure."
        ),
        "no_tracking_label": "Aucun suivi ni publicité",
        "no_tracking_body": (
            "Nous ne déposons pas de cookies de suivi, n’utilisons pas de réseaux publicitaires, "
            "n’exécutons pas de pixels analytiques et ne partageons pas de données avec des plateformes "
            "publicitaires tierces. Note : GitHub Pages, qui héberge ce site, est régi par la propre "
            "politique de confidentialité de GitHub. Leur infrastructure traite les requêtes HTTP pour "
            "servir ces fichiers, conformément à leurs conditions."
        ),
        "tools_label": "Outils interactifs",
        "tools_body": (
            "Les outils de comparaison et calculateurs présents sur ce site fonctionnent entièrement "
            "dans votre navigateur en tant que JavaScript côté client. Aucune donnée saisie dans ces "
            "outils n’est transmise à un serveur. Les données restent locales à votre session de "
            "navigation et sont supprimées lorsque vous quittez la page."
        ),
        "future_label": "Modifications futures",
        "future_body": (
            "Si la politique de confidentialité de ce site change un jour—par exemple, si des analyses "
            "ou des fonctionnalités côté serveur étaient ajoutées—cette page sera mise à jour avant "
            "que ces changements prennent effet, et non après."
        ),
        "contact_label": "Questions",
        "contact_body": "Pour les questions relatives à la confidentialité, utilisez la",
        "contact_link": "page de contact",
    },
    "es": {
        "title": "Privacidad",
        "lead": "TourVsTravel es un sitio de referencia estático. No recopilamos datos personales, no gestionamos cuentas de usuario, no procesamos pagos ni operamos redes publicitarias.",
        "static_label": "Arquitectura de sitio estático",
        "static_body": (
            "Este sitio se genera de forma estática a partir de archivos fuente y se sirve desde GitHub Pages. "
            "No hay servidor de aplicaciones, ni base de datos, ni gestión de sesiones, ni procesamiento "
            "del lado del servidor de las solicitudes de los usuarios. Cada página que recibe es un archivo "
            "HTML pre-construido."
        ),
        "no_accounts_label": "Sin cuentas",
        "no_accounts_body": (
            "TourVsTravel no tiene registro de usuarios, inicio de sesión, preferencias guardadas ni "
            "sistema de suscripción. No existe ningún tipo de cuenta que crear o mantener."
        ),
        "no_payment_label": "Sin transacciones",
        "no_payment_body": (
            "Este sitio no procesa pagos, no maneja información de facturación ni se conecta a pasarelas "
            "de pago. Ningún dato financiero de ningún tipo pasa por esta infraestructura."
        ),
        "no_tracking_label": "Sin seguimiento ni publicidad",
        "no_tracking_body": (
            "No establecemos cookies de seguimiento, no usamos redes publicitarias, no ejecutamos píxeles "
            "de análisis ni compartimos datos con plataformas publicitarias de terceros. Nota: GitHub Pages, "
            "que aloja este sitio, se rige por la propia política de privacidad de GitHub. Su infraestructura "
            "procesa solicitudes HTTP para servir estos archivos, sujeto a sus términos."
        ),
        "tools_label": "Herramientas interactivas",
        "tools_body": (
            "Las herramientas de comparación y calculadoras de este sitio se ejecutan completamente en su "
            "navegador como JavaScript del lado del cliente. Ninguna entrada que proporcione a estas "
            "herramientas se transmite a ningún servidor. Los datos permanecen locales en su sesión del "
            "navegador y se descartan cuando navega a otra página."
        ),
        "future_label": "Cambios futuros",
        "future_body": (
            "Si la postura de privacidad de este sitio cambia alguna vez—por ejemplo, si se añaden "
            "análisis o funciones del lado del servidor—esta página se actualizará antes de que esos "
            "cambios entren en vigor, no después."
        ),
        "contact_label": "Preguntas",
        "contact_body": "Para preguntas relacionadas con la privacidad, utilice la",
        "contact_link": "página de contacto",
    },
    "de": {
        "title": "Datenschutz",
        "lead": "TourVsTravel ist eine statische Referenzwebsite. Wir erheben keine personenbezogenen Daten, betreiben keine Benutzerkonten, verarbeiten keine Zahlungen und betreiben keine Werbenetzwerke.",
        "static_label": "Statische Website-Architektur",
        "static_body": (
            "Diese Website wird statisch aus Quelldateien generiert und über GitHub Pages bereitgestellt. "
            "Es gibt keinen Anwendungsserver, keine Datenbank, keine Sitzungsverwaltung und keine "
            "serverseitige Verarbeitung von Benutzeranfragen. Jede Seite, die Sie erhalten, ist eine "
            "vorgefertigte HTML-Datei."
        ),
        "no_accounts_label": "Keine Konten",
        "no_accounts_body": (
            "TourVsTravel hat keine Benutzerregistrierung, kein Login, keine gespeicherten Einstellungen "
            "und kein Abonnement-System. Es gibt keinerlei Konto, das erstellt oder gepflegt werden "
            "müsste."
        ),
        "no_payment_label": "Keine Transaktionen",
        "no_payment_body": (
            "Diese Website verarbeitet keine Zahlungen, verwaltet keine Abrechnungsdaten und ist nicht "
            "mit Zahlungs-Gateways verbunden. Keinerlei Finanzdaten werden über diese Infrastruktur "
            "übermittelt."
        ),
        "no_tracking_label": "Kein Tracking oder Werbung",
        "no_tracking_body": (
            "Wir setzen keine Tracking-Cookies, nutzen keine Werbenetzwerke, betreiben keine "
            "Analyse-Pixel und geben keine Daten an Drittanbieter-Werbeplattformen weiter. Hinweis: "
            "GitHub Pages, das diese Website hostet, unterliegt der eigenen Datenschutzrichtlinie von "
            "GitHub. Ihre Infrastruktur verarbeitet HTTP-Anfragen zur Bereitstellung dieser Dateien "
            "gemäß ihren Bedingungen."
        ),
        "tools_label": "Interaktive Werkzeuge",
        "tools_body": (
            "Vergleichstools und Rechner auf dieser Website laufen vollständig in Ihrem Browser als "
            "clientseitiges JavaScript. Keine Eingabe, die Sie in diese Tools machen, wird an einen "
            "Server übermittelt. Die Daten bleiben lokal in Ihrer Browser-Sitzung und werden verworfen, "
            "wenn Sie die Seite verlassen."
        ),
        "future_label": "Zukünftige Änderungen",
        "future_body": (
            "Falls sich die Datenschutzposition dieser Website ändert—zum Beispiel wenn Analysen oder "
            "serverseitige Funktionen hinzugefügt würden—wird diese Seite vor Inkrafttreten dieser "
            "Änderungen aktualisiert, nicht danach."
        ),
        "contact_label": "Fragen",
        "contact_body": "Für datenschutzbezogene Fragen nutzen Sie bitte die",
        "contact_link": "Kontaktseite",
    },
    "zh": {
        "title": "隐私政策",
        "lead": "TourVsTravel 是一个静态参考网站。我们不收集个人数据，不运营用户账户，不处理付款，也不运营广告网络。",
        "static_label": "静态网站架构",
        "static_body": (
            "本站由源文件静态生成，通过 GitHub Pages 提供服务。没有应用程序服务器、数据库、会话管理，也没有对用户请求的服务器端处理。"
            "您收到的每个页面都是预先构建的 HTML 文件。"
        ),
        "no_accounts_label": "无账户",
        "no_accounts_body": (
            "TourVsTravel 没有用户注册、登录、保存的偏好设置或订阅系统。没有任何类型的账户可以创建或维护。"
        ),
        "no_payment_label": "无交易",
        "no_payment_body": (
            "本站不处理付款，不处理账单信息，也不连接支付网关。没有任何类型的财务数据通过此基础设施传输。"
        ),
        "no_tracking_label": "无追踪或广告",
        "no_tracking_body": (
            "我们不设置追踪 Cookie，不使用广告网络，不运行分析像素，也不与第三方广告平台共享数据。注意：托管本站的 GitHub Pages 受 GitHub "
            "自己的隐私政策约束。其基础设施处理 HTTP 请求以提供这些文件，遵循其服务条款。"
        ),
        "tools_label": "交互工具",
        "tools_body": (
            "本站的比较工具和计算器完全在您的浏览器中作为客户端 JavaScript 运行。您向这些工具输入的任何内容都不会传输到任何服务器。"
            "数据保留在您浏览器会话的本地，当您离开页面时即被丢弃。"
        ),
        "future_label": "未来变更",
        "future_body": (
            "如果本站的隐私立场发生变化——例如添加了分析功能或服务器端功能——本页面将在这些变更生效之前更新，而不是之后。"
        ),
        "contact_label": "问题",
        "contact_body": "如有隐私相关问题，请使用",
        "contact_link": "联系页面",
    },
    "ja": {
        "title": "プライバシー",
        "lead": "TourVsTravel は静的な参照サイトです。個人データの収集、ユーザーアカウントの管理、支払い処理、広告ネットワークの運営は一切行っておりません。",
        "static_label": "静的サイトのアーキテクチャ",
        "static_body": (
            "このサイトはソースファイルから静的に生成され、GitHub Pages から提供されています。アプリケーションサーバー、データベース、セッション管理、"
            "またはユーザーリクエストのサーバーサイド処理はありません。受信するすべてのページは事前に構築された HTML ファイルです。"
        ),
        "no_accounts_label": "アカウントなし",
        "no_accounts_body": (
            "TourVsTravel にはユーザー登録、ログイン、保存された設定、またはサブスクリプションシステムはありません。"
            "作成または維持すべきいかなる種類のアカウントも存在しません。"
        ),
        "no_payment_label": "取引なし",
        "no_payment_body": (
            "このサイトは支払いの処理、請求情報の取り扱い、または支払いゲートウェイへの接続は行いません。"
            "いかなる財務データもこのインフラを通過しません。"
        ),
        "no_tracking_label": "トラッキングや広告なし",
        "no_tracking_body": (
            "トラッキング Cookie の設定、広告ネットワークの使用、分析ピクセルの実行、サードパーティ広告プラットフォームへのデータ共有は一切行っておりません。"
            "注意：このサイトをホストする GitHub Pages は、GitHub 独自のプライバシーポリシーに準拠しています。彼らのインフラはこれらのファイルを提供するために "
            "HTTP リクエストを処理しますが、それは彼らの利用規約に従ったものです。"
        ),
        "tools_label": "インタラクティブツール",
        "tools_body": (
            "このサイトの比較ツールや計算機は、クライアントサイドの JavaScript としてお使いのブラウザ内で完全に動作します。"
            "これらのツールに入力したデータはいかなるサーバーにも送信されません。データはブラウザセッションのローカルに留まり、ページを離れると破棄されます。"
        ),
        "future_label": "将来の変更",
        "future_body": (
            "このサイトのプライバシー態勢が変更された場合——例：分析機能やサーバーサイド機能が追加された場合——このページはその変更が発効する前に更新されます。事後ではありません。"
        ),
        "contact_label": "お問い合わせ",
        "contact_body": "プライバシーに関するご質問は",
        "contact_link": "お問い合わせページ",
    },
}


class GeneratePrivacyError(Exception):
    pass


def _ensure_mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise GeneratePrivacyError(f"{label} must be a mapping/object.")
    return value


def _ensure_string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise GeneratePrivacyError(f"{label} must be a string.")
    text = value.strip()
    if not text:
        raise GeneratePrivacyError(f"{label} must not be empty.")
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
        raise GeneratePrivacyError(f"{label} must start with /static/: {path}")
    asset_path = (ROOT_DIR / path.lstrip("/")).resolve()
    try:
        asset_path.relative_to(STATIC_DIR.resolve())
    except ValueError as exc:
        raise GeneratePrivacyError(f"{label} escapes static directory: {path}") from exc
    if not asset_path.is_file():
        raise GeneratePrivacyError(f"Missing static asset for {label}: {path}")
    return path


def _resolve_logo_path(site_config: Mapping[str, Any]) -> str:
    logo = _get_nested(site_config, ("branding", "logo_path"), "/static/img/brand/logo-icon.webp")
    return _ensure_string(logo, "branding.logo_path")


def _resolve_manifest_url() -> str:
    candidate = ROOT_DIR / "static" / "site.webmanifest"
    return "/static/site.webmanifest" if candidate.is_file() else ""


def _create_jinja_env() -> Environment:
    if not TEMPLATES_DIR.exists():
        raise GeneratePrivacyError(f"Missing templates directory: {TEMPLATES_DIR}")
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
        raise GeneratePrivacyError(f"Unable to write {path}: {exc}") from exc


def _ensure_safe_output_dir(output_dir: Path) -> Path:
    resolved = output_dir.resolve()
    if str(resolved) == resolved.anchor:
        raise GeneratePrivacyError(f"Refusing filesystem root as output directory: {resolved}")
    if resolved.exists() and resolved.is_symlink():
        raise GeneratePrivacyError(f"Refusing symlink output directory: {resolved}")
    return resolved


def _build_urls_by_lang(site_config: Mapping[str, Any], languages: Sequence[str]) -> Dict[str, str]:
    urls: Dict[str, str] = {}
    site = _ensure_mapping(site_config.get("site"), "site_config.site")
    raw_base = site.get("base_url", "https://tourvstravel.com")
    base = _ensure_string(raw_base, "site.base_url").rstrip("/")
    for code in languages:
        rel = build_privacy_path(site_config, code, absolute=False)
        urls[code] = f"{base}{rel}" if rel.startswith("/") else f"{base}/{rel}"
    return urls


def _build_context(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> Dict[str, Any]:
    copy = get_trust_page_copy("privacy", lang)
    base_url = _ensure_string(
        _get_nested(site_config, ("site", "base_url"), "https://tourvstravel.com").strip().rstrip("/"),
        "site.base_url",
    )
    site_name = _extract_site_name(site_config, lang)
    logo_url = _resolve_logo_path(site_config)
    canonical_url = build_privacy_path(site_config, lang, absolute=True)
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
        "body_class": "page-privacy",
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
            "url_contact": build_contact_path(site_config, lang, absolute=False),
            "url_about": build_about_path(site_config, lang, absolute=False),
            "url_source_policy": build_source_policy_path(site_config, lang, absolute=False),
        },
    }
    context.update(localized_ui_context(lang))
    return context


def render_privacy_page(
    *,
    site_config: Mapping[str, Any],
    lang: str,
    languages: Sequence[str],
) -> str:
    env = _create_jinja_env()
    try:
        template = env.get_template(TEMPLATE_NAME)
    except TemplateError as exc:
        raise GeneratePrivacyError(f"Unable to load template {TEMPLATE_NAME}: {exc}") from exc
    context = _build_context(site_config=site_config, lang=lang, languages=languages)
    try:
        html_out = template.render(**context)
    except TemplateError as exc:
        raise GeneratePrivacyError(f"Unable to render privacy page [{lang}]: {exc}") from exc
    if not html_out.strip():
        raise GeneratePrivacyError(f"Rendered privacy page is empty for language {lang!r}.")
    return html_out


def generate_privacy_pages(
    *,
    requested_lang: Optional[str] = None,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> List[Path]:
    safe_output_dir = _ensure_safe_output_dir(output_dir)
    site_config = load_site_config()
    if not isinstance(site_config, Mapping):
        raise GeneratePrivacyError("load_site_config() must return a mapping/object.")
    if requested_lang is not None:
        lang = requested_lang.strip()
        if lang not in SUPPORTED_LANGUAGES:
            raise GeneratePrivacyError(f"Unsupported language requested: {requested_lang!r}")
        languages = [lang]
    else:
        languages = _extract_enabled_languages(site_config)
    if not languages:
        raise GeneratePrivacyError("No enabled languages available for privacy generation.")
    written: List[Path] = []
    for lang in languages:
        html_output = render_privacy_page(site_config=site_config, lang=lang, languages=languages)
        output_path = safe_output_dir / lang / "privacy" / "index.html"
        _atomic_write_text(output_path, html_output)
        written.append(output_path)
        log.info("Generated privacy page [%s] -> %s", lang, output_path)
    return written


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate TourVsTravel privacy pages.")
    parser.add_argument("--lang", type=str, default=None)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
    args = parse_args(argv)
    try:
        generate_privacy_pages(requested_lang=args.lang, output_dir=args.output_dir)
    except GeneratePrivacyError as exc:
        log.error(str(exc))
        return 1
    except Exception as exc:
        log.exception("Unexpected privacy generation failure: %s", exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
