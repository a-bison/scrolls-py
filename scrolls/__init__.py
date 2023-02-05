"""
Scrolls is a small, embeddable scripting engine with an emphasis on abuse prevention, designed to be used
in bots for chat services such as Discord.

.. include:: pdoc/scrolls.md
"""

from .ast import *
from .builtins import *
from .containers import *
from .errors import *
from .interpreter import *

__version__ = "0.3.1"
