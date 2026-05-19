import sys
import os
import inspect
import html
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QTextEdit, QPushButton, QStatusBar, QListWidget,
    QStackedWidget, QProgressBar, QMessageBox, QGroupBox, QSplitter,
    QStyle, QComboBox, QTabWidget, QLineEdit, QCheckBox, QTextBrowser,
    QFrame, QSizePolicy,
)
from PyQt6.QtCore import QObject, QThread, pyqtSignal, Qt, QSize
from PyQt6.QtGui import QFont, QIcon, QGuiApplication, QColor, QTextCursor

from custom_widgets import SimpleSwitch
from passgenai import passgen
from osintai import osint
from chatbot import Chatbot
from dotenv import load_dotenv, set_key, find_dotenv

# ── Paths ────────────────────────────────────────────────────────────────────
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Available Gemini models ──────────────────────────────────────────────────
AVAILABLE_MODELS = [
    ("gemini-2.0-flash",     "Gemini 2.0 Flash  (Recommended)"),
    ("gemini-2.0-flash-exp", "Gemini 2.0 Flash Exp"),
    ("gemini-1.5-pro",       "Gemini 1.5 Pro  (High Quality)"),
    ("gemini-1.5-flash",     "Gemini 1.5 Flash"),
]

# ── Stylesheet ───────────────────────────────────────────────────────────────
DARK_STYLESHEET = """
    * { outline: none; }

    QWidget {
        background-color: #1e1f23;
        color: #dde1e7;
        font-family: 'Segoe UI', Arial, sans-serif;
        font-size: 10pt;
    }
    QMainWindow { background-color: #16171a; }

    /* ── Tabs ── */
    QTabWidget::pane {
        border: 1px solid #2e3039;
        border-top: 2px solid #3b82f6;
        background-color: #1e1f23;
    }
    QTabBar::tab {
        background: #16171a;
        color: #6b7280;
        border: 1px solid #2a2b30;
        border-bottom: none;
        border-top-left-radius: 6px;
        border-top-right-radius: 6px;
        padding: 7px 20px;
        min-width: 10ex;
        font-weight: 600;
    }
    QTabBar::tab:selected {
        background: #1e1f23;
        color: #dde1e7;
        border-color: #2e3039;
    }
    QTabBar::tab:hover:!selected {
        background: #23242a;
        color: #a0aec0;
    }

    /* ── GroupBox ── */
    QGroupBox {
        font-size: 9pt;
        font-weight: 700;
        color: #6b7280;
        border: 1px solid #2e3039;
        border-radius: 8px;
        margin-top: 14px;
        padding-top: 10px;
        letter-spacing: 0.6px;
        text-transform: uppercase;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 14px;
        padding: 0 6px;
    }

    /* ── Inputs ── */
    QTextEdit, QTextBrowser, QListWidget, QLineEdit {
        background-color: #16171a;
        border: 1px solid #2e3039;
        border-radius: 6px;
        padding: 6px 9px;
        color: #dde1e7;
        selection-background-color: #3b82f6;
    }
    QTextEdit:focus, QLineEdit:focus {
        border-color: #3b82f6;
        background-color: #1a1c20;
    }
    QTextBrowser {
        border-color: #2e3039;
    }
    QListWidget { padding: 4px; }
    QListWidget::item {
        padding: 5px 7px;
        border-radius: 4px;
        border: none;
    }
    QListWidget::item:selected {
        background-color: rgba(59,130,246,0.2);
        color: #93c5fd;
    }
    QListWidget::item:hover:!selected { background-color: #252730; }

    /* ── Buttons ── */
    QPushButton {
        background-color: #3b82f6;
        color: white;
        border: none;
        padding: 8px 20px;
        border-radius: 6px;
        font-size: 10pt;
        font-weight: 700;
        letter-spacing: 0.2px;
    }
    QPushButton:hover { background-color: #5a9af8; }
    QPushButton:pressed { background-color: #2563eb; }
    QPushButton:disabled { background-color: #252730; color: #4b5563; }

    QPushButton#secondary {
        background-color: #252730;
        color: #94a3b8;
    }
    QPushButton#secondary:hover { background-color: #2e3039; color: #dde1e7; }
    QPushButton#secondary:pressed { background-color: #1e1f23; }

    /* ── ComboBox ── */
    QComboBox {
        background-color: #16171a;
        border: 1px solid #2e3039;
        border-radius: 6px;
        padding: 5px 10px;
        color: #dde1e7;
        min-width: 130px;
    }
    QComboBox:hover { border-color: #3b82f6; }
    QComboBox::drop-down {
        subcontrol-origin: padding;
        subcontrol-position: right center;
        width: 22px;
        border-left: 1px solid #2e3039;
        border-top-right-radius: 6px;
        border-bottom-right-radius: 6px;
    }
    QComboBox QAbstractItemView {
        background-color: #1e1f23;
        border: 1px solid #3b82f6;
        selection-background-color: #3b82f6;
        color: #dde1e7;
        padding: 3px;
        border-radius: 4px;
    }

    /* ── Scrollbars ── */
    QScrollBar:vertical {
        background: transparent; width: 7px; margin: 0;
    }
    QScrollBar::handle:vertical {
        background: #3a3d47; border-radius: 3px; min-height: 28px;
    }
    QScrollBar::handle:vertical:hover { background: #55596b; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar:horizontal {
        background: transparent; height: 7px;
    }
    QScrollBar::handle:horizontal {
        background: #3a3d47; border-radius: 3px; min-width: 28px;
    }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

    /* ── Progress bar ── */
    QProgressBar {
        border: none;
        border-radius: 3px;
        background-color: #252730;
        max-height: 5px;
        text-align: center;
    }
    QProgressBar::chunk { background-color: #3b82f6; border-radius: 3px; }

    /* ── Misc ── */
    QLabel { color: #dde1e7; }
    QStatusBar {
        background-color: #16171a;
        color: #6b7280;
        border-top: 1px solid #2a2b30;
        font-size: 9pt;
        padding: 2px 8px;
    }
    QCheckBox { color: #94a3b8; spacing: 7px; }
    QCheckBox::indicator {
        width: 15px; height: 15px;
        border-radius: 4px; border: 1px solid #4b5563;
        background-color: #16171a;
    }
    QCheckBox::indicator:checked {
        background-color: #3b82f6; border-color: #3b82f6;
    }
    QSplitter::handle { background-color: #2a2b30; }
    QSplitter::handle:vertical { height: 3px; }
    QFrame#divider { background-color: #2e3039; }
    QMessageBox { background-color: #1e1f23; }
    QMessageBox QPushButton { min-width: 80px; }
"""

