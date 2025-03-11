#!/usr/bin/env python3
"""
Alternative setup approach that uses a more direct method
for creating a macOS app bundle
"""
from setuptools import setup

APP = ['main.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': False, 
    'iconfile': 'icon.icns',
    'plist': {
        'CFBundleName': 'GustoPunch',
        'CFBundleDisplayName': 'GustoPunch',
        'CFBundleIdentifier': "com.yourcompany.gustopunch",
        'CFBundleVersion': "0.1.0",
        'CFBundleShortVersionString': "0.1.0",
        'LSBackgroundOnly': True,  # Alternative to LSUIElement
        'LSUIElement': True,  # Menu bar only app
    },
    # Minimal dependencies approach - specify only what's strictly needed
    'includes': ['rumps', 'selenium', 'keyring', 'webdriver_manager'],
    # Force use of Python from system rather than bundling it
    'semi_standalone': True,
    # Do not try to create a compressed .app bundle
    'compressed': False,
    # Don't try to strip the binaries
    'strip': False,
    # Use the newer site packages format
    'site_packages': True,
}

setup(
    name="GustoPunch",
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
    install_requires=[
        'rumps>=0.4.0',
        'selenium>=4.29.0',
        'keyring>=25.6.0',
        'webdriver-manager>=4.0.2'
    ],
)