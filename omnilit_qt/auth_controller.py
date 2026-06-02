from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot

from .app_controller import AppController
from .i18n import LocaleController
from .secrets import protect_secret, unprotect_secret
from .services import AccountStore


class AuthController(QObject):
    """处理本地账号登录、注册和加密密码记忆。"""

    changed = Signal()
    authenticated = Signal()
    loggedOut = Signal()

    def __init__(self, app: AppController, store: AccountStore, locale: LocaleController):
        """初始化账号状态。参数：应用、账号存储和语言控制器。返回值：无。"""
        super().__init__()
        self.app = app
        self.store = store
        self.locale = locale
        self._username = ""
        self._status = ""
        self._remembered_password = ""
        self._restore_remembered_password()

    def _restore_remembered_password(self) -> None:
        """解密上次保存的密码。参数：无。返回值：无。"""
        if self.store.setting("remember_password") != "1":
            return
        try:
            self._remembered_password = unprotect_secret(self.store.setting("remember_secret"))
        except Exception:
            # 密文损坏或跨用户复制时直接清理，避免每次启动重复报错。
            self._clear_login_secret()

    def _clear_login_secret(self) -> None:
        """删除本地登录密文。参数：无。返回值：无。"""
        self._remembered_password = ""
        for key in ("remember_password", "remember_secret"):
            self.store.delete_setting(key)

    def _save_login_secret(self, username: str, password: str, remember_password: bool) -> None:
        """按用户选择保存或清理密码。参数：账号、密码和记忆开关。返回值：无。"""
        self.store.set_setting("remember_username", username.strip())
        if not remember_password:
            self._clear_login_secret()
            return
        self.store.set_setting("remember_password", "1")
        self.store.set_setting("remember_secret", protect_secret(password))
        self._remembered_password = password

    def _set_status(self, value: str) -> None:
        """更新账号状态。参数：消息文本。返回值：无。"""
        self._status = value
        self.app.set_status(value)
        self.changed.emit()

    def _error_text(self, exc: Exception) -> str:
        """翻译账号存储异常。参数：底层异常。返回值：当前语言错误文本。"""
        message = str(exc)
        if self.locale.language == "zh":
            return message
        translations = {
            "用户名至少需要 3 个字符。": "Username must contain at least 3 characters.",
            "密码至少需要 6 个字符。": "Password must contain at least 6 characters.",
            "用户名已存在。": "Username already exists.",
            "请输入用户名和密码。": "Enter your username and password.",
            "账号不存在。": "Account does not exist.",
            "密码不正确。": "Incorrect password.",
        }
        russian = {
            "用户名至少需要 3 个字符。": "Имя пользователя должно содержать не менее 3 символов.",
            "密码至少需要 6 个字符。": "Пароль должен содержать не менее 6 символов.",
            "用户名已存在。": "Имя пользователя уже существует.",
            "请输入用户名和密码。": "Введите имя пользователя и пароль.",
            "账号不存在。": "Аккаунт не существует.",
            "密码不正确。": "Неверный пароль.",
        }
        return (russian if self.locale.language == "ru" else translations).get(message, message)

    @Property(bool, notify=changed)
    def loggedIn(self) -> bool:
        """返回登录状态。参数：无。返回值：是否已登录。"""
        return bool(self._username)

    @Property(str, notify=changed)
    def username(self) -> str:
        """返回当前账号。参数：无。返回值：用户名。"""
        return self._username

    @Property(str, constant=True)
    def rememberedUsername(self) -> str:
        """返回上次账号。参数：无。返回值：用户名。"""
        return self.store.setting("remember_username")

    @Property(str, constant=True)
    def rememberedPassword(self) -> str:
        """返回已解密密码用于自动填充。参数：无。返回值：密码明文。"""
        return self._remembered_password

    @Property(bool, constant=True)
    def rememberPasswordChecked(self) -> bool:
        """返回记住密码复选框初始状态。参数：无。返回值：是否勾选。"""
        return bool(self._remembered_password)

    @Property(str, notify=changed)
    def statusText(self) -> str:
        """返回账号状态。参数：无。返回值：状态文本。"""
        return self._status

    @Slot(str, str, bool, result=bool)
    def login(self, username: str, password: str, remember_password: bool = False) -> bool:
        """登录账号。参数：账号、密码和记忆开关。返回值：是否成功。"""
        try:
            self.store.login(username, password)
            self._save_login_secret(username, password, remember_password)
        except (ValueError, OSError) as exc:
            self._set_status(self._error_text(exc))
            return False
        self._username = username.strip()
        self._set_status(self.locale.textf("logged_in", username=self._username))
        self.authenticated.emit()
        return True

    @Slot(str, str, str, bool, result=bool)
    def registerUser(self, username: str, password: str, confirm_password: str, remember_password: bool = False) -> bool:
        """注册并登录。参数：账号、两次密码和记忆开关。返回值：是否成功。"""
        if password != confirm_password:
            self._set_status(self.locale.textf("password_mismatch"))
            return False
        try:
            self.store.register(username, password)
            self.store.login(username, password)
            self._save_login_secret(username, password, remember_password)
        except (ValueError, OSError) as exc:
            self._set_status(self._error_text(exc))
            return False
        self._username = username.strip()
        self._set_status(self.locale.textf("registered", username=self._username))
        self.authenticated.emit()
        return True

    @Slot()
    def logout(self) -> None:
        """退出当前账号但保留用户选择的密文。参数：无。返回值：无。"""
        self._username = ""
        self._set_status("")
        self.loggedOut.emit()
