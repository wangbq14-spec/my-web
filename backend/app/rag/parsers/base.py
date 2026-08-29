from dataclasses import dataclass


@dataclass
class ParsedDocument:
    text: str
    metadata: dict


class ParserError(Exception):
    """Raised when a supported document cannot be converted to usable text."""