# ── i18n ─────────────────────────────────────────────────────────────────────
LANGUAGES = {
    "en": {
        "window_title": "SentinAI — Cybersecurity Assistant",
        "tab_assistant": "Assistant",
        "tab_chat": "AI Chat",
        "tab_settings": "Settings",
        "language_label": "Language:",
        "groupbox_input_title": "Mode & Input",
        "groupbox_results_title": "Results",
        "groupbox_api_config_title": "API Configuration",
        "groupbox_model_title": "AI Model",
        "passgen_label": "PassGen",
        "osint_label": "OSINT",
        "run_button": "Execute",
        "copy_button": "Copy Selected",
        "api_key_label": "Gemini API Key:",
        "model_label": "Model:",
        "save_api_key_button": "Save Key",
        "show_api_key_checkbox": "Show Key",
        "status_ready": "Ready",
        "status_running_osint": "Running OSINT investigation...",
        "status_running_passgen": "Generating wordlist...",
        "status_finished": "Task finished.",
        "status_error": "An error occurred.",
        "status_no_password_selected": "No password selected.",
        "status_copied": "Copied '{text}' to clipboard.",
        "status_api_key_saved": "API Key saved successfully.",
        "status_api_key_save_error": "Error: Could not save API Key.",
        "status_api_key_is_set": "API Key: set",
        "status_api_key_not_set": "API Key: not set",
        "status_generated_count": "Generated {count} passwords.",
        "error_input_empty_title": "Input Error",
        "error_input_empty_msg": "Input cannot be empty.",
        "error_execution_title": "Execution Error",
        "error_api_key_missing_title": "API Key Missing",
        "error_api_key_missing_msg": "Please go to Settings and save your Gemini API key.",
        "placeholder_passgen": (
            "Enter personal information to generate a wordlist...\n"
            "Example: name=Berk, surname=Küçük, birthdate=2001, "
            "team=trabzonspor, pet=sushi, min_len=6, max_len=12"
        ),
        "placeholder_osint": (
            "Enter a full name, username, or keywords for OSINT investigation...\n"
            "Example: John Doe, johndoe99, software developer new york"
        ),
        "chat_placeholder": "Ask the cybersecurity assistant...",
        "chat_send_button": "Send",
        "chat_clear_button": "Clear",
        "chat_thinking": "Thinking...",
        "chat_error_no_api": "Please set your API key in Settings first.",
        "chat_welcome": (
            "Hello! I'm **SentinAI**, your cybersecurity assistant. "
            "I can help with OSINT, password security, CTFs, threat analysis, and more. "
            "How can I help you today?"
        ),
    },
    "tr": {
        "window_title": "SentinAI — Siber Güvenlik Asistanı",
        "tab_assistant": "Asistan",
        "tab_chat": "AI Sohbet",
        "tab_settings": "Ayarlar",
        "language_label": "Dil:",
        "groupbox_input_title": "Mod & Girdi",
        "groupbox_results_title": "Sonuçlar",
        "groupbox_api_config_title": "API Yapılandırması",
        "groupbox_model_title": "AI Modeli",
        "passgen_label": "Parola Üretici",
        "osint_label": "OSINT Aracı",
        "run_button": "Çalıştır",
        "copy_button": "Seçileni Kopyala",
        "api_key_label": "Gemini API Anahtarı:",
        "model_label": "Model:",
        "save_api_key_button": "Anahtarı Kaydet",
        "show_api_key_checkbox": "Anahtarı Göster",
        "status_ready": "Hazır",
        "status_running_osint": "OSINT araştırması yürütülüyor...",
        "status_running_passgen": "Kelime listesi oluşturuluyor...",
        "status_finished": "Görev tamamlandı.",
        "status_error": "Bir hata oluştu.",
        "status_no_password_selected": "Kopyalamak için parola seçilmedi.",
        "status_copied": "'{text}' panoya kopyalandı.",
        "status_api_key_saved": "API Anahtarı başarıyla kaydedildi.",
        "status_api_key_save_error": "Hata: API Anahtarı kaydedilemedi.",
        "status_api_key_is_set": "API Anahtarı: ayarlanmış",
        "status_api_key_not_set": "API Anahtarı: ayarlanmamış",
        "status_generated_count": "{count} adet parola oluşturuldu.",
        "error_input_empty_title": "Girdi Hatası",
        "error_input_empty_msg": "Girdi alanı boş olamaz.",
        "error_execution_title": "Çalıştırma Hatası",
        "error_api_key_missing_title": "API Anahtarı Eksik",
        "error_api_key_missing_msg": "Lütfen Ayarlar sekmesine gidip Gemini API anahtarını kaydedin.",
        "placeholder_passgen": (
            "Kelime listesi oluşturmak için kişisel bilgi girin...\n"
            "Örnek: isim=Berk, soyisim=Küçük, dogum=2001, "
            "takim=trabzonspor, evcilhayvan=sushi, min_uzunluk=6, max_uzunluk=12"
        ),
        "placeholder_osint": (
            "OSINT araştırması için bir tam isim, kullanıcı adı veya anahtar kelime girin...\n"
            "Örnek: John Doe, johndoe99, yazılım geliştirici new york"
        ),
        "chat_placeholder": "Siber güvenlik asistanına sor...",
        "chat_send_button": "Gönder",
        "chat_clear_button": "Temizle",
        "chat_thinking": "Düşünüyor...",
        "chat_error_no_api": "Lütfen önce Ayarlar'da API anahtarını ayarlayın.",
        "chat_welcome": (
            "Merhaba! Ben **SentinAI**, siber güvenlik asistanınızım. "
            "OSINT, parola güvenliği, CTF, tehdit analizi ve daha fazlasında yardımcı olabilirim. "
            "Nasıl yardımcı olabilirim?"
        ),
    },
    "ru": {
        "window_title": "SentinAI — Ассистент по кибербезопасности",
        "tab_assistant": "Ассистент",
        "tab_chat": "AI Чат",
        "tab_settings": "Настройки",
        "language_label": "Язык:",
        "groupbox_input_title": "Режим и ввод",
        "groupbox_results_title": "Результаты",
        "groupbox_api_config_title": "Конфигурация API",
        "groupbox_model_title": "Модель ИИ",
        "passgen_label": "Генератор паролей",
        "osint_label": "Инструмент OSINT",
        "run_button": "Выполнить",
        "copy_button": "Копировать",
        "api_key_label": "Ключ API Gemini:",
        "model_label": "Модель:",
        "save_api_key_button": "Сохранить ключ",
        "show_api_key_checkbox": "Показать ключ",
        "status_ready": "Готово",
        "status_running_osint": "Выполняется OSINT-расследование...",
        "status_running_passgen": "Создание списка слов...",
        "status_finished": "Задача завершена.",
        "status_error": "Произошла ошибка.",
        "status_no_password_selected": "Пароль для копирования не выбран.",
        "status_copied": "Скопировано '{text}' в буфер обмена.",
        "status_api_key_saved": "Ключ API успешно сохранён.",
        "status_api_key_save_error": "Ошибка: Не удалось сохранить ключ API.",
        "status_api_key_is_set": "API ключ: установлен",
        "status_api_key_not_set": "API ключ: не установлен",
        "status_generated_count": "Сгенерировано {count} паролей.",
        "error_input_empty_title": "Ошибка ввода",
        "error_input_empty_msg": "Поле ввода не может быть пустым.",
        "error_execution_title": "Ошибка выполнения",
        "error_api_key_missing_title": "Отсутствует ключ API",
        "error_api_key_missing_msg": "Перейдите в Настройки и сохраните ключ API Gemini.",
        "placeholder_passgen": (
            "Введите личную информацию для создания списка слов...\n"
            "Пример: имя=Иван, фамилия=Иванов, датарождения=1990, "
            "команда=спартак, питомец=шарик, мин_длина=6, макс_длина=12"
        ),
        "placeholder_osint": (
            "Введите полное имя, имя пользователя или ключевые слова...\n"
            "Пример: Иван Иванов, ivanivanov90, разработчик москва"
        ),
        "chat_placeholder": "Спросите ассистента по кибербезопасности...",
        "chat_send_button": "Отправить",
        "chat_clear_button": "Очистить",
        "chat_thinking": "ИИ думает...",
        "chat_error_no_api": "Сначала установите API-ключ в настройках.",
        "chat_welcome": (
            "Привет! Я **SentinAI**, ваш помощник по кибербезопасности. "
            "Могу помочь с OSINT, безопасностью паролей, CTF, анализом угроз. "
            "Чем могу помочь?"
        ),
    },
}


