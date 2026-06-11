"""Compatibility exports for Qt controller classes.

Controller implementations live in focused modules. Importing from
``omnilit_qt.controllers`` remains supported for existing callers.
"""

from .app_controller import AppController
from .auth_controller import AuthController
from .download_controller import DOWNLOAD_FORM_SETTING, DownloadController
from .literature_library_controller import LiteratureLibraryController
from .onboarding_controller import OnboardingController
from .pdf_extraction_controller import PdfExtractionController
from .preferences_controller import PreferencesController
from .translation_controller import TRANSLATION_FORM_SETTING, TranslationController
from .update_controller import DEFAULT_UPDATE_MANIFEST_URL, UpdateController

__all__ = [
    "AppController",
    "AuthController",
    "DEFAULT_UPDATE_MANIFEST_URL",
    "DOWNLOAD_FORM_SETTING",
    "DownloadController",
    "LiteratureLibraryController",
    "OnboardingController",
    "PdfExtractionController",
    "PreferencesController",
    "TRANSLATION_FORM_SETTING",
    "TranslationController",
    "UpdateController",
]
