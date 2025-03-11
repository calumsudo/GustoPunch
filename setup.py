from setuptools import setup

APP = ['gusto.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': True,
    'iconfile': 'icon.icns',  # You'll need to create this icon file
    'plist': {
        'CFBundleName': 'GustoPunch',
        'CFBundleDisplayName': 'GustoPunch',
        'CFBundleGetInfoString': "Track your work hours in Gusto",
        'CFBundleIdentifier': "com.yourcompany.gustopunch",
        'CFBundleVersion': "0.1.0",
        'CFBundleShortVersionString': "0.1.0",
        'NSHumanReadableCopyright': "Copyright © 2024, Your Name, All Rights Reserved",
        'NSAppleEventsUsageDescription': 'This app needs access to run automation',
        'LSUIElement': True,  # This makes it a background app with only a menu bar icon
    },
    'packages': ['rumps', 'selenium', 'keyring', 'webdriver_manager'],
    'includes': ['pkg_resources.py2_warn'],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
)