# ── Worker ───────────────────────────────────────────────────────────────────
class Worker(QObject):
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, func, *args, **kwargs):
        super().__init__()
        self.func = func
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            sig = inspect.signature(self.func)
            if "progress_callback" in sig.parameters:
                result = self.func(*self.args, **self.kwargs, progress_callback=self.progress.emit)
            else:
                result = self.func(*self.args, **self.kwargs)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


# ── Chat Worker (runs in thread to keep UI responsive) ───────────────────────
class ChatWorker(QObject):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, chatbot: Chatbot, message: str):
        super().__init__()
        self.chatbot = chatbot
        self.message = message

    def run(self):
        try:
            reply = self.chatbot.send_message(self.message)
            self.finished.emit(reply)
        except Exception as e:
            self.error.emit(str(e))


# ── Main Window ───────────────────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.current_lang = "en"
        self.current_model = "gemini-2.0-flash"
        self._chatbot: Chatbot | None = None

        self.setGeometry(100, 100, 920, 780)
        self.setMinimumSize(780, 600)

        icon_path = os.path.join(_BASE_DIR, "icons", "icon.png")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            self.setWindowIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon))

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.assistant_tab = QWidget()
        self.tabs.addTab(self.assistant_tab, "Assistant")
        self.setup_assistant_ui()

        self.chat_tab = QWidget()
        self.tabs.addTab(self.chat_tab, "AI Chat")
        self.setup_chat_ui()

        self.settings_tab = QWidget()
        self.tabs.addTab(self.settings_tab, "Settings")
        self.setup_settings_ui()

        self.setStatusBar(QStatusBar(self))

        self.run_button.clicked.connect(self.run_agent_task)
        self.copy_button.clicked.connect(self.copy_selected_password)
        self.agent_selector.stateChanged.connect(self.switch_output_view)
        self.lang_combo.currentIndexChanged.connect(self.switch_language_by_index)
        self.save_api_key_button.clicked.connect(self.save_api_key)
        self.show_api_key_checkbox.stateChanged.connect(self.toggle_api_key_visibility)
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)

        self._load_persisted_model()
        self.check_api_key_status()
        self.switch_language("en")

    # ── Assistant Tab ─────────────────────────────────────────────────────────
    def setup_assistant_ui(self):
        layout = QVBoxLayout(self.assistant_tab)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        # Top bar: language selector
        top_bar = QHBoxLayout()
        top_bar.addStretch()
        self.language_label = QLabel()
        self.language_label.setStyleSheet("color: #6b7280; font-size: 9pt;")
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("English", "en")
        self.lang_combo.addItem("Türkçe", "tr")
        self.lang_combo.addItem("Русский", "ru")
        top_bar.addWidget(self.language_label)
        top_bar.addWidget(self.lang_combo)
        layout.addLayout(top_bar)

        # Input group
        self.input_groupbox = QGroupBox()
        input_layout = QVBoxLayout(self.input_groupbox)
        input_layout.setSpacing(10)
        input_layout.setContentsMargins(12, 22, 12, 12)

        selector_layout = QHBoxLayout()
        selector_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        selector_layout.setSpacing(12)
        self.passgen_label = QLabel()
        self.passgen_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.passgen_label.setStyleSheet("color: #dde1e7;")
        self.agent_selector = SimpleSwitch()
        self.osint_label = QLabel()
        self.osint_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.osint_label.setStyleSheet("color: #dde1e7;")
        selector_layout.addWidget(self.passgen_label)
        selector_layout.addWidget(self.agent_selector)
        selector_layout.addWidget(self.osint_label)
        input_layout.addLayout(selector_layout)

        self.input_text = QTextEdit()
        self.input_text.setMinimumHeight(100)
        input_layout.addWidget(self.input_text)

        action_row = QHBoxLayout()
        self.run_button = QPushButton()
        self.run_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.run_button.setIconSize(QSize(14, 14))
        self.run_button.setMinimumHeight(36)
        self.run_button.setMinimumWidth(140)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #6b7280; font-size: 9pt;")
        self.progress_label.setVisible(False)
        action_row.addWidget(self.run_button)
        action_row.addWidget(self.progress_bar, 1)
        action_row.addWidget(self.progress_label, 3)
        input_layout.addLayout(action_row)

        # Output group
        self.output_groupbox = QGroupBox()
        output_layout = QVBoxLayout(self.output_groupbox)
        output_layout.setContentsMargins(12, 22, 12, 12)

        self.output_stack = QStackedWidget()
        self._setup_passgen_output()
        self._setup_osint_output()
        output_layout.addWidget(self.output_stack)

        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self.input_groupbox)
        splitter.addWidget(self.output_groupbox)
        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 3)
        layout.addWidget(splitter)

    def _setup_passgen_output(self):
        container = QWidget()
        v = QVBoxLayout(container)
        v.setContentsMargins(0, 4, 0, 0)
        v.setSpacing(8)

        self.passgen_count_label = QLabel("")
        self.passgen_count_label.setStyleSheet("color: #6b7280; font-size: 9pt;")

        self.passgen_list_widget = QListWidget()
        font = QFont("Consolas", 10)
        self.passgen_list_widget.setFont(font)

        btn_row = QHBoxLayout()
        self.copy_button = QPushButton()
        self.copy_button.setObjectName("secondary")
        self.copy_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogContentsView))
        self.copy_button.setIconSize(QSize(14, 14))
        self.copy_button.setFixedWidth(180)
        btn_row.addStretch()
        btn_row.addWidget(self.copy_button)

        v.addWidget(self.passgen_count_label)
        v.addWidget(self.passgen_list_widget)
        v.addLayout(btn_row)
        self.output_stack.addWidget(container)

    def _setup_osint_output(self):
        self.osint_result_browser = QTextBrowser()
        self.osint_result_browser.setOpenExternalLinks(True)
        self.osint_result_browser.setFont(QFont("Segoe UI", 10))
        self.output_stack.addWidget(self.osint_result_browser)

    # ── Chat Tab ──────────────────────────────────────────────────────────────
    def setup_chat_ui(self):
        layout = QVBoxLayout(self.chat_tab)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(0)

        # Header row
        header_row = QHBoxLayout()
        chat_title = QLabel("SentinAI Chat")
        chat_title.setStyleSheet("color: #dde1e7; font-size: 11pt; font-weight: 700;")
        self.chat_clear_button = QPushButton()
        self.chat_clear_button.setObjectName("secondary")
        self.chat_clear_button.setFixedWidth(110)
        self.chat_clear_button.setFixedHeight(30)
        self.chat_clear_button.clicked.connect(self.clear_chat)
        header_row.addWidget(chat_title)
        header_row.addStretch()
        header_row.addWidget(self.chat_clear_button)
        layout.addLayout(header_row)

        # Divider
        line = QFrame()
        line.setObjectName("divider")
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        layout.addSpacing(8)
        layout.addWidget(line)
        layout.addSpacing(8)

        # Chat history
        self.chat_browser = QTextBrowser()
        self.chat_browser.setOpenExternalLinks(True)
        self.chat_browser.setFont(QFont("Segoe UI", 10))
        self.chat_browser.setStyleSheet(
            "QTextBrowser { background-color: #16171a; border: 1px solid #2e3039; "
            "border-radius: 8px; padding: 8px; }"
        )
        layout.addWidget(self.chat_browser, 1)
        layout.addSpacing(8)

        # Input row
        input_row = QHBoxLayout()
        input_row.setSpacing(8)
        self.chat_input = QLineEdit()
        self.chat_input.setMinimumHeight(38)
        self.chat_input.returnPressed.connect(self.send_chat_message)
        self.chat_send_button = QPushButton()
        self.chat_send_button.setMinimumHeight(38)
        self.chat_send_button.setMinimumWidth(90)
        self.chat_send_button.clicked.connect(self.send_chat_message)
        input_row.addWidget(self.chat_input)
        input_row.addWidget(self.chat_send_button)
        layout.addLayout(input_row)

    # ── Settings Tab ──────────────────────────────────────────────────────────
    def setup_settings_ui(self):
        layout = QVBoxLayout(self.settings_tab)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(16)

        # API Key
        self.api_config_groupbox = QGroupBox()
        api_layout = QVBoxLayout(self.api_config_groupbox)
        api_layout.setSpacing(12)
        api_layout.setContentsMargins(14, 24, 14, 14)

        key_row = QHBoxLayout()
        self.api_key_label = QLabel()
        self.api_key_label.setFixedWidth(155)
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.api_key_input.setMinimumHeight(34)
        key_row.addWidget(self.api_key_label)
        key_row.addWidget(self.api_key_input)
        api_layout.addLayout(key_row)

        controls_row = QHBoxLayout()
        self.show_api_key_checkbox = QCheckBox()
        self.save_api_key_button = QPushButton()
        self.save_api_key_button.setFixedWidth(120)
        self.save_api_key_button.setMinimumHeight(34)
        self.api_status_label = QLabel()
        self.api_status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.api_status_label.setStyleSheet("font-size: 9pt; font-weight: 600;")
        controls_row.addWidget(self.show_api_key_checkbox)
        controls_row.addStretch()
        controls_row.addWidget(self.api_status_label)
        controls_row.addSpacing(12)
        controls_row.addWidget(self.save_api_key_button)
        api_layout.addLayout(controls_row)

        layout.addWidget(self.api_config_groupbox)

        # Model selector
        self.model_groupbox = QGroupBox()
        model_layout = QVBoxLayout(self.model_groupbox)
        model_layout.setContentsMargins(14, 24, 14, 14)

        model_row = QHBoxLayout()
        self.model_label_widget = QLabel()
        self.model_label_widget.setFixedWidth(155)
        self.model_combo = QComboBox()
        for mid, mname in AVAILABLE_MODELS:
            self.model_combo.addItem(mname, mid)
        model_row.addWidget(self.model_label_widget)
        model_row.addWidget(self.model_combo)
        model_row.addStretch()
        model_layout.addLayout(model_row)

        layout.addWidget(self.model_groupbox)
        layout.addStretch()

    # ── Language ──────────────────────────────────────────────────────────────
    def switch_language_by_index(self, index: int):
        code = self.lang_combo.itemData(index)
        if code:
            self.switch_language(code)

    def switch_language(self, lang_code: str):
        self.current_lang = lang_code
        lang = LANGUAGES[lang_code]

        idx = self.lang_combo.findData(lang_code)
        if idx != -1:
            self.lang_combo.blockSignals(True)
            self.lang_combo.setCurrentIndex(idx)
            self.lang_combo.blockSignals(False)

        self.setWindowTitle(lang["window_title"])
        self.tabs.setTabText(0, lang["tab_assistant"])
        self.tabs.setTabText(1, lang["tab_chat"])
        self.tabs.setTabText(2, lang["tab_settings"])

        self.language_label.setText(lang["language_label"])
        self.input_groupbox.setTitle(lang["groupbox_input_title"])
        self.output_groupbox.setTitle(lang["groupbox_results_title"])
        self.passgen_label.setText(lang["passgen_label"])
        self.osint_label.setText(lang["osint_label"])
        self.run_button.setText(lang["run_button"])
        self.copy_button.setText(lang["copy_button"])
        self.statusBar().showMessage(lang["status_ready"])

        self.chat_send_button.setText(lang["chat_send_button"])
        self.chat_clear_button.setText(lang["chat_clear_button"])
        self.chat_input.setPlaceholderText(lang["chat_placeholder"])

        self.api_config_groupbox.setTitle(lang["groupbox_api_config_title"])
        self.api_key_label.setText(lang["api_key_label"])
        self.save_api_key_button.setText(lang["save_api_key_button"])
        self.show_api_key_checkbox.setText(lang["show_api_key_checkbox"])
        self.model_groupbox.setTitle(lang["groupbox_model_title"])
        self.model_label_widget.setText(lang["model_label"])

        self.check_api_key_status()
        self.switch_output_view()

    # ── Settings: API key ─────────────────────────────────────────────────────
    def check_api_key_status(self):
        lang = LANGUAGES[self.current_lang]
        env_path = os.path.join(_BASE_DIR, ".env")
        load_dotenv(env_path)
        if os.getenv("GOOGLE_API_KEY"):
            self.api_status_label.setText(lang["status_api_key_is_set"])
            self.api_status_label.setStyleSheet("color: #22c55e; font-size: 9pt; font-weight: 600;")
            if not self.api_key_input.text():
                self.api_key_input.setText("*" * 20)
        else:
            self.api_status_label.setText(lang["status_api_key_not_set"])
            self.api_status_label.setStyleSheet("color: #ef4444; font-size: 9pt; font-weight: 600;")

    def save_api_key(self):
        lang = LANGUAGES[self.current_lang]
        api_key = self.api_key_input.text().strip()
        if not api_key or set(api_key) == {"*"}:
            self.check_api_key_status()
            return
        try:
            env_file = find_dotenv(usecwd=False) or os.path.join(_BASE_DIR, ".env")
            set_key(env_file, "GOOGLE_API_KEY", api_key)
            self._chatbot = None  # reset chatbot so it picks up new key
            QMessageBox.information(self, lang["window_title"], lang["status_api_key_saved"])
            self.check_api_key_status()
        except Exception as e:
            QMessageBox.critical(self, lang["window_title"],
                                 f"{lang['status_api_key_save_error']}\n{e}")

    def toggle_api_key_visibility(self, state):
        mode = (QLineEdit.EchoMode.Normal if state == Qt.CheckState.Checked.value
                else QLineEdit.EchoMode.Password)
        self.api_key_input.setEchoMode(mode)

    # ── Settings: Model ───────────────────────────────────────────────────────
    def _load_persisted_model(self):
        env_path = os.path.join(_BASE_DIR, ".env")
        load_dotenv(env_path)
        saved = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        idx = self.model_combo.findData(saved)
        if idx != -1:
            self.model_combo.blockSignals(True)
            self.model_combo.setCurrentIndex(idx)
            self.model_combo.blockSignals(False)
        self.current_model = saved

    def on_model_changed(self, index: int):
        model_id = self.model_combo.itemData(index)
        if not model_id:
            return
        self.current_model = model_id
        self._chatbot = None  # reset chatbot to use new model
        try:
            env_file = find_dotenv(usecwd=False) or os.path.join(_BASE_DIR, ".env")
            set_key(env_file, "GEMINI_MODEL", model_id)
        except Exception:
            pass

    # ── Assistant: run ────────────────────────────────────────────────────────
    def switch_output_view(self):
        lang = LANGUAGES[self.current_lang]
        if self.agent_selector.isChecked():
            self.output_stack.setCurrentIndex(1)
            self.input_text.setPlaceholderText(lang["placeholder_osint"])
        else:
            self.output_stack.setCurrentIndex(0)
            self.input_text.setPlaceholderText(lang["placeholder_passgen"])

    def run_agent_task(self):
        lang = LANGUAGES[self.current_lang]
        env_path = os.path.join(_BASE_DIR, ".env")
        load_dotenv(env_path)
        if not os.getenv("GOOGLE_API_KEY"):
            QMessageBox.warning(self,
                                lang["error_api_key_missing_title"],
                                lang["error_api_key_missing_msg"])
            self.tabs.setCurrentIndex(2)
            return

        user_input = self.input_text.toPlainText().strip()
        if not user_input:
            QMessageBox.warning(self, lang["error_input_empty_title"], lang["error_input_empty_msg"])
            return

        self.run_button.setEnabled(False)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setVisible(True)
        self.progress_label.setVisible(True)
        self.progress_label.setText("")

        is_osint = self.agent_selector.isChecked()
        if is_osint:
            self.statusBar().showMessage(lang["status_running_osint"])
            self.worker = Worker(osint, user_input, self.current_lang)
        else:
            self.statusBar().showMessage(lang["status_running_passgen"])
            self.worker = Worker(passgen, user_input, self.current_model)

        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.on_task_finished)
        self.worker.error.connect(self.on_task_error)
        self.worker.progress.connect(self.on_task_progress)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.worker.error.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    def on_task_progress(self, message: str):
        self.progress_label.setText(message)
        self.statusBar().showMessage(message)

    def on_task_finished(self, result):
        lang = LANGUAGES[self.current_lang]
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.run_button.setEnabled(True)

        if self.agent_selector.isChecked():
            # OSINT → markdown string
            self.osint_result_browser.setMarkdown(str(result))
            self.statusBar().showMessage(lang["status_finished"])
        else:
            # PassGen → list[str]
            passwords = result if isinstance(result, list) else []
            self.passgen_list_widget.clear()
            self.passgen_list_widget.addItems(passwords)
            count = len(passwords)
            msg = lang["status_generated_count"].format(count=count)
            self.passgen_count_label.setText(msg)
            self.statusBar().showMessage(msg)

    def on_task_error(self, error_message: str):
        lang = LANGUAGES[self.current_lang]
        self.progress_bar.setVisible(False)
        self.progress_label.setVisible(False)
        self.run_button.setEnabled(True)
        self.statusBar().showMessage(lang["status_error"])
        QMessageBox.critical(self, lang["error_execution_title"], error_message)

    def copy_selected_password(self):
        lang = LANGUAGES[self.current_lang]
        selected = self.passgen_list_widget.selectedItems()
        if not selected:
            self.statusBar().showMessage(lang["status_no_password_selected"])
            return
        text = selected[0].text()
        QGuiApplication.clipboard().setText(text)
        self.statusBar().showMessage(lang["status_copied"].format(text=text))

    # ── Chat ──────────────────────────────────────────────────────────────────
    def _get_chatbot(self) -> Chatbot | None:
        if self._chatbot:
            return self._chatbot
        env_path = os.path.join(_BASE_DIR, ".env")
        load_dotenv(env_path)
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            return None
        self._chatbot = Chatbot(api_key, self.current_model)
        # Show welcome on first init
        lang = LANGUAGES[self.current_lang]
        self._append_chat_message(lang["chat_welcome"], is_user=False)
        return self._chatbot

    def send_chat_message(self):
        lang = LANGUAGES[self.current_lang]
        user_text = self.chat_input.text().strip()
        if not user_text:
            return

        bot = self._get_chatbot()
        if bot is None:
            QMessageBox.warning(self, lang["error_api_key_missing_title"],
                                lang["chat_error_no_api"])
            self.tabs.setCurrentIndex(2)
            return

        self.chat_input.clear()
        self._append_chat_message(user_text, is_user=True)
        self.chat_send_button.setEnabled(False)
        self.chat_input.setEnabled(False)
        self.statusBar().showMessage(lang["chat_thinking"])

        self._chat_worker = ChatWorker(bot, user_text)
        self._chat_thread = QThread()
        self._chat_worker.moveToThread(self._chat_thread)
        self._chat_thread.started.connect(self._chat_worker.run)
        self._chat_worker.finished.connect(self.on_chat_reply)
        self._chat_worker.error.connect(self.on_chat_error)
        self._chat_worker.finished.connect(self._chat_thread.quit)
        self._chat_worker.error.connect(self._chat_thread.quit)
        self._chat_worker.finished.connect(self._chat_worker.deleteLater)
        self._chat_worker.error.connect(self._chat_worker.deleteLater)
        self._chat_thread.finished.connect(self._chat_thread.deleteLater)
        self._chat_thread.start()

    def on_chat_reply(self, reply: str):
        lang = LANGUAGES[self.current_lang]
        self._append_chat_message(reply, is_user=False)
        self.chat_send_button.setEnabled(True)
        self.chat_input.setEnabled(True)
        self.chat_input.setFocus()
        self.statusBar().showMessage(lang["status_ready"])

    def on_chat_error(self, error_message: str):
        lang = LANGUAGES[self.current_lang]
        self._append_chat_message(f"Error: {error_message}", is_user=False)
        self.chat_send_button.setEnabled(True)
        self.chat_input.setEnabled(True)
        self.statusBar().showMessage(lang["status_error"])

    def clear_chat(self):
        self.chat_browser.clear()
        if self._chatbot:
            self._chatbot.clear_history()

    def _append_chat_message(self, text: str, is_user: bool):
        safe = html.escape(text).replace("\n", "<br>")
        # Bold **text** support (simple)
        import re
        safe = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", safe)

        if is_user:
            block = (
                f'<div style="margin:6px 2px; text-align:right;">'
                f'<span style="background:#3b82f6; color:#fff; border-radius:14px 14px 4px 14px; '
                f'padding:8px 14px; display:inline-block; max-width:78%; word-wrap:break-word; '
                f'font-size:9.5pt; line-height:1.5;">{safe}</span>'
                f'<div style="color:#4b5563; font-size:7.5pt; margin-top:3px; margin-right:4px;">You</div>'
                f'</div>'
            )
        else:
            block = (
                f'<div style="margin:6px 2px; text-align:left;">'
                f'<div style="color:#3b82f6; font-size:7.5pt; margin-bottom:3px; '
                f'margin-left:4px; font-weight:700; letter-spacing:0.5px;">SENTINAI</div>'
                f'<span style="background:#252730; color:#dde1e7; border-radius:14px 14px 14px 4px; '
                f'padding:8px 14px; display:inline-block; max-width:78%; word-wrap:break-word; '
                f'font-size:9.5pt; line-height:1.5; border:1px solid #2e3039;">{safe}</span>'
                f'</div>'
            )

        cursor = self.chat_browser.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        self.chat_browser.setTextCursor(cursor)
        self.chat_browser.insertHtml(block + "<br>")
        self.chat_browser.verticalScrollBar().setValue(
            self.chat_browser.verticalScrollBar().maximum()
        )


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
