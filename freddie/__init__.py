"""FastAPI tools library for building DRF-like viewsets"""

__version__ = '0.2.1'

from .schemas import Schema
from .viewsets import ViewSet

__all__ = ('Schema', 'ViewSet')
