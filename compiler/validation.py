"""Validation helpers for Lacuna Deck Language 0.5.0 interchange data."""

from __future__ import annotations

import json
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


SCHEMA_PATH = Path(__file__).parent / "syntax" / "0.5.0" / "interchange.schema.json"
IDENTIFIER_CHARS = frozenset("_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789")
LITERAL_PUNCTUATION = frozenset(".,;:?!-()\"'。 、？！".replace(" ", ""))
RESERVED_CHARACTERS = frozenset("[]<>{}#=^~")


def is_identifier(value: str) -> bool:
    if not value or value[0] not in "_ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
        return False
    return all(character in IDENTIFIER_CHARS for character in value[1:])


def invalid_linguistic_characters(value: str, allow_underscore: bool = False) -> List[str]:
    invalid = []
    for character in value:
        category = unicodedata.category(character)
        if category[0] in {"L", "M", "N"}:
            continue
        if character == " " or character in LITERAL_PUNCTUATION:
            continue
        if allow_underscore and character == "_":
            continue
        invalid.append(character)
    return invalid


def character_description(character: str) -> str:
    try:
        name = unicodedata.name(character)
    except ValueError:
        name = "unnamed character"
    return f"{character!r} (U+{ord(character):04X}, {name})"


def parse_side_tokens(text: str) -> Tuple[List[Tuple[str, Tuple[str, ...]]], List[str]]:
    """Return replacement tokens and lexical/content errors for one compiled Side."""
    tokens: List[Tuple[str, Tuple[str, ...]]] = []
    errors: List[str] = []
    literal: List[str] = []

    def finish_literal() -> None:
        if not literal:
            return
        value = "".join(literal)
        bad = invalid_linguistic_characters(value)
        for character in bad:
            advice = ""
            if character == "&":
                advice = "; spell out 'and'"
            elif character == "+":
                advice = "; spell out 'plus'"
            errors.append(f"forbidden literal character {character_description(character)}{advice}")
        literal.clear()

    index = 0
    while index < len(text):
        character = text[index]
        if character in "[<":
            finish_literal()
            closer = "]" if character == "[" else ">"
            end = text.find(closer, index + 1)
            if end == -1:
                errors.append(f"unclosed replacement beginning with {character!r}")
                break
            body = text[index + 1 : end]
            if any(marker in body for marker in "[]<>"):
                errors.append(f"nested or mismatched replacement {text[index:end + 1]!r}")
            else:
                parts = tuple(body.split(":"))
                kind = "group" if character == "[" else "pairgroup"
                required = (1, 2) if kind == "group" else (2, 3)
                if len(parts) not in required or any(not is_identifier(part) for part in parts):
                    errors.append(f"malformed {kind} replacement {text[index:end + 1]!r}")
                else:
                    tokens.append((kind, parts))
            index = end + 1
            continue
        if character in "]>":
            finish_literal()
            errors.append(f"unmatched replacement delimiter {character!r}")
        elif character in RESERVED_CHARACTERS:
            finish_literal()
            errors.append(f"reserved character {character!r} is not valid literal text")
        else:
            literal.append(character)
        index += 1
    finish_literal()
    return tokens, errors


@lru_cache(maxsize=1)
def load_schema() -> Dict[str, Any]:
    with SCHEMA_PATH.open(encoding="utf-8") as schema_file:
        return json.load(schema_file)


def _path(parts: Iterable[Any]) -> str:
    result = "$"
    for part in parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += f".{part}"
    return result


def _schema_errors(document: Any) -> List[str]:
    try:
        from jsonschema import Draft202012Validator
    except ImportError:
        return ["jsonschema is required to validate Lacuna Deck Language output"]

    validator = Draft202012Validator(load_schema())
    return [
        f"{_path(error.absolute_path)}: {error.message}"
        for error in sorted(
            validator.iter_errors(document),
            key=lambda error: tuple(str(part) for part in error.absolute_path),
        )
    ]


