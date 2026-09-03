"""Модель данных — specs/001-ai-monitoring-center/data-model.md.

Все модули импортируются здесь, чтобы декларативный реестр SQLAlchemy был полон
до первой конфигурации мапперов: связи объявлены строковыми ссылками и разрешаются
через реестр, а не через пространство имён модуля.
"""

from src.models._base import (
    ActEventType,
    ActStage,
    AssessmentScheme,
    Author,
    Base,
    ItemType,
    Topic,
    utcnow,
)
from src.models.act import Act, ActEvent
from src.models.assessment import Assessment
from src.models.digest import Digest, DigestItem
from src.models.item import Item, Story, Summary
from src.models.profile import CompanyProfile
from src.models.revision import Revision
from src.models.source import Source, SourceCategory, SourceType

__all__ = [
    "Act",
    "ActEvent",
    "ActEventType",
    "ActStage",
    "Assessment",
    "AssessmentScheme",
    "Author",
    "Base",
    "CompanyProfile",
    "Digest",
    "DigestItem",
    "Item",
    "ItemType",
    "Revision",
    "Source",
    "SourceCategory",
    "SourceType",
    "Story",
    "Summary",
    "Topic",
    "utcnow",
]
