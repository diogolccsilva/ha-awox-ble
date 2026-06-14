"""Test fixtures / path setup.

The protocol module is intentionally dependency-free, so we import it directly
from the integration folder. This avoids importing the package's ``__init__``
(which pulls in Home Assistant) and lets the protocol be tested in isolation.
"""

import pathlib
import sys

_PROTOCOL_DIR = (
    pathlib.Path(__file__).resolve().parent.parent / "custom_components" / "awox_plug"
)
sys.path.insert(0, str(_PROTOCOL_DIR))