def validate_interchange(document: Any) -> List[str]:
    """Return all structural and semantic 0.5.0 validation errors found."""
    errors = _schema_errors(document)
    if not isinstance(document, dict):
        return errors
    required_arrays = ("categories", "groups", "pair_groups", "chapters")
    if not all(isinstance(document.get(name), list) for name in required_arrays):
        return errors

    categories = document["categories"]
    groups = document["groups"]
    pairgroups = document["pair_groups"]
    chapters = document["chapters"]

    category_by_name: Dict[str, Dict[str, Any]] = {}
    category_positions: Dict[str, int] = {}
    for category_index, category in enumerate(categories):
        path = f"$.categories[{category_index}]"
        if not isinstance(category, dict):
            continue
        name = category.get("name")
        if isinstance(name, str):
            if name in category_by_name:
                errors.append(f"{path}.name: duplicate Category name {name!r}")
            else:
                category_by_name[name] = category
                category_positions[name] = category_index
        variants = category.get("variant_names")
        selectables = category.get("selectables")
        if isinstance(variants, list):
            if category.get("num_variants") != len(variants):
                errors.append(f"{path}.num_variants: does not match variant_names length")
        if isinstance(variants, list) and isinstance(selectables, list):
            for selectable_index, selectable in enumerate(selectables):
                selectable_path = f"{path}.selectables[{selectable_index}]"
                values = selectable.get("variants") if isinstance(selectable, dict) else None
                if isinstance(values, list) and len(values) != len(variants):
                    errors.append(f"{selectable_path}.variants: does not match variant_names length")
                if isinstance(values, list):
                    for value_index, value in enumerate(values):
                        if isinstance(value, str):
                            for character in invalid_linguistic_characters(value):
                                errors.append(
                                    f"{selectable_path}.variants[{value_index}]: forbidden linguistic "
                                    f"character {character_description(character)}"
                                )

    def matches(category_name: Any, variant_name: Any, value: Any) -> List[Tuple[int, int]]:
        category = category_by_name.get(category_name) if isinstance(category_name, str) else None
        if not category:
            return []
        variants = category.get("variant_names")
        selectables = category.get("selectables")
        if not isinstance(variants, list) or variant_name not in variants or not isinstance(selectables, list):
            return []
        variant_index = variants.index(variant_name)
        found = []
        for selectable_index, selectable in enumerate(selectables):
            values = selectable.get("variants") if isinstance(selectable, dict) else None
            if isinstance(values, list) and variant_index < len(values) and values[variant_index] == value:
                found.append((category_positions[category_name], selectable_index))
        return found

    group_by_name: Dict[str, Dict[str, Any]] = {}
    for group_index, group in enumerate(groups):
        path = f"$.groups[{group_index}]"
        if not isinstance(group, dict):
            continue
        name = group.get("name")
        if isinstance(name, str):
            if name in group_by_name:
                errors.append(f"{path}.name: duplicate Group name {name!r}")
            else:
                group_by_name[name] = group
        category_name = group.get("category_name")
        key_variant = group.get("key_variant_name")
        category = category_by_name.get(category_name) if isinstance(category_name, str) else None
        if category is None:
            errors.append(f"{path}.category_name: unknown Category {category_name!r}")
        elif not isinstance(category.get("variant_names"), list) or key_variant not in category[
            "variant_names"
        ]:
            errors.append(f"{path}.key_variant_name: unknown Variant {key_variant!r}")
        keys = group.get("keys")
        category_variants = category.get("variant_names") if category is not None else None
        if (
            isinstance(keys, list)
            and isinstance(category_variants, list)
            and key_variant in category_variants
        ):
            for key_index, key in enumerate(keys):
                if isinstance(key, str):
                    if "," in key or "{" in key or "}" in key:
                        errors.append(
                            f"{path}.keys[{key_index}]: Group keys cannot contain commas or braces"
                        )
                    for character in invalid_linguistic_characters(key):
                        errors.append(
                            f"{path}.keys[{key_index}]: forbidden lookup character "
                            f"{character_description(character)}"
                        )
                if not matches(category_name, key_variant, key):
                    errors.append(f"{path}.keys[{key_index}]: unresolved Selectable {key!r}")

    pairgroup_by_name: Dict[str, Dict[str, Any]] = {}
    pairgroup_categories: Dict[Tuple[str, str], Optional[str]] = {}
    for pairgroup_index, pairgroup in enumerate(pairgroups):
        path = f"$.pair_groups[{pairgroup_index}]"
        if not isinstance(pairgroup, dict):
            continue
        name = pairgroup.get("name")
        aliases = pairgroup.get("column_names")
        types = pairgroup.get("column_types")
        checking = pairgroup.get("category_checking")
        rows = pairgroup.get("pairs")
        if not all(isinstance(value, list) for value in (aliases, types, checking, rows)):
            continue
        if isinstance(name, str):
            if name in pairgroup_by_name:
                errors.append(f"{path}.name: duplicate Pairgroup name {name!r}")
            else:
                pairgroup_by_name[name] = pairgroup
        if len(types) != len(aliases):
            errors.append(f"{path}.column_types: length does not match column_names")
        if len(checking) != len(aliases):
            errors.append(f"{path}.category_checking: length does not match column_names")
        for row_index, row in enumerate(rows):
            if isinstance(row, list) and len(row) != len(aliases):
                errors.append(f"{path}.pairs[{row_index}]: length does not match column_names")
        for column_index, alias in enumerate(aliases):
            if column_index >= len(types):
                continue
            column_type = types[column_index]
            resolved_category: Optional[str] = None
            if column_type == "group":
                categories_used = set()
                for row_index, row in enumerate(rows):
                    if not isinstance(row, list) or column_index >= len(row):
                        continue
                    if not isinstance(row[column_index], str) or not is_identifier(
                        row[column_index]
                    ):
                        errors.append(
                            f"{path}.pairs[{row_index}][{column_index}]: "
                            "Group-valued cells must be structural names"
                        )
                    cell = row[column_index]
                    group = group_by_name.get(cell) if isinstance(cell, str) else None
                    if group is None:
                        errors.append(
                            f"{path}.pairs[{row_index}][{column_index}]: unknown Group {row[column_index]!r}"
                        )
                    else:
                        group_category = group.get("category_name")
                        if isinstance(group_category, str):
                            categories_used.add(group_category)
                if len(categories_used) > 1:
                    errors.append(f"{path}: Group-valued column {alias!r} uses multiple Categories")
                if len(categories_used) == 1:
                    resolved_category = next(iter(categories_used))
            elif isinstance(column_type, str) and column_type.startswith("selectable:"):
                parts = column_type.split(":")
                if len(parts) == 3:
                    resolved_category = parts[1]
                    category = category_by_name.get(parts[1])
                    if category is None:
                        errors.append(f"{path}.column_types[{column_index}]: unknown Category {parts[1]!r}")
                    elif not isinstance(category.get("variant_names"), list) or parts[
                        2
                    ] not in category["variant_names"]:
                        errors.append(f"{path}.column_types[{column_index}]: unknown Variant {parts[2]!r}")
                    else:
                        for row_index, row in enumerate(rows):
                            if isinstance(row, list) and column_index < len(row):
                                value = row[column_index]
                                if isinstance(value, str):
                                    if "," in value or "{" in value or "}" in value:
                                        errors.append(
                                            f"{path}.pairs[{row_index}][{column_index}]: "
                                            "Selectable lookup values cannot contain commas or braces"
                                        )
                                    for character in invalid_linguistic_characters(value):
                                        errors.append(
                                            f"{path}.pairs[{row_index}][{column_index}]: "
                                            f"forbidden lookup character {character_description(character)}"
                                        )
                                if not matches(parts[1], parts[2], row[column_index]):
                                    errors.append(
                                        f"{path}.pairs[{row_index}][{column_index}]: unresolved Selectable "
                                        f"{row[column_index]!r}"
                                    )
            expected_check = resolved_category if column_type == "group" else None
            if column_index < len(checking) and checking[column_index] != expected_check:
                errors.append(
                    f"{path}.category_checking[{column_index}]: expected {expected_check!r}"
                )
            if isinstance(name, str) and isinstance(alias, str):
                pairgroup_categories[(name, alias)] = resolved_category

    introduced = set()
    chapter_names = set()
    for chapter_index, chapter in enumerate(chapters):
        path = f"$.chapters[{chapter_index}]"
        if not isinstance(chapter, dict):
            continue
        name = chapter.get("name")
        if isinstance(name, str):
            if name in chapter_names:
                errors.append(f"{path}.name: duplicate Chapter name {name!r}")
            chapter_names.add(name)
            for character in invalid_linguistic_characters(name, allow_underscore=True):
                errors.append(f"{path}.name: forbidden character {character_description(character)}")
        labels = chapter.get("column_variants")
        templates = chapter.get("templates")
        forced = chapter.get("forced_first_side")
        if isinstance(labels, list):
            normalized = [
                label[1:] if isinstance(label, str) and label.startswith("~") else label
                for label in labels
            ]
            string_labels = [label for label in normalized if isinstance(label, str)]
            if len(string_labels) == len(normalized) and len(set(string_labels)) != len(string_labels):
                errors.append(f"{path}.column_variants: duplicate Side labels after removing '~'")
            if labels and isinstance(labels[0], str) and labels[0].startswith("~"):
                errors.append(f"{path}.column_variants[0]: compiled Side zero is supplementary")
            if isinstance(forced, int) and not isinstance(forced, bool) and not 0 <= forced < len(labels):
                errors.append(f"{path}.forced_first_side: outside the source Side range")
        if isinstance(templates, list) and isinstance(labels, list):
            for template_index, template in enumerate(templates):
                template_path = f"{path}.templates[{template_index}]"
                sides = template.get("sides") if isinstance(template, dict) else None
                if not isinstance(sides, list):
                    continue
                if len(sides) != len(labels):
                    errors.append(f"{template_path}.sides: length does not match column_variants")
                selections_by_side = []
                used_pairgroups = set()
                for side_index, side in enumerate(sides):
                    if not isinstance(side, str):
                        selections_by_side.append(set())
                        continue
                    tokens, token_errors = parse_side_tokens(side)
                    for error in token_errors:
                        errors.append(f"{template_path}.sides[{side_index}]: {error}")
                    default_variant = None
                    if side_index < len(labels) and isinstance(labels[side_index], str):
                        default_variant = labels[side_index].lstrip("~")
                    selections = set()
                    for kind, parts in tokens:
                        if kind == "group":
                            group = group_by_name.get(parts[0])
                            selection = ("group", parts[0])
                            if group is None:
                                errors.append(f"{template_path}.sides[{side_index}]: unknown Group {parts[0]!r}")
                            else:
                                variant = parts[1] if len(parts) == 2 else default_variant
                                category_name = group.get("category_name")
                                category = (
                                    category_by_name.get(category_name)
                                    if isinstance(category_name, str)
                                    else None
                                )
                                variants = (
                                    category.get("variant_names")
                                    if category is not None
                                    else None
                                )
                                if isinstance(variants, list) and variant not in variants:
                                    errors.append(
                                        f"{template_path}.sides[{side_index}]: unknown Variant {variant!r} "
                                        f"for Group {parts[0]!r}"
                                    )
                        else:
                            pairgroup_name, alias = parts[:2]
                            selection = ("pairgroup", pairgroup_name, alias)
                            used_pairgroups.add(pairgroup_name)
                            pairgroup = pairgroup_by_name.get(pairgroup_name)
                            if pairgroup is None:
                                errors.append(
                                    f"{template_path}.sides[{side_index}]: unknown Pairgroup {pairgroup_name!r}"
                                )
                            elif not isinstance(pairgroup.get("column_names"), list) or alias not in pairgroup[
                                "column_names"
                            ]:
                                errors.append(
                                    f"{template_path}.sides[{side_index}]: unknown alias {alias!r} "
                                    f"in Pairgroup {pairgroup_name!r}"
                                )
                            else:
                                variant = parts[2] if len(parts) == 3 else default_variant
                                category_name = pairgroup_categories.get((pairgroup_name, alias))
                                category = category_by_name.get(category_name)
                                variants = (
                                    category.get("variant_names")
                                    if category is not None
                                    else None
                                )
                                if isinstance(variants, list) and variant not in variants:
                                    errors.append(
                                        f"{template_path}.sides[{side_index}]: unknown Variant {variant!r} "
                                        f"for Pairgroup alias {alias!r}"
                                    )
                        if selection in selections:
                            errors.append(
                                f"{template_path}.sides[{side_index}]: repeated selection {selection[1:]!r}"
                            )
                        selections.add(selection)
                    selections_by_side.append(selections)
                if len(used_pairgroups) > 1:
                    errors.append(f"{template_path}: references more than one Pairgroup")
                if selections_by_side:
                    for side_index, selections in enumerate(selections_by_side[1:], 1):
                        for selection in selections - selections_by_side[0]:
                            errors.append(
                                f"{template_path}.sides[{side_index}]: selection {selection[1:]!r} "
                                f"is absent from Side zero"
                            )
        vocab = chapter.get("vocab")
        if isinstance(vocab, list):
            for vocab_index, declaration in enumerate(vocab):
                vocab_path = f"{path}.vocab[{vocab_index}]"
                if not isinstance(declaration, dict):
                    continue
                category_name = declaration.get("category_name")
                key_variant = declaration.get("key_variant_name")
                category = (
                    category_by_name.get(category_name)
                    if isinstance(category_name, str)
                    else None
                )
                if category is None:
                    errors.append(f"{vocab_path}.category_name: unknown Category {category_name!r}")
                elif not isinstance(category.get("variant_names"), list) or key_variant not in category[
                    "variant_names"
                ]:
                    errors.append(f"{vocab_path}.key_variant_name: unknown Variant {key_variant!r}")
                keys = declaration.get("keys")
                if isinstance(keys, list):
                    for key_index, key in enumerate(keys):
                        if isinstance(key, str):
                            if "," in key or "{" in key or "}" in key:
                                errors.append(
                                    f"{vocab_path}.keys[{key_index}]: vocabulary keys cannot "
                                    "contain commas or braces"
                                )
                            for character in invalid_linguistic_characters(key):
                                errors.append(
                                    f"{vocab_path}.keys[{key_index}]: forbidden lookup character "
                                    f"{character_description(character)}"
                                )
                        found = matches(category_name, key_variant, key)
                        if not found:
                            errors.append(f"{vocab_path}.keys[{key_index}]: unresolved Selectable {key!r}")
                        else:
                            identity = found[0]
                            if identity in introduced:
                                errors.append(
                                    f"{vocab_path}.keys[{key_index}]: Selectable is introduced more than once"
                                )
                            introduced.add(identity)

    return errors
