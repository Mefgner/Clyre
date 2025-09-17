import os
import re
from abc import ABC, abstractmethod
from pathlib import Path

from sqlalchemy import Integer, String, Date, ForeignKey, Text
from sqlalchemy.orm import mapped_column, relationship

from . import Base

WORKDIR = Path(os.getenv('WORKDIR', '.')).resolve()


class PayloadError(Exception): ...


class PayloadNotFound(PayloadError): ...


class InvalidKey(PayloadError): ...


def error_redirect(func):
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except FileNotFoundError:
            raise PayloadNotFound("Payload not found")
        except ValueError:
            raise InvalidKey("Invalid sha256 or user_id")

    return wrapper


class PayloadStore(ABC):
    @abstractmethod
    @error_redirect
    def __init__(self, user_id: str, sha256: str, encoding: str):
        self._user_id = user_id
        self._sha256 = sha256
        self._encoding = encoding

        for p in [user_id, sha256]:
            if not re.match(r'^[A-Za-z0-9_\-]{1,128}$', p):
                raise ValueError()

    @abstractmethod
    @error_redirect
    def read(self) -> str:
        ...

    @abstractmethod
    @error_redirect
    def write(self, payload: str) -> None:
        ...

    @abstractmethod
    @error_redirect
    def append(self, payload: str) -> None:
        ...


class FSPayloadStore(PayloadStore):
    def __init__(self, user_id: str, sha256: str, encoding: str):
        super().__init__(user_id, sha256, encoding)
        self.file_path = WORKDIR / 'payload' / user_id / (sha256 + '.txt')
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    @error_redirect
    def read(self):
        with open(self.file_path, 'r', encoding=self._encoding) as file:
            return file.read()

    @error_redirect
    def write(self, text):
        with open(self.file_path, 'w', encoding=self._encoding) as file:
            file.write(text)

    @error_redirect
    def append(self, text):
        with open(self.file_path, 'a', encoding=self._encoding) as file:
            file.write(text)


class EXTPayloadStore(PayloadStore):
    def __init__(self, user_id: str, sha256: str, encoding: str):
        super().__init__(user_id, sha256, encoding)

    def read(self): ...

    def write(self, text): ...

    def append(self, text): ...


class File(Base):
    __tablename__ = "file"

    user_id = mapped_column(String(36), ForeignKey("user.id"), nullable=False, index=True)
    name = mapped_column(String(255), nullable=False)
    inline_value = mapped_column(Text, nullable=True)
    hash = mapped_column(String(64), nullable=False, index=True)
    keywords = mapped_column(String(255), nullable=True)
    creation_date = mapped_column(Date, nullable=True)

    user = relationship("User", back_populates="files")
    thread_links = relationship("FileHasThread", back_populates="file")
    project_links = relationship("FileHasProject", back_populates="file")

    @property
    def payload_store(self) -> "PayloadStore":
        return FSPayloadStore("global", self.hash, "utf-8")
        # return EXTPayloadStore("global", self.hash, "utf-8")


class FileHasThread(Base):
    __tablename__ = "file_has_thread"

    file_id = mapped_column(Integer, ForeignKey("file.id"), primary_key=True)
    thread_id = mapped_column(Integer, ForeignKey("thread.id"), primary_key=True)

    file = relationship("File", back_populates="thread_links")
    thread = relationship("Thread", back_populates="file_links")


class FileHasProject(Base):
    __tablename__ = "file_has_project"

    file_id = mapped_column(Integer, ForeignKey("file.id"), primary_key=True)
    project_id = mapped_column(Integer, ForeignKey("project.id"), primary_key=True)

    file = relationship("File", back_populates="project_links")
    project = relationship("Project", back_populates="file_links")


__all__ = ["File", "FileHasThread", "FileHasProject"]
