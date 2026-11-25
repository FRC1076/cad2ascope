"""Errors and warnings written for students.

Every message names the mate, part, or link, says what is wrong, and says what to change in Onshape or in
cad/advantagescope.yaml (CLAUDE.md, PLAN §6.6). Errors stop the build and exit non-zero; warnings do not.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class CadError(Exception):
    """A problem the student can fix. The message is shown as-is, so write it for a ninth grader."""


@dataclass
class Warnings:
    """Collects warnings in the order they are found. Duplicates are kept once."""

    messages: list[str] = field(default_factory=list)

    def add(self, message: str) -> None:
        if message not in self.messages:
            self.messages.append(message)

    def __iter__(self):
        return iter(self.messages)

    def __len__(self) -> int:
        return len(self.messages)
