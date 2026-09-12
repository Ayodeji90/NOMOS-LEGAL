"""Legal corpus parsers for different jurisdictions."""

from .za_parser import ZAParser
from .gb_parser import GBParser
from .ng_parser import NGParser

__all__ = ["ZAParser", "GBParser", "NGParser"]