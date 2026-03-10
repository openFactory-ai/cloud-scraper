"""Abstract provider interface for cloud data export."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


class DataType(Enum):
    EMAIL = "email"
    CONTACTS = "contacts"
    CALENDAR = "calendar"
    DRIVE = "drive"
    PHOTOS = "photos"


@dataclass
class ExportProgress:
    """Progress update from an export operation."""
    data_type: DataType
    current: int
    total: int
    message: str


ProgressCallback = Callable[[ExportProgress], None]


class BaseProvider(ABC):
    """Abstract base class for cloud data providers."""

    name: str = ""
    icon_name: str = ""
    supported_data_types: list[DataType] = []
    experimental: bool = False

    def __init__(self):
        self._authenticated = False
        self._user_email: str | None = None
        self.last_error: str | None = None

    @property
    def is_authenticated(self) -> bool:
        return self._authenticated

    @property
    def user_email(self) -> str | None:
        return self._user_email

    @abstractmethod
    def authenticate(self) -> bool:
        """Run the OAuth/auth flow. Returns True on success."""
        ...

    @abstractmethod
    def export_data(
        self,
        data_types: list[DataType],
        dest_dir: Path,
        progress_cb: ProgressCallback | None = None,
    ) -> dict[DataType, Path]:
        """Export selected data types to dest_dir.

        Returns a mapping of data type to the output path.
        """
        ...

    def disconnect(self) -> None:
        """Clear stored credentials."""
        self._authenticated = False
        self._user_email = None
