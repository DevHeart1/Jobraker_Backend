"""
Settings package initialization.
Default to development settings.
"""

import os

# Default settings module
SETTINGS_MODULE = os.getenv('DJANGO_SETTINGS_MODULE', 'jobraker.settings.development')

# Import the appropriate settings
if SETTINGS_MODULE.endswith('production'):
    from .production import *
elif SETTINGS_MODULE.endswith('testing'):
    from .testing import *
else:
    from .development import *
