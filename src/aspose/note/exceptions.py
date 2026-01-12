from __future__ import annotations


class AsposeNoteError(Exception):
    """Base error for Aspose.Note-compatible Python API."""


class FileCorruptedException(AsposeNoteError):
    pass


class IncorrectDocumentStructureException(AsposeNoteError):
    pass


class IncorrectPasswordException(AsposeNoteError):
    pass


class UnsupportedFileFormatException(AsposeNoteError):
    def __init__(self, message: str = "Unsupported file format", *, file_format: str | None = None):
        super().__init__(message)
        self.FileFormat = file_format


class UnsupportedSaveFormatException(AsposeNoteError):
    pass
