from py2app.build_app import setup

APP = ['gusto.py']
DATA_FILES = []
OPTIONS = {
    'argv_emulation': False,
    'iconfile': 'icon.icns',
    'plist': {
        'CFBundleName': 'GustoPunch',
        'CFBundleDisplayName': 'GustoPunch',
        'CFBundleGetInfoString': "Track your work hours in Gusto",
        'CFBundleIdentifier': "com.yourcompany.gustopunch",
        'CFBundleVersion': "0.1.0",
        'CFBundleShortVersionString': "0.1.0",
        'LSUIElement': True,  # Makes it a background app with menu bar icon
    },
    'packages': ['rumps', 'selenium', 'keyring', 'webdriver_manager'],
}

if __name__ == '__main__':
    import sys
    import shutil
    import os
    
    # Clean up any existing build artifacts
    if os.path.exists('build'):
        shutil.rmtree('build')
    if os.path.exists('dist'):
        shutil.rmtree('dist')
        
    # Run the setup
    sys.argv = [sys.argv[0], 'py2app']
    setup(
        app=APP,
        data_files=DATA_FILES,
        options={'py2app': OPTIONS},
    )