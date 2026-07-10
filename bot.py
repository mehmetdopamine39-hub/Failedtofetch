import os
import json
import re
import time
import logging
import asyncio
import aiohttp
import requests
import cloudscraper
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from collections import defaultdict
from functools import wraps
from bs4 import BeautifulSoup
import html5lib

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode
import telegram.error

# ======================== KONFIGÜRASYON ========================
BOT_TOKEN = "8723649029:AAH_E81gQ1blNXvitDNYGsjrm08xinAfZm4"
ADMIN_IDS = [8610336203]
SUPPORT_USERNAME = "@rinexdestek"

# Emoji listesi
EMOJIS = {
    "success": "✅",
    "error": "❌",
    "warning": "⚠️",
    "info": "ℹ️",
    "loading": "⏳",
    "search": "🔍",
    "user": "👤",
    "admin": "🛡️",
    "premium": "⭐",
    "free": "🆓",
    "money": "💰",
    "settings": "⚙️",
    "database": "📊",
    "link": "🔗",
    "time": "🕐",
    "lock": "🔒",
    "unlock": "🔓",
    "warning_icon": "🚨",
    "new": "🆕",
    "delete": "🗑️",
    "edit": "✏️",
    "refresh": "🔄",
    "menu": "📋",
    "id": "🆔",
    "phone": "📱",
    "address": "🏠",
    "car": "🚗",
    "bank": "🏦",
    "school": "🎓",
    "social": "🌐",
}

# ======================== VERİ YAPILARI ========================
@dataclass
class UserData:
    user_id: int
    username: str = ""
    first_name: str = ""
    last_name: str = ""
    is_premium: bool = False
    premium_expiry: Optional[str] = None
    search_count: int = 0
    last_search: Optional[str] = None
    is_banned: bool = False
    warning_count: int = 0
    joined_date: str = field(default_factory=lambda: datetime.now().isoformat())

@dataclass
class SearchQuery:
    query_id: str
    user_id: int
    query_type: str
    query_value: str
    result: Any = None
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    is_premium_query: bool = False

@dataclass
class ApiEndpoint:
    name: str
    url: str
    params: Dict[str, str]
    is_premium: bool = False
    is_active: bool = True
    bypass_js: bool = False

@dataclass
class Announcement:
    id: str
    title: str
    content: str
    date: str = field(default_factory=lambda: datetime.now().isoformat())
    is_active: bool = True

# ======================== VERİ YÖNETİCİSİ ========================
class DataManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.users_file = os.path.join(data_dir, "users.json")
        self.queries_file = os.path.join(data_dir, "queries.json")
        self.apis_file = os.path.join(data_dir, "apis.json")
        self.announcements_file = os.path.join(data_dir, "announcements.json")
        self.settings_file = os.path.join(data_dir, "settings.json")
        
        self.users: Dict[int, UserData] = {}
        self.queries: List[SearchQuery] = []
        self.apis: Dict[str, ApiEndpoint] = {}
        self.announcements: List[Announcement] = []
        self.settings: Dict[str, Any] = {}
        
        self._load_data()
    
    def _load_data(self):
        self.users = self._load_json(self.users_file, {})
        self.queries = self._load_json(self.queries_file, [])
        self.apis = self._load_json(self.apis_file, {})
        self.announcements = self._load_json(self.announcements_file, [])
        self.settings = self._load_json(self.settings_file, {})
        
        default_settings = {
            "maintenance_mode": False,
            "maintenance_message": "Bakım çalışması var, lütfen daha sonra tekrar deneyin.",
            "premium_price": 50,
            "premium_duration": 30,
            "free_search_limit": 5,
        }
        for key, value in default_settings.items():
            if key not in self.settings:
                self.settings[key] = value
    
    def _load_json(self, file_path: str, default: Any):
        try:
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logging.error(f"Veri yükleme hatası {file_path}: {e}")
        return default
    
    def _save_json(self, file_path: str, data: Any):
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Veri kaydetme hatası {file_path}: {e}")
    
    def save_all(self):
        self._save_json(self.users_file, self.users)
        self._save_json(self.queries_file, self.queries)
        self._save_json(self.apis_file, self.apis)
        self._save_json(self.announcements_file, self.announcements)
        self._save_json(self.settings_file, self.settings)
    
    def get_user(self, user_id: int) -> UserData:
        if user_id not in self.users:
            self.users[user_id] = UserData(user_id=user_id)
            self.save_all()
        return self.users[user_id]
    
    def save_user(self, user_data: UserData):
        self.users[user_data.user_id] = user_data
        self.save_all()
    
    def add_query(self, query: SearchQuery):
        self.queries.append(query)
        self.save_all()
    
    def get_user_queries(self, user_id: int, limit: int = 10) -> List[SearchQuery]:
        return [q for q in self.queries if q.user_id == user_id][-limit:]
    
    def get_api(self, name: str) -> Optional[ApiEndpoint]:
        return self.apis.get(name)
    
    def add_api(self, api: ApiEndpoint):
        self.apis[api.name] = api
        self.save_all()
    
    def delete_api(self, name: str):
        if name in self.apis:
            del self.apis[name]
            self.save_all()
    
    def add_announcement(self, announcement: Announcement):
        self.announcements.append(announcement)
        self.save_all()
    
    def delete_announcement(self, announcement_id: str):
        self.announcements = [a for a in self.announcements if a.id != announcement_id]
        self.save_all()
    
    def get_active_announcements(self) -> List[Announcement]:
        return [a for a in self.announcements if a.is_active]

