import re
import logging
import time
import asyncio
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
import aiohttp
from finders.base import Finder

logger = logging.getLogger(__name__)

class LoginDetectionFinder(Finder):
    """
    Finder для обнаружения систем логина/регистрации на сайте компании.
    Проверяет наличие элементов входа, регистрации и других признаков 
    пользовательского портала на официальном сайте компании.
    """
    
    # Паттерны логина на разных языках
    LOGIN_PATTERNS = {
        "en": ["login", "sign in", "log in", "signin", "register", "sign up", "signup", "account", "my account", "portal", "dashboard", 
               "profile", "subscription", "stream", "member", "membership", "user", "customer", "client area", "personalized", 
               "preferences", "cart", "e-commerce", "checkout", "payment", "billing", "plan", "watch", "save", "download", "bookmark"],
        "ru": ["вход", "войти", "логин", "авторизация", "регистрация", "личный кабинет", "мой аккаунт", "портал", "панель управления",
               "профиль", "подписка", "стрим", "смотреть", "участник", "пользователь", "клиент", "сохранить", "корзина", "оплата", "план"],
        "de": ["anmelden", "einloggen", "registrieren", "konto", "mein konto", "dashboard", "kundenportal", 
               "profil", "abonnement", "stream", "mitglied", "benutzer", "kunde", "warenkorb", "zahlung", "speichern"],
        "fr": ["connexion", "se connecter", "s'identifier", "inscription", "compte", "mon compte", "tableau de bord",
               "profil", "abonnement", "diffusion", "membre", "utilisateur", "client", "panier", "paiement", "sauvegarder"],
        "es": ["iniciar sesión", "acceder", "registrarse", "cuenta", "mi cuenta", "panel", "portal",
               "perfil", "suscripción", "transmisión", "miembro", "usuario", "cliente", "carrito", "pago", "guardar"],
        "it": ["accedi", "login", "registrati", "account", "il mio account",
               "profilo", "abbonamento", "streaming", "utente", "cliente", "carrello", "pagamento", "salvare"],
        "pt": ["entrar", "login", "cadastro", "registrar", "conta", "minha conta",
               "perfil", "assinatura", "streaming", "membro", "usuário", "cliente", "carrinho", "pagamento", "salvar"],
        "zh": ["登录", "注册", "账户", "我的账户", "个人资料", "订阅", "流媒体", "会员", "用户", "购物车", "支付", "保存"],
        "ja": ["ログイン", "登録", "アカウント", "マイページ", "プロフィール", "購読", "配信", "メンバー", "ユーザー", "カート", "支払い", "保存"],
        # Добавляем больше языков
        "ar": ["تسجيل الدخول", "دخول", "حساب", "حسابي", "تسجيل", "اشتراك", "عضوية", "ملف شخصي", "لوحة التحكم", 
               "مستخدم", "عميل", "سلة التسوق", "الدفع", "حفظ", "مشاهدة", "بث"],
        "fi": ["kirjaudu", "kirjautuminen", "rekisteröidy", "tili", "oma tili", "profiili", "hallintapaneeli", 
               "jäsenyys", "tilaus", "käyttäjä", "asiakas", "ostoskori", "maksu", "tallenna", "katso", "suoratoisto"],
        "sv": ["logga in", "registrera", "konto", "mitt konto", "profil", "kontrollpanel", 
               "medlemskap", "prenumeration", "användare", "kund", "kundvagn", "betalning", "spara", "titta", "strömma"],
        "no": ["logg inn", "registrer", "konto", "min konto", "profil", "kontrollpanel", 
               "medlemskap", "abonnement", "bruker", "kunde", "handlekurv", "betaling", "lagre", "se", "strømme"],
        "da": ["log ind", "registrer", "konto", "min konto", "profil", "kontrolpanel", 
               "medlemskab", "abonnement", "bruger", "kunde", "indkøbskurv", "betaling", "gem", "se", "stream"],
        "nl": ["inloggen", "aanmelden", "registreren", "account", "mijn account", "profiel", "dashboard", 
               "lidmaatschap", "abonnement", "gebruiker", "klant", "winkelwagen", "betaling", "opslaan", "bekijken", "streamen"],
        "tr": ["giriş", "kaydol", "hesap", "hesabım", "profil", "kontrol paneli", 
               "üyelik", "abonelik", "kullanıcı", "müşteri", "sepet", "ödeme", "kaydet", "izle", "yayın"],
        "ko": ["로그인", "가입", "계정", "내 계정", "프로필", "대시보드", 
               "멤버십", "구독", "사용자", "고객", "장바구니", "결제", "저장", "시청", "스트리밍"],
        "hi": ["लॉगिन", "साइन इन", "पंजीकरण", "खाता", "मेरा खाता", "प्रोफाइल", "डैशबोर्ड", 
               "सदस्यता", "उपयोगकर्ता", "ग्राहक", "कार्ट", "भुगतान", "सहेजें", "देखें", "स्ट्रीमिंग"],
        "he": ["התחברות", "כניסה", "הרשמה", "חשבון", "החשבון שלי", "פרופיל", "לוח בקרה", 
               "מנוי", "משתמש", "לקוח", "עגלת קניות", "תשלום", "שמור", "צפה", "הזרמה"]
    }
    
    # Паттерны URL логина
    LOGIN_URL_PATTERNS = [
        "/login", "/signin", "/register", "/signup", "/account", "/auth", "/profile", 
        "/portal", "/dashboard", "/customer", "/user", "/my", "/cabinet", "/panel",
        "/join", "/member", "/subscribe", "/subscription", "/stream", "/plans", "/pricing",
        "/cart", "/checkout", "/payment", "/billing", "/preferences", "/settings",
        "/watch", "/player", "/download", "/save", "/library"
    ]
    
    def __init__(self, timeout: int = 30, verbose: bool = False):
        """
        Инициализация финдера.
        
        Args:
            timeout: Таймаут запросов в секундах
            verbose: Подробный вывод информации
        """
        self.timeout = timeout
        self.verbose = verbose
    
    async def find(self, company_name: str, **context) -> Dict[str, Any]:
        """
        Ищет системы логина на официальном сайте компании.
        
        Args:
            company_name: Название компании
            context: Контекст с результатами предыдущих поисков
            
        Returns:
            Dict[str, Any]: Результат поиска с информацией о наличии системы логина
        """
        # Ищем URL сайта в контексте
        homepage_url = None
        
        # Ищем сначала в переданном напрямую homepage_url
        if "homepage_url" in context:
            homepage_url = context["homepage_url"]
        
        # Если нет, ищем в результатах других финдеров
        if not homepage_url and "finder_results" in context:
            finder_results = context["finder_results"]
            for result in finder_results:
                if result.get("source") == "homepage_finder" and result.get("result"):
                    homepage_url = result["result"]
                    break
                
                # Также проверяем результаты LLM Deep Search
                if result.get("source") == "llm_deep_search" and result.get("extracted_homepage_url"):
                    homepage_url = result["extracted_homepage_url"]
                    break
        
        if not homepage_url:
            logger.warning(f"LoginDetectionFinder: Не найден homepage URL для '{company_name}'")
            return {
                "source": "login_detection_finder", 
                "result": {
                    "has_user_portal": False,
                    "has_transaction_interface": False,
                    "has_dashboard": False,
                    "has_streaming_service": False,
                    "has_personalization": False,
                    "description": "Не удалось проверить наличие логина (URL сайта не найден)"
                },
                "error": "Не найден URL сайта компании"
            }
        
        try:
            logger.info(f"LoginDetectionFinder: Сканирование {homepage_url} для '{company_name}'")
            login_details = await self._scan_website_for_login(homepage_url)
            
            if self.verbose:
                logger.info(f"LoginDetectionFinder для {company_name}: {login_details}")
                
            return {
                "source": "login_detection_finder",
                "result": login_details,
                "_finder_instance_type": self.__class__.__name__
            }
            
        except Exception as e:
            logger.error(f"LoginDetectionFinder: Ошибка при сканировании {homepage_url} для '{company_name}': {str(e)}")
            return {
                "source": "login_detection_finder",
                "result": {
                    "has_user_portal": False,
                    "has_transaction_interface": False,
                    "has_dashboard": False,
                    "has_streaming_service": False,
                    "has_personalization": False,
                    "description": f"Ошибка при сканировании: {str(e)}"
                },
                "error": f"Ошибка сканирования: {str(e)}",
                "_finder_instance_type": self.__class__.__name__
            }
    
    async def _scan_website_for_login(self, url: str) -> Dict[str, Any]:
        """
        Сканирует веб-сайт на наличие систем логина/регистрации.
        
        Args:
            url: URL сайта компании
            
        Returns:
            Dict[str, Any]: Информация о наличии систем логина и деталях
        """
        result = {
            "has_user_portal": False,
            "has_transaction_interface": False,
            "has_dashboard": False,
            "has_streaming_service": False,
            "has_personalization": False,
            "description": ""
        }
        
        # Нормализуем URL
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1"
            }
            
            login_evidences = []
            transaction_evidences = []
            dashboard_evidences = []
            
            # Асинхронный HTTP-клиент
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(url, headers=headers, timeout=self.timeout, ssl=False) as response:
                        if response.status != 200:
                            result["description"] = f"Ошибка загрузки страницы. Код статуса: {response.status}"
                            return result
                            
                        html_content = await response.text()
                        
                        # Используем BeautifulSoup для парсинга HTML
                        soup = BeautifulSoup(html_content, 'html.parser')
                        
                        # 1. Ищем ссылки с текстом, связанным с логином
                        all_login_elements = []
                        
                        # Проходим по всем языкам и проверяем паттерны
                        for lang, patterns in self.LOGIN_PATTERNS.items():
                            for pattern in patterns:
                                # Ищем в тексте ссылок и кнопок
                                for tag in ['a', 'button', 'input', 'div', 'span']:
                                    elements = soup.find_all(tag, text=re.compile(f"\\b{pattern}\\b", re.IGNORECASE))
                                    for el in elements:
                                        all_login_elements.append((el, pattern, lang))
                                        if "dashboard" in pattern.lower() or "панель" in pattern.lower():
                                            dashboard_evidences.append(f"{tag} с текстом '{pattern}' (язык: {lang})")
                                    
                                    # Ищем в атрибутах title, alt, placeholder
                                    for attr in ['title', 'alt', 'placeholder', 'value', 'aria-label']:
                                        elements = soup.find_all(attrs={attr: re.compile(f"\\b{pattern}\\b", re.IGNORECASE)})
                                        for el in elements:
                                            all_login_elements.append((el, pattern, lang))
                                            if "dashboard" in pattern.lower() or "панель" in pattern.lower():
                                                dashboard_evidences.append(f"{tag} с атрибутом {attr}='{pattern}' (язык: {lang})")
                                
                                # Ищем в классах и id
                                for attr_type in ['class', 'id', 'name']:
                                    elements = soup.find_all(attrs={attr_type: re.compile(f".*{pattern}.*", re.IGNORECASE)})
                                    for el in elements:
                                        all_login_elements.append((el, pattern, lang))
                            
                        # 2. Ищем формы логина
                        login_forms = soup.find_all('form')
                        for form in login_forms:
                            # Проверяем атрибуты формы
                            form_action = form.get('action', '').lower()
                            if any(pattern in form_action for pattern in self.LOGIN_URL_PATTERNS):
                                all_login_elements.append((form, "form with login action", "en"))
                                login_evidences.append(f"Форма с action='{form_action}'")
                            
                            # Проверяем наличие полей ввода пароля
                            password_fields = form.find_all('input', {'type': 'password'})
                            if password_fields:
                                all_login_elements.append((form, "form with password field", "en"))
                                login_evidences.append("Форма с полем для ввода пароля")
                            
                            # Проверяем на наличие полей для email/username и password вместе
                            inputs = form.find_all('input')
                            has_username = any(inp.get('type') == 'text' or inp.get('type') == 'email' or 
                                             'user' in inp.get('name', '').lower() or 'email' in inp.get('name', '').lower()
                                             for inp in inputs)
                            
                            if has_username and password_fields:
                                login_evidences.append("Форма с полями для имени пользователя/email и пароля")
                        
                        # 3. Ищем характерные URL-паттерны в ссылках
                        login_urls = []
                        for link in soup.find_all('a', href=True):
                            href = link['href'].lower()
                            for pattern in self.LOGIN_URL_PATTERNS:
                                if pattern in href:
                                    login_urls.append(href)
                                    all_login_elements.append((link, f"link with {pattern}", "en"))
                                    login_evidences.append(f"Ссылка с URL, содержащим '{pattern}'")
                                    break
                        
                        # 4. Проверяем наличие признаков транзакционного интерфейса
                        transaction_keywords = [
                            "payment", "checkout", "cart", "buy", "purchase", "order", "shop", "store", 
                            "оплата", "корзина", "купить", "заказ", "магазин", 
                            "zahlung", "warenkorb", "kaufen", "bestellen", 
                            "paiement", "panier", "acheter", "commander"
                        ]
                        
                        for keyword in transaction_keywords:
                            # Ищем в ссылках, кнопках, формах
                            elements = soup.find_all(text=re.compile(f"\\b{keyword}\\b", re.IGNORECASE))
                            if elements:
                                transaction_evidences.append(f"Найден текст '{keyword}'")
                            
                            # Проверяем атрибуты
                            for attr in ['title', 'alt', 'placeholder', 'value', 'aria-label']:
                                elements = soup.find_all(attrs={attr: re.compile(f"\\b{keyword}\\b", re.IGNORECASE)})
                                if elements:
                                    transaction_evidences.append(f"Найден атрибут {attr}='{keyword}'")
                        
                        # 5. Проверяем наличие признаков потокового вещания и подписок
                        streaming_subscription_keywords = [
                            "stream", "watch", "play", "video", "listen", "subscribe", "subscription", "plan", "membership",
                            "смотреть", "слушать", "видео", "подписка", "трансляция", "стрим", "подписаться", "тариф",
                            "streamen", "ansehen", "hören", "abonnement", "mitgliedschaft",
                            "diffusion", "regarder", "écouter", "abonnement", "adhésion"
                        ]
                        
                        streaming_evidences = []
                        
                        for keyword in streaming_subscription_keywords:
                            # Ищем в тексте страницы
                            elements = soup.find_all(text=re.compile(f"\\b{keyword}\\b", re.IGNORECASE))
                            if elements:
                                streaming_evidences.append(f"Найден текст '{keyword}'")
                            
                            # Проверяем атрибуты
                            for attr in ['title', 'alt', 'placeholder', 'value', 'aria-label', 'href']:
                                elements = soup.find_all(attrs={attr: re.compile(f"\\b{keyword}\\b", re.IGNORECASE)})
                                if elements:
                                    streaming_evidences.append(f"Найден атрибут {attr}='{keyword}'")
                                    
                        # 6. Проверяем наличие признаков персонализации
                        personalization_keywords = [
                            "profile", "account", "settings", "preferences", "my", "personalize", "customize", "save", "bookmark", "history", "favorites",
                            "профиль", "настройки", "предпочтения", "мой", "персонализ", "сохранить", "избранное", "история", "закладки",
                            "profil", "einstellungen", "meine", "anpassen", "speichern", "lesezeichen", "verlauf", "favoriten",
                            "profil", "paramètres", "préférences", "mon", "personnaliser", "enregistrer", "historique", "favoris"
                        ]
                        
                        personalization_evidences = []
                        
                        for keyword in personalization_keywords:
                            # Ищем в тексте страницы
                            elements = soup.find_all(text=re.compile(f"\\b{keyword}\\b", re.IGNORECASE))
                            if elements:
                                personalization_evidences.append(f"Найден текст '{keyword}'")
                            
                            # Проверяем атрибуты
                            for attr in ['title', 'alt', 'placeholder', 'value', 'aria-label', 'href']:
                                elements = soup.find_all(attrs={attr: re.compile(f"\\b{keyword}\\b", re.IGNORECASE)})
                                if elements:
                                    personalization_evidences.append(f"Найден атрибут {attr}='{keyword}'")
                    
                except aiohttp.ClientError as e:
                    result["description"] = f"Ошибка HTTP-клиента: {str(e)}"
                    return result
                    
            # Анализируем результаты
            unique_login_elements_count = len(set(str(el[0])[:50] for el in all_login_elements))
            
            # Формируем описание
            description_parts = []
            
            # Для логин-портала
            if login_evidences:
                description_parts.append(f"Найдены признаки системы логина/регистрации: {', '.join(login_evidences[:3])}")
                if len(login_evidences) > 3:
                    description_parts[-1] += f" и еще {len(login_evidences) - 3}"
                result["has_user_portal"] = True
            
            # Для транзакционного интерфейса
            if transaction_evidences:
                description_parts.append(f"Найдены признаки транзакционного интерфейса: {', '.join(transaction_evidences[:3])}")
                if len(transaction_evidences) > 3:
                    description_parts[-1] += f" и еще {len(transaction_evidences) - 3}"
                result["has_transaction_interface"] = True
                # Если есть транзакционный интерфейс, также считаем, что есть и пользовательский портал
                result["has_user_portal"] = True
            
            # Для дашборда
            if dashboard_evidences:
                description_parts.append(f"Найдены признаки панели управления/дашборда: {', '.join(dashboard_evidences[:3])}")
                if len(dashboard_evidences) > 3:
                    description_parts[-1] += f" и еще {len(dashboard_evidences) - 3}"
                result["has_dashboard"] = True
                # Если есть дашборд, также считаем, что есть и пользовательский портал
                result["has_user_portal"] = True
            
            # Для потокового вещания и подписок
            if streaming_evidences:
                description_parts.append(f"Найдены признаки сервисов потокового вещания/подписок: {', '.join(streaming_evidences[:3])}")
                if len(streaming_evidences) > 3:
                    description_parts[-1] += f" и еще {len(streaming_evidences) - 3}"
                result["has_streaming_service"] = True
                # Если есть сервисы подписок/стриминга, с высокой вероятностью есть и пользовательский портал
                result["has_user_portal"] = True
            
            # Для функций персонализации
            if personalization_evidences:
                description_parts.append(f"Найдены признаки персонализации контента: {', '.join(personalization_evidences[:3])}")
                if len(personalization_evidences) > 3:
                    description_parts[-1] += f" и еще {len(personalization_evidences) - 3}"
                result["has_personalization"] = True
                # Если есть персонализация, весьма вероятно есть и пользовательский портал
                result["has_user_portal"] = True
                
            # Финальное описание
            if description_parts:
                result["description"] = " ".join(description_parts)
            else:
                result["description"] = "Явных признаков системы логина/регистрации не обнаружено."
                
            # Учитываем бизнес-модель сайта - если это интернет-магазин, стриминговый сервис или сайт с подпиской,
            # но мы не нашли явных признаков логина, все равно считаем, что пользовательский интерфейс есть
            if not result["has_user_portal"]:
                # Проверяем наличие ключевых слов, указывающих на бизнес-модель с пользовательским порталом
                business_model_keywords = ["shop", "store", "subscription", "account", "streaming", "e-commerce", 
                                           "member", "premium", "customer", "магазин", "подписка", "стриминг"]
                
                # Ищем ключевые слова в title страницы
                if soup.title and soup.title.string:
                    for keyword in business_model_keywords:
                        if keyword.lower() in soup.title.string.lower():
                            result["has_user_portal"] = True
                            result["description"] += f" Предположительно имеется пользовательский портал на основе бизнес-модели ({keyword})."
                            break
                
            return result
            
        except Exception as e:
            result["description"] = f"Ошибка при сканировании: {str(e)}"
            logger.error(f"LoginDetectionFinder: Ошибка при анализе {url}: {str(e)}")
            return result

# Для тестирования
if __name__ == "__main__":
    async def test_finder():
        logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
        
        # Тестовые URL
        test_urls = [
            {"company": "Slack", "url": "https://slack.com"},
            {"company": "GitHub", "url": "https://github.com"},
            {"company": "Yandex", "url": "https://yandex.ru"}
        ]
        
        finder = LoginDetectionFinder(verbose=True)
        
        for test in test_urls:
            company = test["company"]
            url = test["url"]
            print(f"\n=== Тестирование {company} ({url}) ===")
            
            result = await finder.find(company, homepage_url=url)
            
            if "error" in result:
                print(f"Ошибка: {result['error']}")
            else:
                print(f"Результат: {result['result']}")
    
    # Запускаем тест
    asyncio.run(test_finder()) 