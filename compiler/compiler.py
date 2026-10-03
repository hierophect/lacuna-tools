"""Compiler for Lacuna Deck Language 0.5.0 source files."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from .validation import (
        character_description,
        invalid_linguistic_characters,
        is_identifier,
        parse_side_tokens,
        validate_interchange,
    )
except ImportError:
    from validation import (
        character_description,
        invalid_linguistic_characters,
        is_identifier,
        parse_side_tokens,
        validate_interchange,
    )


@dataclass(frozen=True)
class Location:
    filename: str
    line: Optional[int] = None


@dataclass(frozen=True)
class Diagnostic:
    severity: str
    message: str
    location: Optional[Location] = None

    def format(self) -> str:
        prefix = ""
        if self.location:
            prefix = self.location.filename
            if self.location.line is not None:
                prefix += f":{self.location.line}"
            prefix += ": "
        return f"{prefix}{self.severity}: {self.message}"


@dataclass
class CategoryDeclaration:
    name: str
    variants: List[str]
    rows: List[Tuple[List[str], Location]]
    location: Location


@dataclass
class GroupDeclaration:
    fields: List[str]
    location: Location


@dataclass
class PairgroupDeclaration:
    name: str
    columns: List[str]
    rows: List[Tuple[List[str], Location]]
    location: Location


@dataclass
class VocabularyDeclaration:
    fields: List[str]
    location: Location


@dataclass
class TemplateDeclaration:
    sides: List[Tuple[str, Location]]
    location: Location


@dataclass
class ChapterDeclaration:
    name: str
    labels: List[str]
    vocabulary: List[VocabularyDeclaration]
    templates: List[TemplateDeclaration]
    location: Location


@dataclass
class ParsedFile:
    categories: List[CategoryDeclaration] = field(default_factory=list)
    groups: List[GroupDeclaration] = field(default_factory=list)
    pairgroups: List[PairgroupDeclaration] = field(default_factory=list)
    chapters: List[ChapterDeclaration] = field(default_factory=list)


@dataclass
class CompilationResult:
    document: Optional[Dict[str, Any]]
    diagnostics: List[Diagnostic]

    @property
    def has_errors(self) -> bool:
        return any(item.severity == "error" for item in self.diagnostics)


def _decode_csv_record(raw: str) -> List[str]:
    """Decode one strict, physical semicolon-delimited record."""
    index = 0
    while index < len(raw):
        at_field_start = index == 0 or raw[index - 1] == ";"
        if at_field_start and raw[index] == '"':
            index += 1
            while index < len(raw):
                if raw[index] == '"':
                    if index + 1 < len(raw) and raw[index + 1] == '"':
                        index += 2
                        continue
                    index += 1
                    if index < len(raw) and raw[index] != ";":
                        raise ValueError("characters follow a closing CSV quote")
                    break
                index += 1
            else:
                raise ValueError("unclosed CSV quote")
        else:
            while index < len(raw) and raw[index] != ";":
                if raw[index] == '"':
                    raise ValueError("a quote inside an unquoted field is invalid")
                index += 1
        if index < len(raw):
            index += 1
    try:
        return next(csv.reader([raw], delimiter=";", strict=True))
    except (csv.Error, StopIteration) as error:
        raise ValueError(f"invalid CSV record: {error}") from error


class SourceParser:
    SECTION_NAMES = {
        "# Selectables": "selectables",
        "# Groups": "groups",
        "# Pair Groups": "pairgroups",
        "# PairGroups": "pairgroups",
        "# Templates": "templates",
    }

    def __init__(self, filename: str, text: str, diagnostics: List[Diagnostic]):
        self.filename = filename
        self.text = text
        self.diagnostics = diagnostics
        self.result = ParsedFile()
        self.section: Optional[str] = None
        self.seen_sections: List[str] = []
        self.category: Optional[Dict[str, Any]] = None
        self.pairgroup: Optional[Dict[str, Any]] = None
        self.chapter: Optional[Dict[str, Any]] = None
        self.template: Optional[Dict[str, Any]] = None

    def error(self, message: str, line: Optional[int] = None) -> None:
        self.diagnostics.append(Diagnostic("error", message, Location(self.filename, line)))

    def _waiting_for_header(self) -> bool:
        return bool(
            (self.section == "selectables" and self.category and self.category["variants"] is None)
            or (self.section == "pairgroups" and self.pairgroup and self.pairgroup["columns"] is None)
            or (self.section == "templates" and self.chapter and self.chapter["labels"] is None)
        )

    def parse(self) -> ParsedFile:
        lines = self.text.split("\n")
        if self.text.endswith("\n"):
            lines.pop()
        for line_number, raw_line in enumerate(lines, 1):
            if raw_line.endswith("\r"):
                raw_line = raw_line[:-1]
            stripped = raw_line.lstrip(" \t")
            if not stripped:
                if self._waiting_for_header():
                    self.error("a declaration header record must immediately follow its header", line_number)
                continue
            if stripped.startswith("//"):
                if self._waiting_for_header():
                    self.error("a declaration header record must immediately follow its header", line_number)
                continue
            if stripped.startswith("<!--"):
                if self._waiting_for_header():
                    self.error("a declaration header record must immediately follow its header", line_number)
                if not stripped.endswith("-->"):
                    self.error("HTML-style comment is missing its closing '-->'", line_number)
                continue

            location = Location(self.filename, line_number)
            record_text = stripped if self.template is not None else raw_line
            try:
                fields = _decode_csv_record(record_text)
            except ValueError as error:
                self.error(str(error), line_number)
                continue

            if self.template is not None:
                self._parse_template_record(fields, location)
                continue
            if len(fields) == 1 and fields[0].startswith("# ") and not fields[0].startswith("## "):
                self._change_section(fields[0], location)
                continue
            if self.section is None:
                self.error("text appears outside a language section", line_number)
            elif self.section == "selectables":
                self._parse_selectables(fields, location)
            elif self.section == "groups":
                self._parse_groups(fields, location)
            elif self.section == "pairgroups":
                self._parse_pairgroups(fields, location)
            elif self.section == "templates":
                self._parse_templates(fields, location)

        if self.template is not None:
            self.error("Template block is not closed", self.template["location"].line)
            self.template = None
        self._finalize_section()
        display_names = {"selectables": "Selectables", "groups": "Groups", "templates": "Templates"}
        for required in ("selectables", "groups", "templates"):
            if required not in self.seen_sections:
                self.error(f"required '# {display_names[required]}' section is missing")
        return self.result

    def _change_section(self, header: str, location: Location) -> None:
        new_section = self.SECTION_NAMES.get(header)
        if new_section is None:
            self.error(f"unknown top-level header {header!r}", location.line)
            return
        if new_section in self.seen_sections:
            self.error(f"section {header!r} occurs more than once in this file", location.line)
        sequences = {
            ("selectables",),
            ("selectables", "groups"),
            ("selectables", "groups", "pairgroups"),
            ("selectables", "groups", "templates"),
            ("selectables", "groups", "pairgroups", "templates"),
        }
        sequence = tuple(self.seen_sections + [new_section])
        if sequence not in sequences:
            self.error(f"section {header!r} is missing, duplicated, or out of order", location.line)
        self._finalize_section()
        self.section = new_section
        if new_section not in self.seen_sections:
            self.seen_sections.append(new_section)

    def _finalize_section(self) -> None:
        if self.section == "selectables":
            self._finalize_category()
        elif self.section == "pairgroups":
            self._finalize_pairgroup()
            if not self.result.pairgroups:
                self.error("a Pair Groups section must contain at least one Pairgroup")
        elif self.section == "templates":
            self._finalize_chapter()

    def _finalize_category(self) -> None:
        if self.category is None:
            return
        location = self.category["location"]
        if self.category["variants"] is None:
            self.error("Category is missing its Variant header record", location.line)
        elif not self.category["rows"]:
            self.error("Category must contain at least one Selectable", location.line)
        else:
            self.result.categories.append(
                CategoryDeclaration(
                    self.category["name"], self.category["variants"], self.category["rows"], location
                )
            )
        self.category = None

    def _parse_selectables(self, fields: List[str], location: Location) -> None:
        if len(fields) == 1 and fields[0].startswith("## "):
            self._finalize_category()
            self.category = {
                "name": fields[0][3:],
                "variants": None,
                "rows": [],
                "location": location,
            }
            return
        if self.category is None:
            self.error("Selectable record appears outside a Category", location.line)
            return
        if self.category["variants"] is None:
            if not fields or not fields[0].startswith(">"):
                self.error("Category Variant header must begin with '>'", location.line)
                return
            fields[0] = fields[0][1:]
            self.category["variants"] = fields
            return
        self.category["rows"].append((fields, location))

    def _parse_groups(self, fields: List[str], location: Location) -> None:
        if len(fields) == 1 and fields[0].startswith("## "):
            self.error("subheaders are not valid in the Groups section", location.line)
            return
        self.result.groups.append(GroupDeclaration(fields, location))

    def _finalize_pairgroup(self) -> None:
        if self.pairgroup is None:
            return
        location = self.pairgroup["location"]
        if self.pairgroup["columns"] is None:
            self.error("Pairgroup is missing its column header record", location.line)
        elif not self.pairgroup["rows"]:
            self.error("Pairgroup must contain at least one row", location.line)
        else:
            self.result.pairgroups.append(
                PairgroupDeclaration(
                    self.pairgroup["name"],
                    self.pairgroup["columns"],
                    self.pairgroup["rows"],
                    location,
                )
            )
        self.pairgroup = None

    def _parse_pairgroups(self, fields: List[str], location: Location) -> None:
        if len(fields) == 1 and fields[0].startswith("## "):
            self._finalize_pairgroup()
            self.pairgroup = {
                "name": fields[0][3:],
                "columns": None,
                "rows": [],
                "location": location,
            }
            return
        if self.pairgroup is None:
            self.error("Pairgroup row appears outside a Pairgroup", location.line)
            return
        if self.pairgroup["columns"] is None:
            if not fields or not fields[0].startswith(">"):
                self.error("Pairgroup column header must begin with '>'", location.line)
                return
            fields[0] = fields[0][1:]
            self.pairgroup["columns"] = fields
            return
        self.pairgroup["rows"].append((fields, location))

    def _finalize_chapter(self) -> None:
        if self.chapter is None:
            return
        location = self.chapter["location"]
        if self.chapter["labels"] is None:
            self.error("Chapter is missing its Side-label header record", location.line)
        elif not self.chapter["templates"]:
            self.error("Chapter must contain at least one Template", location.line)
        else:
            self.result.chapters.append(
                ChapterDeclaration(
                    self.chapter["name"],
                    self.chapter["labels"],
                    self.chapter["vocabulary"],
                    self.chapter["templates"],
                    location,
                )
            )
        self.chapter = None

    def _parse_templates(self, fields: List[str], location: Location) -> None:
        if len(fields) == 1 and fields[0].startswith("## "):
            self._finalize_chapter()
            self.chapter = {
                "name": fields[0][3:],
                "labels": None,
                "vocabulary": [],
                "templates": [],
                "location": location,
            }
            return
        if self.chapter is None:
            self.error("Template content appears outside a Chapter", location.line)
            return
        if self.chapter["labels"] is None:
            if not fields or not fields[0].startswith(">"):
                self.error("Chapter Side-label header must begin with '>'", location.line)
                return
            fields[0] = fields[0][1:]
            self.chapter["labels"] = fields
            return
        if fields and fields[0] == ">vocab":
            if self.chapter["templates"]:
                self.error("vocabulary declarations must precede all Templates in a Chapter", location.line)
            self.chapter["vocabulary"].append(VocabularyDeclaration(fields, location))
            return
        if fields == ["{"]:
            self.template = {"sides": [], "location": location}
            return
        if fields == ["}"]:
            self.error("Template closing brace has no matching opening brace", location.line)
            return
        self.error("text appears outside a Template block", location.line)

    def _parse_template_record(self, fields: List[str], location: Location) -> None:
        if fields == ["}"]:
            if not self.template["sides"]:
                self.error("Template block must contain at least one Side", location.line)
            elif self.chapter is not None:
                self.chapter["templates"].append(
                    TemplateDeclaration(self.template["sides"], self.template["location"])
                )
            self.template = None
            return
        if fields == ["{"]:
            self.error("Template blocks cannot be nested", location.line)
            return
        if len(fields) != 1:
            self.error("a Template Side must decode to exactly one field", location.line)
            return
        self.template["sides"].append((fields[0], location))


def _read_source(path: Path, diagnostics: List[Diagnostic]) -> Optional[str]:
    filename = str(path)
    try:
        raw = path.read_bytes()
    except OSError as error:
        diagnostics.append(Diagnostic("error", f"cannot read source file: {error}", Location(filename)))
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        diagnostics.append(
            Diagnostic("error", "UTF-8 byte-order marks are not permitted", Location(filename, 1))
        )
        return None
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        line = raw[: error.start].count(b"\n") + 1
        diagnostics.append(
            Diagnostic("error", f"source is not valid UTF-8: {error.reason}", Location(filename, line))
        )
        return None
    position = text.find("\r")
    while position != -1:
        if position + 1 >= len(text) or text[position + 1] != "\n":
            line = text[:position].count("\n") + 1
            diagnostics.append(
                Diagnostic("error", "bare carriage return is not a valid line ending", Location(filename, line))
            )
            return None
        position = text.find("\r", position + 2)
    if text and not text.endswith("\n"):
        diagnostics.append(
            Diagnostic(
                "warning",
                "final physical record has no line ending",
                Location(filename, text.count("\n") + 1),
            )
        )
    return text


def _parse_member_list(
    value: str, diagnostics: List[Diagnostic], location: Location
) -> List[str]:
    if len(value) < 3 or not value.startswith("{") or not value.endswith("}"):
        diagnostics.append(Diagnostic("error", "member list must use nonempty {...} syntax", location))
        return []
    members = value[1:-1].split(",")
    if any(not member for member in members):
        diagnostics.append(Diagnostic("error", "member list contains an empty member", location))
        return []
    for member in members:
        if "{" in member or "}" in member:
            diagnostics.append(Diagnostic("error", "member list has malformed braces", location))
            return []
        for character in invalid_linguistic_characters(member):
            diagnostics.append(
                Diagnostic(
                    "error",
                    f"member key contains forbidden character {character_description(character)}",
                    location,
                )
            )
    return members


class DeckCompiler:
    def __init__(self, parsed_files: Sequence[ParsedFile], diagnostics: List[Diagnostic]):
        self.files = parsed_files
        self.diagnostics = diagnostics
        self.categories: List[Dict[str, Any]] = []
        self.groups: List[Dict[str, Any]] = []
        self.pairgroups: List[Dict[str, Any]] = []
        self.chapters: List[Dict[str, Any]] = []
        self.category_by_name: Dict[str, Dict[str, Any]] = {}
        self.group_by_name: Dict[str, Dict[str, Any]] = {}
        self.pairgroup_by_name: Dict[str, Dict[str, Any]] = {}

    def error(self, message: str, location: Location) -> None:
        self.diagnostics.append(Diagnostic("error", message, location))

    def warning(self, message: str, location: Location) -> None:
        self.diagnostics.append(Diagnostic("warning", message, location))

    def compile(self) -> Dict[str, Any]:
        self._compile_categories()
        self._compile_groups()
        self._compile_pairgroups()
        self._compile_chapters()
        return {
            "categories": self.categories,
            "groups": self.groups,
            "pair_groups": self.pairgroups,
            "chapters": self.chapters,
        }

    def _validate_identifier(self, value: str, kind: str, location: Location) -> bool:
        if is_identifier(value):
            return True
        self.error(f"{kind} {value!r} is not a valid structural name", location)
        return False

    def _validate_content(self, value: str, kind: str, location: Location) -> bool:
        if not value:
            self.error(f"{kind} must not be empty", location)
            return False
        valid = True
        for character in invalid_linguistic_characters(value):
            advice = ""
            if character == "&":
                advice = "; spell out 'and'"
            elif character == "+":
                advice = "; spell out 'plus'"
            self.error(
                f"{kind} contains forbidden character {character_description(character)}{advice}",
                location,
            )
            valid = False
        return valid

    def _compile_categories(self) -> None:
        for parsed_file in self.files:
            for declaration in parsed_file.categories:
                name_valid = self._validate_identifier(
                    declaration.name, "Category name", declaration.location
                )
                variants_valid = bool(declaration.variants)
                if not declaration.variants:
                    self.error("Category must declare at least one Variant", declaration.location)
                for variant in declaration.variants:
                    variants_valid &= self._validate_identifier(
                        variant, "Variant label", declaration.location
                    )
                if len(set(declaration.variants)) != len(declaration.variants):
                    self.error("Category Variant labels must be unique", declaration.location)
                    variants_valid = False
                existing = self.category_by_name.get(declaration.name)
                if existing is not None and existing["variant_names"] != declaration.variants:
                    self.error(
                        f"Category {declaration.name!r} is reopened with a different ordered Variant schema",
                        declaration.location,
                    )
                    continue
                if not name_valid or not variants_valid:
                    continue
                if existing is None:
                    existing = {
                        "name": declaration.name,
                        "variant_names": list(declaration.variants),
                        "num_variants": len(declaration.variants),
                        "selectables": [],
                    }
                    self.category_by_name[declaration.name] = existing
                    self.categories.append(existing)
                for row, location in declaration.rows:
                    if len(row) != len(declaration.variants):
                        self.error(
                            f"Selectable has {len(row)} fields; expected {len(declaration.variants)}",
                            location,
                        )
                        continue
                    row_valid = True
                    for value in row:
                        row_valid &= self._validate_content(
                            value, "Selectable Variant value", location
                        )
                        if value.endswith(" "):
                            self.warning(
                                "trailing ASCII spaces in a Selectable Variant value are significant",
                                location,
                            )
                    if not row_valid:
                        continue
                    selectable = {"variants": list(row)}
                    if selectable in existing["selectables"]:
                        self.warning(
                            f"exact duplicate Selectable in Category {declaration.name!r} was omitted",
                            location,
                        )
                    else:
                        existing["selectables"].append(selectable)

    def _lookup(
        self,
        category_name: str,
        variant_name: str,
        value: str,
        location: Location,
        purpose: str,
    ) -> Optional[Tuple[int, int]]:
        category = self.category_by_name.get(category_name)
        if category is None:
            self.error(f"unknown Category {category_name!r} used by {purpose}", location)
            return None
        if variant_name not in category["variant_names"]:
            self.error(
                f"unknown Variant {variant_name!r} in Category {category_name!r} used by {purpose}",
                location,
            )
            return None
        variant_index = category["variant_names"].index(variant_name)
        matches = [
            selectable_index
            for selectable_index, selectable in enumerate(category["selectables"])
            if selectable["variants"][variant_index] == value
        ]
        if not matches:
            self.error(
                f"no Selectable matches {value!r} through {category_name!r}.{variant_name}",
                location,
            )
            return None
        if len(matches) > 1:
            self.warning(
                f"ambiguous lookup for {value!r} through {category_name!r}.{variant_name}; "
                "using the first Selectable in compilation order",
                location,
            )
        return self.categories.index(category), matches[0]

    def _compile_groups(self) -> None:
        for parsed_file in self.files:
            for declaration in parsed_file.groups:
                if len(declaration.fields) != 4:
                    self.error("Group record must contain exactly four fields", declaration.location)
                    continue
                name, category_name, key_variant, member_text = declaration.fields
                identifiers_valid = all(
                    (
                        self._validate_identifier(name, "Group name", declaration.location),
                        self._validate_identifier(category_name, "Category name", declaration.location),
                        self._validate_identifier(key_variant, "Variant label", declaration.location),
                    )
                )
                members = _parse_member_list(member_text, self.diagnostics, declaration.location)
                if not identifiers_valid or not members:
                    continue
                category = self.category_by_name.get(category_name)
                if category is None:
                    self.error(
                        f"Group {name!r} uses unknown Category {category_name!r}",
                        declaration.location,
                    )
                    continue
                if key_variant not in category["variant_names"]:
                    self.error(
                        f"Group {name!r} uses unknown Variant {key_variant!r} "
                        f"in Category {category_name!r}",
                        declaration.location,
                    )
                    continue
                existing = self.group_by_name.get(name)
                if existing is not None and (
                    existing["category_name"] != category_name
                    or existing["key_variant_name"] != key_variant
                ):
                    self.error(
                        f"Group {name!r} is reopened with a different Category or key Variant",
                        declaration.location,
                    )
                    continue
                if existing is None:
                    existing = {
                        "name": name,
                        "category_name": category_name,
                        "key_variant_name": key_variant,
                        "keys": [],
                    }
                    self.group_by_name[name] = existing
                    self.groups.append(existing)
                for member in members:
                    resolved = self._lookup(
                        category_name, key_variant, member, declaration.location, f"Group {name!r}"
                    )
                    if resolved is None:
                        continue
                    if member in existing["keys"]:
                        self.warning(
                            f"redundant member {member!r} in Group {name!r} was omitted",
                            declaration.location,
                        )
                    else:
                        existing["keys"].append(member)

    def _compile_pairgroups(self) -> None:
        for parsed_file in self.files:
            for declaration in parsed_file.pairgroups:
                if not self._validate_identifier(
                    declaration.name, "Pairgroup name", declaration.location
                ):
                    continue
                if declaration.name in self.pairgroup_by_name:
                    self.error(
                        f"Pairgroup {declaration.name!r} cannot be reopened",
                        declaration.location,
                    )
                    continue
                aliases: List[str] = []
                types: List[str] = []
                columns_valid = True
                if len(declaration.columns) < 2:
                    self.error("Pairgroup must declare at least two columns", declaration.location)
                    columns_valid = False
                for column in declaration.columns:
                    if column.count("=") != 1:
                        self.error(f"malformed Pairgroup column {column!r}", declaration.location)
                        columns_valid = False
                        continue
                    alias, column_type = column.split("=", 1)
                    columns_valid &= self._validate_identifier(
                        alias, "Pairgroup alias", declaration.location
                    )
                    type_parts = column_type.split(":")
                    if type_parts == ["group"]:
                        pass
                    elif len(type_parts) == 3 and type_parts[0] == "selectable":
                        columns_valid &= self._validate_identifier(
                            type_parts[1], "Category name", declaration.location
                        )
                        columns_valid &= self._validate_identifier(
                            type_parts[2], "Variant label", declaration.location
                        )
                    else:
                        self.error(
                            f"malformed Pairgroup column type {column_type!r}",
                            declaration.location,
                        )
                        columns_valid = False
                    aliases.append(alias)
                    types.append(column_type)
                if len(set(aliases)) != len(aliases):
                    self.error("Pairgroup aliases must be unique", declaration.location)
                    columns_valid = False
                if not columns_valid:
                    continue
                category_checking: List[Optional[str]] = [None] * len(aliases)
                valid_rows: List[List[str]] = []
                for row, location in declaration.rows:
                    if len(row) != len(aliases):
                        self.error(
                            f"Pairgroup row has {len(row)} fields; expected {len(aliases)}",
                            location,
                        )
                        continue
                    row_valid = True
                    for column_index, member in enumerate(row):
                        if not member:
                            self.error("Pairgroup row values must not be empty", location)
                            row_valid = False
                            continue
                        column_type = types[column_index]
                        if column_type == "group":
                            group = self.group_by_name.get(member)
                            if group is None:
                                self.error(f"Pairgroup row uses unknown Group {member!r}", location)
                                row_valid = False
                            elif category_checking[column_index] is None:
                                category_checking[column_index] = group["category_name"]
                            elif category_checking[column_index] != group["category_name"]:
                                self.error(
                                    f"Pairgroup column {aliases[column_index]!r} uses Groups "
                                    "from multiple Categories",
                                    location,
                                )
                                row_valid = False
                        else:
                            _, category_name, variant_name = column_type.split(":")
                            if self._lookup(
                                category_name,
                                variant_name,
                                member,
                                location,
                                f"Pairgroup {declaration.name!r}",
                            ) is None:
                                row_valid = False
                    if row_valid:
                        valid_rows.append(list(row))
                if not valid_rows:
                    self.error(
                        f"Pairgroup {declaration.name!r} has no valid rows", declaration.location
                    )
                    continue
                pairgroup = {
                    "name": declaration.name,
                    "column_names": aliases,
                    "column_types": types,
                    "category_checking": category_checking,
                    "pairs": valid_rows,
                    "valid": True,
                }
                self.pairgroup_by_name[declaration.name] = pairgroup
                self.pairgroups.append(pairgroup)

    def _compile_labels(
        self, labels: List[str], location: Location
    ) -> Optional[Tuple[List[str], List[int], int]]:
        if not labels:
            self.error("Chapter must declare at least one Side label", location)
            return None
        normalized: List[str] = []
        forced_indices = []
        valid = True
        for index, label in enumerate(labels):
            if label.startswith("^~") or label.startswith("~^"):
                self.error(f"Side label {label!r} combines '^' and '~'", location)
                valid = False
                bare = label[2:]
                supplementary = True
            else:
                modifier = label[:1] if label[:1] in {"^", "~"} else ""
                bare = label[1:] if modifier else label
                supplementary = modifier == "~"
                if modifier == "^":
                    forced_indices.append(index)
            if not self._validate_identifier(bare, "Side label", location):
                valid = False
            normalized.append(("~" if supplementary else "") + bare)
        if len(forced_indices) > 1:
            self.error("at most one Side label may use '^'", location)
            valid = False
        bare_labels = [label.lstrip("~") for label in normalized]
        if len(set(bare_labels)) != len(bare_labels):
            self.error("Side labels must be unique after removing modifiers", location)
            valid = False
        if all(label.startswith("~") for label in normalized):
            self.error("a Chapter must have at least one non-supplementary Side", location)
            valid = False
        forced_index = forced_indices[0] if forced_indices else 0
        if not forced_indices and normalized[0].startswith("~"):
            self.error("the first Side cannot be supplementary when no Side uses '^'", location)
            valid = False
        order = [forced_index] + [index for index in range(len(labels)) if index != forced_index]
        reordered = [normalized[index] for index in order]
        return (reordered, order, forced_index) if valid else None

    def _pairgroup_category(
        self, pairgroup: Dict[str, Any], alias: str
    ) -> Optional[Dict[str, Any]]:
        index = pairgroup["column_names"].index(alias)
        column_type = pairgroup["column_types"][index]
        category_name = (
            pairgroup["category_checking"][index]
            if column_type == "group"
            else column_type.split(":")[1]
        )
        return self.category_by_name.get(category_name)

    def _compile_template(
        self,
        declaration: TemplateDeclaration,
        labels: List[str],
        order: List[int],
    ) -> Optional[Dict[str, Any]]:
        if len(declaration.sides) != len(labels):
            self.error(
                f"Template has {len(declaration.sides)} Sides; expected {len(labels)}",
                declaration.location,
            )
            return None
        reordered_sides = [declaration.sides[index] for index in order]
        output_sides: List[str] = []
        selections_by_side = []
        used_pairgroups = set()
        valid = True
        for side_index, (side_text, location) in enumerate(reordered_sides):
            if not side_text:
                self.error("Template Side must not be empty", location)
                valid = False
            if side_text.endswith(" "):
                self.warning(
                    "trailing ASCII spaces in a Template Side are significant", location
                )
            tokens, token_errors = parse_side_tokens(side_text)
            for error in token_errors:
                self.error(error, location)
                valid = False
            default_variant = labels[side_index].lstrip("~")
            selections = set()
            for kind, parts in tokens:
                if kind == "group":
                    name = parts[0]
                    selection = ("group", name)
                    group = self.group_by_name.get(name)
                    if group is None:
                        self.error(f"unknown Group {name!r} in Template Side", location)
                        valid = False
                    else:
                        variant = parts[1] if len(parts) == 2 else default_variant
                        category = self.category_by_name[group["category_name"]]
                        if variant not in category["variant_names"]:
                            self.error(
                                f"unknown Variant {variant!r} for Group {name!r}", location
                            )
                            valid = False
                else:
                    pairgroup_name, alias = parts[:2]
                    selection = ("pairgroup", pairgroup_name, alias)
                    used_pairgroups.add(pairgroup_name)
                    pairgroup = self.pairgroup_by_name.get(pairgroup_name)
                    if pairgroup is None:
                        self.error(
                            f"unknown Pairgroup {pairgroup_name!r} in Template Side", location
                        )
                        valid = False
                    elif alias not in pairgroup["column_names"]:
                        self.error(
                            f"unknown alias {alias!r} in Pairgroup {pairgroup_name!r}", location
                        )
                        valid = False
                    else:
                        category = self._pairgroup_category(pairgroup, alias)
                        variant = parts[2] if len(parts) == 3 else default_variant
                        if category is None or variant not in category["variant_names"]:
                            self.error(
                                f"unknown Variant {variant!r} for Pairgroup alias {alias!r}",
                                location,
                            )
                            valid = False
                if selection in selections:
                    self.error(
                        f"selection {selection[1:]!r} occurs more than once on one Side",
                        location,
                    )
                    valid = False
                selections.add(selection)
            selections_by_side.append(selections)
            output_sides.append(side_text)
        if len(used_pairgroups) > 1:
            self.error("a Template may reference only one distinct Pairgroup", declaration.location)
            valid = False
        if selections_by_side:
            for side_index, selections in enumerate(selections_by_side[1:], 1):
                for selection in selections - selections_by_side[0]:
                    self.error(
                        f"selection {selection[1:]!r} on Side {side_index} "
                        "is absent from compiled Side zero",
                        reordered_sides[side_index][1],
                    )
                    valid = False
        return {"sides": output_sides} if valid else None

    def _compile_chapters(self) -> None:
        seen_chapters = set()
        introduced = set()
        for parsed_file in self.files:
            for declaration in parsed_file.chapters:
                chapter_valid = True
                if declaration.name != declaration.name.strip() or not declaration.name:
                    self.error("Chapter name must be trimmed and nonempty", declaration.location)
                    chapter_valid = False
                for character in invalid_linguistic_characters(
                    declaration.name, allow_underscore=True
                ):
                    self.error(
                        f"Chapter name contains forbidden character {character_description(character)}",
                        declaration.location,
                    )
                    chapter_valid = False
                if declaration.name in seen_chapters:
                    self.error(f"duplicate Chapter name {declaration.name!r}", declaration.location)
                    chapter_valid = False
                seen_chapters.add(declaration.name)
                compiled_labels = self._compile_labels(declaration.labels, declaration.location)
                if compiled_labels is None:
                    continue
                labels, order, forced_index = compiled_labels
                templates = []
                for template in declaration.templates:
                    compiled = self._compile_template(template, labels, order)
                    if compiled is None:
                        chapter_valid = False
                    else:
                        templates.append(compiled)
                vocab_output = []
                for vocabulary in declaration.vocabulary:
                    if len(vocabulary.fields) != 4:
                        self.error(
                            "vocabulary declaration must contain exactly four fields",
                            vocabulary.location,
                        )
                        chapter_valid = False
                        continue
                    _, category_name, key_variant, member_text = vocabulary.fields
                    names_valid = self._validate_identifier(
                        category_name, "Category name", vocabulary.location
                    )
                    names_valid &= self._validate_identifier(
                        key_variant, "Variant label", vocabulary.location
                    )
                    keys = _parse_member_list(
                        member_text, self.diagnostics, vocabulary.location
                    )
                    if not names_valid or not keys:
                        chapter_valid = False
                        continue
                    retained = []
                    local_identities = set()
                    for key in keys:
                        identity = self._lookup(
                            category_name, key_variant, key, vocabulary.location, "vocabulary"
                        )
                        if identity is None:
                            chapter_valid = False
                            continue
                        if identity in introduced or identity in local_identities:
                            self.warning(
                                f"repeated vocabulary declaration for {key!r} was omitted",
                                vocabulary.location,
                            )
                            continue
                        local_identities.add(identity)
                        introduced.add(identity)
                        retained.append(key)
                    if retained:
                        vocab_output.append(
                            {
                                "name": "vocab",
                                "category_name": category_name,
                                "key_variant_name": key_variant,
                                "keys": retained,
                            }
                        )
                if chapter_valid:
                    self.chapters.append(
                        {
                            "name": declaration.name,
                            "column_variants": labels,
                            "forced_first_side": forced_index,
                            "templates": templates,
                            "vocab": vocab_output,
                        }
                    )


def compile_paths(paths: Sequence[Path]) -> CompilationResult:
    diagnostics: List[Diagnostic] = []
    parsed_files = []
    for path in paths:
        source = _read_source(path, diagnostics)
        if source is not None:
            parsed_files.append(SourceParser(str(path), source, diagnostics).parse())
    if any(item.severity == "error" for item in diagnostics):
        return CompilationResult(None, diagnostics)
    document = DeckCompiler(parsed_files, diagnostics).compile()
    if any(item.severity == "error" for item in diagnostics):
        return CompilationResult(None, diagnostics)
    for message in validate_interchange(document):
        diagnostics.append(
            Diagnostic("error", f"compiled interchange validation failed: {message}")
        )
    if any(item.severity == "error" for item in diagnostics):
        return CompilationResult(None, diagnostics)
    return CompilationResult(document, diagnostics)