# ======================== API İSTEK YÖNETİCİSİ ========================
class ApiClient:
    def __init__(self):
        self.session = None
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True,
                'mobile': False
            }
        )
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
            "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
        ]
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    def _get_headers(self, bypass_js: bool = False) -> Dict[str, str]:
        headers = {
            "User-Agent": self.user_agents[0],
            "Accept": "application/json, text/html, */*",
            "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        }
        
        if bypass_js:
            headers["User-Agent"] = "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
            headers["Sec-Fetch-Dest"] = "document"
            headers["Sec-Fetch-Mode"] = "navigate"
            headers["Sec-Fetch-Site"] = "none"
            headers["Sec-Fetch-User"] = "?1"
        
        return headers
    
    def _extract_json_from_html(self, html: str) -> Dict:
        try:
            soup = BeautifulSoup(html, 'html.parser')
            text = soup.get_text()
            
            json_patterns = [
                r'<pre[^>]*>(.*?)</pre>',
                r'<code[^>]*>(.*?)</code>',
                r'({[^{}]*})',
                r'(\[[^\[\]]*\])',
            ]
            
            for pattern in json_patterns:
                matches = re.findall(pattern, html, re.DOTALL)
                for match in matches:
                    try:
                        data = json.loads(match.strip())
                        if data:
                            return data
                    except:
                        continue
            
            try:
                json_match = re.search(r'({.*})', text)
                if json_match:
                    return json.loads(json_match.group(1))
            except:
                pass
            
            try:
                array_match = re.search(r'(\[.*\])', text)
                if array_match:
                    return json.loads(array_match.group(1))
            except:
                pass
                
            return {"raw": text[:500]}
            
        except Exception as e:
            logging.error(f"JSON çıkarma hatası: {e}")
            return {"raw": html[:500]}
    
    async def get(self, url: str, params: Dict = None, bypass_js: bool = False) -> Any:
        try:
            if bypass_js:
                try:
                    response = self.scraper.get(url, params=params, timeout=30)
                    try:
                        return response.json()
                    except:
                        return self._extract_json_from_html(response.text)
                except Exception as e:
                    logging.warning(f"CloudScraper hatası: {e}")
            
            headers = self._get_headers(bypass_js)
            timeout = aiohttp.ClientTimeout(total=30)
            
            async with self.session.get(url, params=params, headers=headers, timeout=timeout) as response:
                content_type = response.headers.get("content-type", "")
                
                if "application/json" in content_type:
                    return await response.json()
                else:
                    text = await response.text()
                    json_data = self._extract_json_from_html(text)
                    if json_data and "raw" not in json_data:
                        return json_data
                    return {"raw": text[:500]}
                    
        except Exception as e:
            logging.error(f"API isteği hatası: {e}")
            return {"error": str(e)}

# ======================== BOT YÖNETİCİSİ ========================
class SorguBot:
    def __init__(self, token: str, data_manager: DataManager):
        self.token = token
        self.data = data_manager
        self.api_client = ApiClient()
        self.application = None
        self._load_default_apis()
    
    def _load_default_apis(self):
        """Tüm API'leri yükle"""
        default_apis = {
            # ===== ARAŞTIR.VIP API'leri =====
            "tc_sorgu": ApiEndpoint(
                name="tc_sorgu",
                url="https://arastir.vip/api/tc.php",
                params={"tc": ""},
                is_premium=False,
                bypass_js=True
            ),
            "adsoyad_sorgu": ApiEndpoint(
                name="adsoyad_sorgu",
                url="https://arastir.vip/api/adsoyad.php",
                params={"adi": "", "soyadi": "", "il": "", "ilce": ""},
                is_premium=False,
                bypass_js=True
            ),
            "adres_sorgu": ApiEndpoint(
                name="adres_sorgu",
                url="https://arastir.vip/api/adres.php",
                params={"tc": ""},
                is_premium=True,
                bypass_js=True
            ),
            "gsm_sorgu": ApiEndpoint(
                name="gsm_sorgu",
                url="https://arastir.vip/api/gsmtc.php",
                params={"gsm": ""},
                is_premium=True,
                bypass_js=True
            ),
            "tc_gsm_sorgu": ApiEndpoint(
                name="tc_gsm_sorgu",
                url="https://arastir.vip/api/tcgsm.php",
                params={"tc": ""},
                is_premium=True,
                bypass_js=True
            ),
            "isyeri_sorgu": ApiEndpoint(
                name="isyeri_sorgu",
                url="https://arastir.vip/api/isyeri.php",
                params={"tc": ""},
                is_premium=True,
                bypass_js=True
            ),
            "sulale_sorgu": ApiEndpoint(
                name="sulale_sorgu",
                url="https://arastir.vip/api/sulale.php",
                params={"tc": ""},
                is_premium=True,
                bypass_js=True
            ),
            
            # ===== ANYAPI.IO =====
            "iban_sorgu": ApiEndpoint(
                name="iban_sorgu",
                url="https://anyapi.io/api/v1/iban",
                params={"apiKey": "6alee0spg0op0nan20fd5gjdc2tgto7poqqrbe2s06uoiepevf5ok5g", "iban": ""},
                is_premium=True,
                bypass_js=False
            ),
            
            # ===== SORGUPANELAPILERIM =====
            "eokul_sorgu": ApiEndpoint(
                name="eokul_sorgu",
                url="https://sorgupanelapilerim.freedev.app/index.php",
                params={"api": "eokul", "q": "", "type": "tc"},
                is_premium=True,
                bypass_js=True
            ),
            "plaka_sorgu": ApiEndpoint(
                name="plaka_sorgu",
                url="https://sorgupanelapilerim.freedev.app/index.php",
                params={"api": "plaka", "q": "", "type": "plaka"},
                is_premium=False,
                bypass_js=True
            ),
            "papara_sorgu": ApiEndpoint(
                name="papara_sorgu",
                url="https://sorgupanelapilerim.freedev.app/index.php",
                params={"api": "papara", "q": "", "type": "id"},
                is_premium=False,
                bypass_js=True
            ),
            
            # ===== RINEX INSTAGRAM =====
            "instagram_sorgu": ApiEndpoint(
                name="instagram_sorgu",
                url="https://rinexinstegramsorguapi.rf.gd/api/instagram.php",
                params={"kullanici_adi": ""},
                is_premium=False,
                bypass_js=True
            ),
            
            # ===== RINEX SECMEN =====
            "secmen_tc_sorgu": ApiEndpoint(
                name="secmen_tc_sorgu",
                url="https://rinexsecmensorguapu.gt.tc/api/secmen.php",
                params={"action": "tc", "tc": ""},
                is_premium=True,
                bypass_js=True
            ),
            "secmen_adsoyad_sorgu": ApiEndpoint(
                name="secmen_adsoyad_sorgu",
                url="https://rinexsecmensorguapu.gt.tc/api/secmen.php",
                params={"action": "adsoyad", "ad": "", "soyad": ""},
                is_premium=True,
                bypass_js=True
            ),
            
            # ===== RINEX PLAKA =====
            "plaka_arama_sorgu": ApiEndpoint(
                name="plaka_arama_sorgu",
                url="https://rinexplakasorguapi.gt.tc/api/plaka.php",
                params={"endpoint": "ara", "q": ""},
                is_premium=False,
                bypass_js=True
            ),
            
            # ===== INIAL SORGU =====
            "innial_gsm_sorgu": ApiEndpoint(
                name="innial_gsm_sorgu",
                url="https://inialsorguapi.onrender.com/api/innial.php",
                params={"gsm": ""},
                is_premium=True,
                bypass_js=False
            ),
            "innial_tc_sorgu": ApiEndpoint(
                name="innial_tc_sorgu",
                url="https://inialsorguapi.onrender.com/api/innial.php",
                params={"tc": ""},
                is_premium=True,
                bypass_js=False
            ),
            
            # ===== SGK =====
            "sgk_tc_sorgu": ApiEndpoint(
                name="sgk_tc_sorgu",
                url="https://eokulsorguapi.onrender.com/sgk/api",
                params={"tc": ""},
                is_premium=True,
                bypass_js=False
            ),
            "sgk_adsoyad_sorgu": ApiEndpoint(
                name="sgk_adsoyad_sorgu",
                url="https://eokulsorguapi.onrender.com/sgk/api",
                params={"ad": "", "soyad": ""},
                is_premium=True,
                bypass_js=False
            ),
            
            # ===== EOKUL =====
            "eokul_tc_sorgu": ApiEndpoint(
                name="eokul_tc_sorgu",
                url="https://lorexchecksorguapi.onrender.com/eokul/api",
                params={"tc": ""},
                is_premium=True,
                bypass_js=False
            ),
            
            # ===== TELEFON REHBERİ =====
            "telefon_rehberi": ApiEndpoint(
                name="telefon_rehberi",
                url="https://arastir.vip/api/gsmtc.php",
                params={"gsm": ""},
                is_premium=True,
                bypass_js=True
            ),
            
            # ===== ADRES SORGU =====
            "adres_detay": ApiEndpoint(
                name="adres_detay",
                url="https://arastir.vip/api/adres.php",
                params={"tc": ""},
                is_premium=True,
                bypass_js=True
            ),
            
            # ===== NÜFUS SORGU =====
            "nufus_sorgu": ApiEndpoint(
                name="nufus_sorgu",
                url="https://arastir.vip/api/tc.php",
                params={"tc": ""},
                is_premium=False,
                bypass_js=True
            ),
        }
        
        for name, api in default_apis.items():
            if name not in self.data.apis:
                self.data.add_api(api)
    
    async def initialize(self):
        self.application = Application.builder().token(self.token).build()
        
        self.application.add_handler(CommandHandler("start", self.start_command))
        self.application.add_handler(CommandHandler("admin", self.admin_command))
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        self.application.add_error_handler(self.error_handler)
    
    async def check_user(self, update: Update) -> Tuple[Optional[UserData], bool]:
        user = update.effective_user
        user_data = self.data.get_user(user.id)
        user_data.username = user.username or ""
        user_data.first_name = user.first_name or ""
        user_data.last_name = user.last_name or ""
        self.data.save_user(user_data)
        
        if user_data.is_banned:
            await update.effective_message.reply_text(
                f"{EMOJIS['error']} Hesabınız yasaklanmıştır!"
            )
            return user_data, False
        
        if self.data.settings.get("maintenance_mode", False):
            if user.id not in ADMIN_IDS:
                await update.effective_message.reply_text(
                    f"{EMOJIS['warning']} {self.data.settings.get('maintenance_message', 'Bakım çalışması var.')}"
                )
                return user_data, False
        
        return user_data, True
    
    def create_main_menu(self, user_data: UserData) -> InlineKeyboardMarkup:
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['search']} Sorgu Başlat", callback_data="menu_search")],
            [InlineKeyboardButton(f"{EMOJIS['premium']} Premium Bilgilerim", callback_data="menu_premium")],
            [InlineKeyboardButton(f"{EMOJIS['database']} Sorgu Geçmişim", callback_data="menu_history")],
            [InlineKeyboardButton(f"{EMOJIS['info']} Yardım & Destek", callback_data="menu_help")],
        ]
        
        if user_data.user_id in ADMIN_IDS:
            keyboard.append([InlineKeyboardButton(f"{EMOJIS['admin']} Admin Paneli", callback_data="menu_admin")])
        
        return InlineKeyboardMarkup(keyboard)
    
    def create_search_menu(self, user_data: UserData) -> InlineKeyboardMarkup:
        keyboard = []
        
        free_apis = [api for api in self.data.apis.values() if not api.is_premium and api.is_active]
        for api in free_apis:
            label = f"{EMOJIS['free']} {api.name.replace('_', ' ').title()}"
            keyboard.append([InlineKeyboardButton(label, callback_data=f"search_{api.name}")])
        
        premium_apis = [api for api in self.data.apis.values() if api.is_premium and api.is_active]
        if premium_apis:
            keyboard.append([InlineKeyboardButton("─── Premium Sorgular ───", callback_data="dummy")])
            for api in premium_apis:
                label = f"{EMOJIS['premium']} {api.name.replace('_', ' ').title()}"
                if user_data.is_premium:
                    callback = f"search_{api.name}"
                else:
                    callback = "premium_required"
                keyboard.append([InlineKeyboardButton(label, callback_data=callback)])
        
        keyboard.append([InlineKeyboardButton(f"{EMOJIS['menu']} Ana Menü", callback_data="main_menu")])
        return InlineKeyboardMarkup(keyboard)
    
    async def format_result(self, data: Any, query_type: str) -> str:
        if isinstance(data, dict):
            if "error" in data:
                return f"{EMOJIS['error']} Hata: {data['error']}"
            
            result_parts = [f"{EMOJIS['success']} Sorgu Sonucu:"]
            for key, value in data.items():
                if value and key not in ["raw", "error", "apiKey"]:
                    result_parts.append(f"🔹 {key.replace('_', ' ').title()}: {value}")
            
            if len(result_parts) == 1:
                return f"{EMOJIS['warning']} Veri bulunamadı veya hatalı format."
            
            return "\n".join(result_parts)
        elif isinstance(data, list):
            result_parts = [f"{EMOJIS['success']} Sorgu Sonucu:"]
            for item in data[:10]:
                if isinstance(item, dict):
                    for key, value in list(item.items())[:5]:
                        if value:
                            result_parts.append(f"🔹 {key}: {value}")
                    result_parts.append("---")
            return "\n".join(result_parts[:30]) if result_parts else f"{EMOJIS['warning']} Veri bulunamadı."
        elif isinstance(data, str):
            return f"{EMOJIS['success']} {data[:500]}"
        else:
            return f"{EMOJIS['success']} {str(data)[:500]}"
    
    # ======================== KOMUTLAR ========================
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_data, ok = await self.check_user(update)
        if not ok:
            return
        
        welcome_msg = (
            f"{EMOJIS['user']} *Hoş Geldiniz, {update.effective_user.first_name}!*\n\n"
            f"Bu bot ile çeşitli sorgulama işlemleri yapabilirsiniz.\n"
            f"🚀 Hızlı ve güvenli sorgulama\n"
            f"📊 Premium seçenekler\n"
            f"🔒 Gizlilik koruması\n\n"
            f"Lütfen aşağıdaki menüden işlem seçin:"
        )
        
        await update.message.reply_text(
            welcome_msg,
            reply_markup=self.create_main_menu(user_data),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def admin_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if user.id not in ADMIN_IDS:
            await update.message.reply_text(f"{EMOJIS['error']} Bu komut sadece adminler içindir!")
            return
        
        await self.show_admin_menu(update, context)
    
    async def show_admin_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['database']} Sorgu Yönetimi", callback_data="admin_queries")],
            [InlineKeyboardButton(f"{EMOJIS['user']} Kullanıcı Yönetimi", callback_data="admin_users")],
            [InlineKeyboardButton(f"{EMOJIS['premium']} Premium Yönetimi", callback_data="admin_premium")],
            [InlineKeyboardButton(f"{EMOJIS['settings']} Ayarlar", callback_data="admin_settings")],
            [InlineKeyboardButton(f"{EMOJIS['new']} Duyuru Ekle", callback_data="admin_announce")],
            [InlineKeyboardButton(f"{EMOJIS['warning_icon']} Bakım Modu", callback_data="admin_maintenance")],
            [InlineKeyboardButton(f"{EMOJIS['menu']} Ana Menü", callback_data="main_menu")],
        ]
        
        query = update.callback_query if update.callback_query else None
        if query:
            await query.edit_message_text(
                f"{EMOJIS['admin']} *Admin Paneli*\n\nYönetim işlemleri:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        else:
            await update.message.reply_text(
                f"{EMOJIS['admin']} *Admin Paneli*\n\nYönetim işlemleri:",
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
    
    # ======================== CALLBACK HANDLER ========================
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        
        user_data, ok = await self.check_user(update)
        if not ok:
            return
        
        data = query.data
        
        if data == "main_menu":
            await query.edit_message_text(
                f"{EMOJIS['user']} *Ana Menü*\n\nHoş geldiniz {update.effective_user.first_name}!",
                reply_markup=self.create_main_menu(user_data),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif data == "menu_search":
            await query.edit_message_text(
                f"{EMOJIS['search']} *Sorgu Menüsü*\n\nAşağıdan sorgu tipini seçin:",
                reply_markup=self.create_search_menu(user_data),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif data == "menu_premium":
            if user_data.is_premium:
                expiry = user_data.premium_expiry or "Süresiz"
                text = (
                    f"{EMOJIS['premium']} *Premium Bilgileriniz*\n\n"
                    f"Durum: ✅ Aktif\n"
                    f"Bitiş: {expiry}\n"
                    f"Toplam Sorgu: {user_data.search_count}"
                )
            else:
                text = (
                    f"{EMOJIS['premium']} *Premium Bilgileriniz*\n\n"
                    f"Durum: ❌ Değil\n"
                    f"Fiyat: {self.data.settings.get('premium_price', 50)} TL\n"
                    f"Süre: {self.data.settings.get('premium_duration', 30)} gün\n\n"
                    f"Premium almak için /admin yazıp admin ile iletişime geçin."
                )
            
            keyboard = [[InlineKeyboardButton(f"{EMOJIS['menu']} Ana Menü", callback_data="main_menu")]]
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif data == "menu_history":
            history = self.data.get_user_queries(user_data.user_id, 10)
            if history:
                text = f"{EMOJIS['database']} *Son 10 Sorgunuz:*\n\n"
                for i, q in enumerate(history, 1):
                    text += f"{i}. {q.query_type.replace('_', ' ').title()}: {q.query_value}\n"
            else:
                text = f"{EMOJIS['info']} Henüz sorgu yapmamışsınız."
            
            keyboard = [[InlineKeyboardButton(f"{EMOJIS['menu']} Ana Menü", callback_data="main_menu")]]
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif data == "menu_help":
            text = (
                f"{EMOJIS['info']} *Yardım & Destek*\n\n"
                f"📌 *Kullanım:*\n"
                f"1. Sorgu menüsünden sorgu tipini seçin\n"
                f"2. İstenen bilgileri girin\n"
                f"3. Sonucu bekleyin\n\n"
                f"🔒 *Gizlilik:* Sorgularınız kayıt altına alınmaz.\n\n"
                f"🆘 *Destek:* {SUPPORT_USERNAME}"
            )
            
            keyboard = [[InlineKeyboardButton(f"{EMOJIS['menu']} Ana Menü", callback_data="main_menu")]]
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif data == "menu_admin":
            if update.effective_user.id in ADMIN_IDS:
                await self.show_admin_menu(update, context)
            else:
                await query.edit_message_text(
                    f"{EMOJIS['error']} Bu alana erişim yetkiniz yok!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJIS['menu']} Ana Menü", callback_data="main_menu")]])
                )
        
        elif data.startswith("search_"):
            api_name = data.replace("search_", "")
            api = self.data.get_api(api_name)
            if not api:
                await query.edit_message_text(
                    f"{EMOJIS['error']} Sorgu türü bulunamadı!",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJIS['menu']} Ana Menü", callback_data="main_menu")]])
                )
                return
            
            if api.is_premium and not user_data.is_premium:
                await query.edit_message_text(
                    f"{EMOJIS['premium']} Bu sorgu premium özelliktir!\n\n"
                    f"Premium üye olmak için /admin yazıp admin ile iletişime geçin.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"{EMOJIS['menu']} Ana Menü", callback_data="main_menu")]])
                )
                return
            
            context.user_data['search_api'] = api_name
            param_examples = [v for v in api.params.values() if v]
            
            await query.edit_message_text(
                f"{EMOJIS['search']} *{api.name.replace('_', ' ').title()} Sorgusu*\n\n"
                f"Lütfen sorgu değerini girin:\n"
                f"Örnek: {', '.join(param_examples) if param_examples else 'Değer'}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJIS['menu']} Vazgeç", callback_data="main_menu")]
                ]),
                parse_mode=ParseMode.MARKDOWN
            )
        
        elif data == "premium_required":
            await query.edit_message_text(
                f"{EMOJIS['premium']} Bu özellik premium üyelik gerektirir!\n\n"
                f"Premium bilgilerinizi görüntülemek için 'Premium Bilgilerim' butonuna tıklayın.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"{EMOJIS['premium']} Premium Bilgilerim", callback_data="menu_premium")],
                    [InlineKeyboardButton(f"{EMOJIS['menu']} Ana Menü", callback_data="main_menu")]
                ])
            )
        
        elif data.startswith("admin_"):
            if update.effective_user.id not in ADMIN_IDS:
                await query.edit_message_text(f"{EMOJIS['error']} Bu alana erişim yetkiniz yok!")
                return
            
            if data == "admin_queries":
                await self.admin_queries_menu(update, context)
            elif data == "admin_users":
                await self.admin_users_menu(update, context)
            elif data == "admin_premium":
                await self.admin_premium_menu(update, context)
            elif data == "admin_settings":
                await self.admin_settings_menu(update, context)
            elif data == "admin_announce":
                await self.admin_announce_menu(update, context)
            elif data == "admin_maintenance":
                await self.admin_maintenance_menu(update, context)
    
    # ======================== ADMIN MENULERİ ========================
    async def admin_queries_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['new']} Yeni Sorgu Ekle", callback_data="admin_add_query")],
            [InlineKeyboardButton(f"{EMOJIS['delete']} Sorgu Sil", callback_data="admin_del_query")],
            [InlineKeyboardButton(f"{EMOJIS['list']} Sorgu Listesi", callback_data="admin_list_queries")],
            [InlineKeyboardButton(f"{EMOJIS['menu']} Geri", callback_data="menu_admin")],
        ]
        
        query = update.callback_query
        await query.edit_message_text(
            f"{EMOJIS['database']} *Sorgu Yönetimi*\n\nMevcut sorguları yönetin:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def admin_users_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['user']} Kullanıcı Listesi", callback_data="admin_user_list")],
            [InlineKeyboardButton(f"{EMOJIS['lock']} Kullanıcı Banla", callback_data="admin_ban_user")],
            [InlineKeyboardButton(f"{EMOJIS['unlock']} Ban Kaldır", callback_data="admin_unban_user")],
            [InlineKeyboardButton(f"{EMOJIS['warning_icon']} Uyarı Ver", callback_data="admin_warn_user")],
            [InlineKeyboardButton(f"{EMOJIS['premium']} Premium Ver", callback_data="admin_give_premium")],
            [InlineKeyboardButton(f"{EMOJIS['menu']} Geri", callback_data="menu_admin")],
        ]
        
        query = update.callback_query
        await query.edit_message_text(
            f"{EMOJIS['user']} *Kullanıcı Yönetimi*\n\nKullanıcı işlemleri:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def admin_premium_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['premium']} Premium Fiyat Ayarla", callback_data="admin_set_price")],
            [InlineKeyboardButton(f"{EMOJIS['money']} Premium Süre Ayarla", callback_data="admin_set_duration")],
            [InlineKeyboardButton(f"{EMOJIS['free']} Premium Ver", callback_data="admin_give_premium")],
            [InlineKeyboardButton(f"{EMOJIS['delete']} Premium Kaldır", callback_data="admin_remove_premium")],
            [InlineKeyboardButton(f"{EMOJIS['menu']} Geri", callback_data="menu_admin")],
        ]
        
        query = update.callback_query
        await query.edit_message_text(
            f"{EMOJIS['premium']} *Premium Yönetimi*\n\nPremium ayarları:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def admin_settings_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        settings = self.data.settings
        text = (
            f"{EMOJIS['settings']} *Ayarlar*\n\n"
            f"Bakım Modu: {'✅ Açık' if settings.get('maintenance_mode', False) else '❌ Kapalı'}\n"
            f"Premium Fiyat: {settings.get('premium_price', 50)} TL\n"
            f"Premium Süre: {settings.get('premium_duration', 30)} gün\n"
            f"Ücretsiz Sorgu Limiti: {settings.get('free_search_limit', 5)}/gün"
        )
        
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['edit']} Bakım Mesajı Düzenle", callback_data="admin_edit_maintenance_msg")],
            [InlineKeyboardButton(f"{EMOJIS['menu']} Geri", callback_data="menu_admin")],
        ]
        
        query = update.callback_query
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def admin_announce_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        keyboard = [
            [InlineKeyboardButton(f"{EMOJIS['new']} Duyuru Ekle", callback_data="admin_add_announce")],
            [InlineKeyboardButton(f"{EMOJIS['delete']} Duyuru Sil", callback_data="admin_del_announce")],
            [InlineKeyboardButton(f"{EMOJIS['list']} Duyurular", callback_data="admin_list_announce")],
            [InlineKeyboardButton(f"{EMOJIS['menu']} Geri", callback_data="menu_admin")],
        ]
        
        query = update.callback_query
        await query.edit_message_text(
            f"{EMOJIS['new']} *Duyuru Yönetimi*\n\nDuyuru işlemleri:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    async def admin_maintenance_menu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        mode = self.data.settings.get("maintenance_mode", False)
        text = (
            f"{EMOJIS['warning_icon']} *Bakım Modu*\n\n"
            f"Durum: {'✅ Açık' if mode else '❌ Kapalı'}\n"
            f"Mesaj: {self.data.settings.get('maintenance_message', 'Bakım çalışması var.')}"
        )
        
        keyboard = [
            [InlineKeyboardButton(
                f"{EMOJIS['lock']} Bakımı Aç" if not mode else f"{EMOJIS['unlock']} Bakımı Kapat",
                callback_data="admin_toggle_maintenance"
            )],
            [InlineKeyboardButton(f"{EMOJIS['edit']} Mesajı Düzenle", callback_data="admin_edit_maintenance_msg")],
            [InlineKeyboardButton(f"{EMOJIS['menu']} Geri", callback_data="menu_admin")],
        ]
        
        query = update.callback_query
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode=ParseMode.MARKDOWN
        )
    
    # ======================== MESAJ HANDLER ========================
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_data, ok = await self.check_user(update)
        if not ok:
            return
        
        message = update.message.text
        user_id = update.effective_user.id
        
        if 'search_api' in context.user_data:
            api_name = context.user_data.pop('search_api')
            api = self.data.get_api(api_name)
            
            if not api:
                await update.message.reply_text(f"{EMOJIS['error']} Sorgu türü bulunamadı!")
                return
            
            await update.message.reply_text(f"{EMOJIS['loading']} Sorgu yapılıyor, lütfen bekleyin...")
            
            params = {}
            param_keys = list(api.params.keys())
            
            if len(param_keys) == 1:
                params[param_keys[0]] = message
            else:
                values = message.split()
                for i, key in enumerate(param_keys):
                    if i < len(values):
                        params[key] = values[i]
                    else:
                        params[key] = ""
            
            async with ApiClient() as client:
                result = await client.get(api.url, params=params, bypass_js=api.bypass_js)
            
            formatted_result = await self.format_result(result, api_name)
            
            query = SearchQuery(
                query_id=str(time.time()),
                user_id=user_id,
                query_type=api_name,
                query_value=message,
                result=result
            )
            self.data.add_query(query)
            
            user_data.search_count += 1
            user_data.last_search = datetime.now().isoformat()
            self.data.save_user(user_data)
            
            await update.message.reply_text(
                f"{formatted_result}\n\n{EMOJIS['menu']} Ana menü için /start yazın."
            )
            
            if user_data.search_count > self.data.settings.get('free_search_limit', 5) and not user_data.is_premium:
                await update.message.reply_text(
                    f"{EMOJIS['warning']} Günlük ücretsiz sorgu limitini aştınız! Premium almak için /admin yazın."
                )
                for admin_id in ADMIN_IDS:
                    try:
                        await self.application.bot.send_message(
                            admin_id,
                            f"{EMOJIS['warning_icon']} Kullanıcı limit aştı!\n"
                            f"Kullanıcı: {user_data.first_name} (@{user_data.username})\n"
                            f"ID: {user_id}\n"
                            f"Sorgu: {api_name} - {message}"
                        )
                    except:
                        pass
        else:
            await update.message.reply_text(
                f"{EMOJIS['info']} Anlamadım. Lütfen butonları kullanın veya /start yazın."
            )
    
    # ======================== HATA YÖNETİMİ ========================
    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logging.error(f"Bot hatası: {context.error}")
        
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    f"{EMOJIS['error']} Bir hata oluştu! Lütfen daha sonra tekrar deneyin."
                )
        except:
            pass
        
        for admin_id in ADMIN_IDS:
            try:
                await self.application.bot.send_message(
                    admin_id,
                    f"{EMOJIS['error']} Bot hatası!\n{str(context.error)[:500]}"
                )
            except:
                pass
    
    # ======================== BOT BAŞLATMA ========================
    def run(self):
        if not self.application:
            asyncio.run(self.initialize())
        
        logging.info("Bot başlatılıyor...")
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

# ======================== ANA PROGRAM ========================
if __name__ == "__main__":
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    
    data_manager = DataManager()
    bot = SorguBot(BOT_TOKEN, data_manager)
    bot.run()
