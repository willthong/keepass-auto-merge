"""Decide whether merging a conflict file is a clean fast-forward.

`keepassxc-cli merge` is always keep-newer and never applies deletions, so a merge that looks
routine can silently discard a change someone made in the master, or ignore a deletion someone made
in the conflict file. This module compares the two databases entry by entry and reports anything
that is not a clean fast-forward, without changing either database.
"""

from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime

EMPTY_RECYCLE_BIN = "AAAAAAAAAAAAAAAAAAAAAA=="


@dataclass(frozen=True)
class EntryRef:
    """An entry as it exists in one database."""

    uuid: str
    title: str
    path: str
    last_modified: datetime | None


@dataclass(frozen=True)
class EntryRecord:
    """An entry plus every revision the database remembers for it."""

    ref: EntryRef
    revisions: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class Classification:
    added: list[EntryRef] = field(default_factory=list)
    deletions: list[EntryRef] = field(default_factory=list)
    master_newer: list[EntryRef] = field(default_factory=list)
    both_changed: list[EntryRef] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.deletions or self.master_newer or self.both_changed)

    def report(self) -> str:
        """Journal-ready lines for everything a human should look at."""
        lines: list[str] = []
        for entry in self.deletions:
            lines.append(
                f"ERROR: not a clean fast-forward: {entry.title!r} ({entry.path}, {entry.uuid}) "
                "is missing from the conflict file; keep-newer will not delete it from the master"
            )
        for entry in self.master_newer:
            lines.append(
                f"ERROR: not a clean fast-forward: {entry.title!r} ({entry.path}, {entry.uuid}) "
                "is newer in the master; the conflict file's version will be discarded"
            )
        for entry in self.both_changed:
            lines.append(
                f"ERROR: not a clean fast-forward: {entry.title!r} ({entry.path}, {entry.uuid}) "
                "changed on both sides; keep-newer keeps the master's version"
            )
        return "\n".join(lines)


def parse_export(xml_text: str) -> dict[str, EntryRecord]:
    """Index a KeePass XML export by entry UUID, current revision plus history."""
    root = ET.fromstring(xml_text)
    recycle_bin = _text(root.find("Meta/RecycleBinUUID"))
    records: dict[str, EntryRecord] = {}

    for group in _groups(root.find("Root")):
        if _text(group.find("UUID")) == recycle_bin and recycle_bin != EMPTY_RECYCLE_BIN:
            continue
        group_path = _group_path(group)
        for entry in group.findall("Entry"):
            record = _record(entry, group_path)
            if record is not None:
                records[record.ref.uuid] = record
    return records


def classify(master: dict[str, EntryRecord], conflict: dict[str, EntryRecord]) -> Classification:
    """Compare two databases and say whether the conflict file is a clean fast-forward."""
    deletions = [master[uuid].ref for uuid in sorted(set(master) - set(conflict))]
    added = [conflict[uuid].ref for uuid in sorted(set(conflict) - set(master))]

    master_newer: list[EntryRef] = []
    both_changed: list[EntryRef] = []
    for uuid in sorted(set(master) & set(conflict)):
        master_record, conflict_record = master[uuid], conflict[uuid]
        changed_in_master = _changed_since_ancestor(master_record, conflict_record)
        changed_in_conflict = _changed_since_ancestor(conflict_record, master_record)
        if changed_in_master and changed_in_conflict:
            both_changed.append(master_record.ref)
        elif changed_in_master:
            master_newer.append(master_record.ref)

    return Classification(
        added=added,
        deletions=deletions,
        master_newer=master_newer,
        both_changed=both_changed,
    )


def _changed_since_ancestor(record: EntryRecord, other: EntryRecord) -> bool:
    """Did `record` change after its newest revision that `other` also knows about?"""
    shared = set(record.revisions) & set(other.revisions)
    if not shared:
        return record.ref.uuid != other.ref.uuid and record.revisions != other.revisions
    ancestor = max(shared)
    ancestor_fingerprint = record.revisions[ancestor]
    return any(
        stamp > ancestor and fingerprint != ancestor_fingerprint
        for stamp, fingerprint in record.revisions.items()
    )


def _record(entry: ET.Element, group_path: str) -> EntryRecord | None:
    uuid = _text(entry.find("UUID"))
    if not uuid:
        return None
    ref = EntryRef(
        uuid=uuid,
        title=_value(entry, "Title"),
        path=group_path,
        last_modified=_modified(entry),
    )
    revisions = {}
    for revision in [entry, *entry.findall("History/Entry")]:
        stamp = _stamp(revision)
        if stamp is not None:
            revisions[str(stamp)] = _fingerprint(revision)
    return EntryRecord(ref=ref, revisions=revisions)


def _groups(root: ET.Element | None) -> list[ET.Element]:
    if root is None:
        return []
    found: list[ET.Element] = []
    for group in root.iter("Group"):
        found.append(group)
    return found


def _group_path(group: ET.Element) -> str:
    names = []
    for ancestor in _ancestors(group):
        name = _text(ancestor.find("Name")) or "?"
        names.append(name)
    return "/".join(names) or "/"


def _ancestors(group: ET.Element) -> list[ET.Element]:
    # ElementTree has no parent links, so rebuild them from the document root.
    return list(group.iterancestors()) if hasattr(group, "iterancestors") else []


def _fingerprint(entry: ET.Element) -> str:
    clone = copy.deepcopy(entry)
    times = clone.find("Times")
    if times is not None:
        clone.remove(times)
    history = clone.find("History")
    if history is not None:
        clone.remove(history)
    return ET.tostring(clone, encoding="unicode")


def _stamp(entry: ET.Element) -> int | None:
    modified = _modified(entry)
    return int(modified.timestamp()) if modified else None


def _modified(entry: ET.Element) -> datetime | None:
    raw = _text(entry.find("Times/LastModificationTime"))
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _value(entry: ET.Element, key: str) -> str:
    for string in entry.findall("String"):
        if _text(string.find("Key")) == key:
            return _text(string.find("Value")) or ""
    return ""


def _text(element: ET.Element | None) -> str:
    if element is None or element.text is None:
        return ""
    return element.text.strip()
