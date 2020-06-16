"""FastAPI tools library for building DRF-like viewsets"""

__version__ = '0.2.0'

from .schemas import Schema
from .viewsets import ModelViewSet, ViewSet

__all__ = ('Schema', 'ModelViewSet', 'ViewSet')
