import json
import csv
import sys
import re
import argparse
import traceback


class ParsedDeck:
    def __init__(self):
        self.categories = []
        self.groups = []
        self.pair_groups = []
        self.chapters = []


class ParsedSelectableCategory:
    def __init__(self, name_string, columns_tuple):
        self.name = name_string
        self.variant_names = columns_tuple
        self.num_variants = len(columns_tuple)
        self.selectables = []


class ParsedSelectable:
    def __init__(self, variants_tuple):
        self.variants = variants_tuple


class ParsedGroup:
    def __init__(self, name, category_name, key_variant, keys):
        self.name = name
        self.category_name = category_name
        self.key_variant_name = key_variant
        self.keys = keys


class ParsedPairGroup:
    def __init__(self, name, col_names, col_types, num_col, validity):
        self.name = name
        self.column_names = col_names
        self.column_types = col_types
        self.category_checking = [None] * num_col
        self.pairs = []
        self.valid = validity


class ParsedChapter:
    def __init__(self, name, col_variants, forced_idx):
        self.name = name
        self.column_variants = col_variants
        self.forced_first_side = forced_idx
        self.templates = []
        self.vocab = []


class ParsedTemplate:
    def __init__(self):
        self.sides = []


class Parser:
    def __init__(self):
        self.current_state = None
        self.line_index = 0

        self.current_subheader_str = None
        self.extending_object_index = None
        self.current_object = None
        self.following_subheader = False
        self.num_subheader_columns = 0
        self.num_template_sides = 0
        self.current_template = None
        self.parsed_deck = ParsedDeck()
        self.has_pair_groups = False

        self.issues = []
        self.infos = []
        self.debug = False

    def process_line(self, line):
        self.line_index += 1
        try:
            # skip empty lines and comments
            if (not line) or (line[0][:2] == "//") or (line[0][:4] == "<!--"):
                return

            # alter state if header encountered
            if line[0][:2] == "# ":
                header_str = line[0][2:]
                self.change_state(header_str)
                return

            if self.current_state == "ParseSelectables":
                self.parse_selectables(line)
            elif self.current_state == "ParseGroups":
                self.parse_groups(line)
            elif self.current_state == "ParsePairGroups":
                self.parse_pairgroups(line)
            elif self.current_state == "ParseTemplates":
                self.parse_templates(line)
            else:
                pass  # may be on lines before or after valid headers.
        except Exception as e:
            # Get current exception information
            exc_type, exc_value, exc_traceback = sys.exc_info()
            # Extract and format the traceback
            tb = traceback.extract_tb(exc_traceback)
            # Get the last line of the traceback, which is where the exception occurred
            filename, line, func, text = tb[-1]
            self.log_issue(f"Unidentifiable error - may be caused by prior errors")
            if self.debug:
                print(f"Line {line}: {e}")

    def change_state(self, str):
        # TODO: ensure all transitions are in this order
        if str == "Selectables":
            # print("PARSING SELECTABLES")
            self.current_state = "ParseSelectables"
        elif str == "Groups":
            # print("PARSING GROUPS")
            # append leftover category, if it wasn't an extension
            if self.current_object:
                self.parsed_deck.categories.append(self.current_object)
            self.current_object = None
            self.current_subheader_str = None

            self.current_state = "ParseGroups"
        elif str == "Pair Groups" or str == "PairGroups":
            # print("PARSING PAIR GROUPS")
            # groups do not have leftovers
            self.has_pair_groups = True
            self.current_state = "ParsePairGroups"
        elif str == "Templates":
            # print("PARSING CARDS")
            # append leftover pairgroup
            if self.has_pair_groups:
                self.parsed_deck.pair_groups.append(self.current_object)
            self.current_subheader_str = None
            self.current_object = None

            self.current_state = "ParseTemplates"
        else:
            self.current_state == None
            self.log_issue(f"Bad header '{str}'")

    def parse_selectables(self, line):
        # TODO: duplicate checking
        if line[0][:3] == "## ":
            ## finalize previous category, if it exists
            if self.current_object:
                self.parsed_deck.categories.append(self.current_object)
                self.current_object = None
            elif self.extending_object_index != None:
                self.extending_object_index = None
            self.current_subheader_str = line[0][3:]
            # duplicate checking
            for i, category in enumerate(self.parsed_deck.categories):
                if self.current_subheader_str == category.name:
                    self.log_info(f"Found duplicated category {category.name}")
                    self.extending_object_index = i
            self.following_subheader = True
            return

        # collect labels from the immediately following line
        if self.following_subheader:
            # check for indentation, but don't mess stuff up if it's missing
            if line[0][0] == ">":
                line[0] = line[0][1:]
            else:
                self.log_issue(f"Subheader info line not indented, needs '>'")
            # this is used regardless of whether it's a dupe extension or not
            self.num_subheader_columns = len(line)
            # if duplicate, double check the columns
            if self.extending_object_index != None:
                category = self.parsed_deck.categories[self.extending_object_index]
                if category.variant_names != line:
                    self.log_issue(
                        f"Category extension variant names '{','.join(line)}'"
                        f" do not match prior variant names "
                        f"'{','.join(category.variant_names)}'"
                    )
            else:
                self.current_object = ParsedSelectableCategory(
                    self.current_subheader_str, line
                )
            self.following_subheader = False
            return

        # otherwise parse a selectable as a row of variants
        if len(line) != self.num_subheader_columns:
            self.log_issue(
                f"Number of selectable columns [{len(line)}] does not match header "
                f"[{self.num_subheader_columns}]"
            )
        else:
            if self.extending_object_index != None:
                # Extend the existing category with a new selectable
                category = self.parsed_deck.categories[self.extending_object_index]
                parsed_selectable = ParsedSelectable(line)
                for selectable in category.selectables:
                    if selectable.variants == parsed_selectable.variants:
                        self.log_info(
                            f"Found duplicate selectable '{line[0]}' while extending "
                            f"category, skipping"
                        )
                        return
                self.log_info(
                    f"Extending category {category.name} with selectable {','.join(line)}"
                )
                category.selectables.append(parsed_selectable)
            else:
                # add selectable to new in-progress category
                self.current_object.selectables.append(ParsedSelectable(line))

    def parse_groups(self, line):
        # Groups are all on one line, and always 4 entries
        if len(line) != 4:
            self.log_issue("Wrong separators, check semicolon use")
            return
        group_name = line[0]
        category_name = line[1]
        key_variant = line[2]
        keys = line[3][1:-1].split(",")

        self.check_group_integrity(category_name, key_variant, keys)

        # Extend or fail for duplicate groups
        found_duplicate = False
        for i, group in enumerate(self.parsed_deck.groups):
            if group_name == group.name:
                found_duplicate = True
                if group.category_name != category_name:
                    self.log_issue(
                        f"Expanding group with category {category_name}"
                        f"does not match prior category {group.category_name}"
                    )
                    return
                elif group.key_variant_name != key_variant:
                    self.log_issue(
                        f"Expanding group with key variant {key_variant}"
                        f"does not match prior key variant {group.key_variant_name}"
                    )
                    return
                else:
                    # exists and new one is a valid extension. Extend it.
                    # we already know integrity is good from before
                    extended = False
                    for key in keys:
                        if key not in group.keys:
                            self.log_info(f"Extended group {group_name} with key {key}")
                            self.parsed_deck.groups[i].keys.append(key)
                            extended = True
                    if not extended:
                        self.log_info(f"Duplicate group {group_name} had no new keys")
        if not found_duplicate:
            self.parsed_deck.groups.append(
                ParsedGroup(group_name, category_name, key_variant, keys)
            )

    def check_group_integrity(self, category_name, key_variant, keys):
        # Data integrity checking
        found_category = None
        # check if the category exists
        for category in self.parsed_deck.categories:
            if category.name == category_name:
                found_category = category
                break  # Exit the loop once a match is found
        if not found_category:
            self.log_issue(f"No selectable category '{category_name}' found for group")
        else:
            # check if the key variant exists in the category
            found_key_variant_index = None
            for count, variant_name in enumerate(found_category.variant_names):
                if variant_name == key_variant:
                    found_key_variant_index = count
            if found_key_variant_index == None:
                self.log_issue(
                    f"No selectable variant '{key_variant}' found in"
                    f"selectable category '{category_name}'"
                )
                return
            # check if all group keys can be found in the selectable category column
            for key in keys:
                found_key = False
                for selectable in found_category.selectables:
                    if key == selectable.variants[found_key_variant_index]:
                        found_key = True
                if not found_key:
                    self.log_issue(
                        f"No selectable '{key}' under column '{key_variant}' "
                        f"found in selectable category '{category_name}'"
                    )

    def parse_pairgroups(self, line):
        # Obtain pairgroup name, prep new structure
        if line[0][:3] == "## ":
            ## finalize previous pairgroup, if it exists
            if self.current_object:
                self.parsed_deck.pair_groups.append(self.current_object)
                self.current_object = None
            self.current_subheader_str = line[0][3:]
            self.following_subheader = True
            return
        # get names/types from follower line
        if self.following_subheader:
            if line[0][0] == ">":
                line[0] = line[0][1:]
            else:
                self.log_issue(f"Subheader info line not indented, needs '>'")
            self.num_subheader_columns = len(line)
            names = []
            types = []
            for section in line:
                names.append(section.split("=")[0])
                types.append(section.split("=")[1])
            validity = True
            # check subheader integrity
            for name, type in zip(names, types):
                type_category = type.split(":")[0]
                if type_category == "selectable":
                    ## see if we have enough type info
                    if len(type.split(":")) < 3:
                        self.log_issue(
                            f"Insufficient type information for column '{name}'"
                        )
                        validity = False
                        continue
                    ## check that the category exists
                    category_name = type.split(":")[1]
                    variant_name = type.split(":")[2]
                    found_category = False
                    for category in self.parsed_deck.categories:
                        if category.name == category_name:
                            found_category = category
                    if not found_category:
                        validity = False
                        self.log_issue(
                            f"Category '{category_name}' for column '{name}' not found"
                        )
                    else:
                        ## check that the variant exists in the category
                        if variant_name not in found_category.variant_names:
                            validity = False
                            self.log_issue(
                                f"Variant name '{variant_name }' not found in "
                                f"'{category_name}' for column '{name}'"
                            )
                elif type_category != "group":
                    validity = False
                    self.log_issue(f"Pair members must be either groups or selectables")

            # Check for duplicates (simple)
            # TODO: allow pairgroup extension across files
            for pairgroup in self.parsed_deck.pair_groups:
                if self.current_subheader_str == pairgroup.name:
                    self.log_issue(
                        f"Extending pairgroup {pairgroup.name} is not supported"
                    )
                    validity = False

            self.current_object = ParsedPairGroup(
                self.current_subheader_str,
                names,
                types,
                self.num_subheader_columns,
                validity,
            )
            self.following_subheader = False
            return
        # Otherwise, start parsing pairs
        if len(line) != self.num_subheader_columns:
            self.log_issue(
                f"Number of pair columns [{len(line)}] does not match header "
                f"[{self.num_subheader_columns}]"
            )
        # Data integrity checking
        for count, member in enumerate(line):
            if not self.current_object.valid:
                self.log_issue(f"Pair not parsed as pair group is invalid")
                return
            if self.current_object.column_types[count].split(":")[0] == "group":
                group = self.get_object_by_name(member, self.parsed_deck.groups)
                if not group:
                    self.log_issue(
                        f"No matching group for pair member '{member}' at index {count}"
                    )
                    return
                # if not member in [group.name for group in self.parsed_deck.groups]:
                if not self.current_object.category_checking[count]:
                    self.current_object.category_checking[count] = group.category_name
                else:
                    if (
                        group.category_name
                        != self.current_object.category_checking[count]
                    ):
                        self.log_issue(
                            f"Group's category '{group.category_name}' must match categories "
                            f"in other groups of this column "
                            f"({self.current_object.category_checking[count]})"
                        )
            if self.current_object.column_types[count].split(":")[0] == "selectable":
                category_name = self.current_object.column_types[count].split(":")[1]
                variant_name = self.current_object.column_types[count].split(":")[2]
                found_category = None
                found_selectable = False
                # fetch the category by name. We've already validated it exists in the header.
                found_category = next(
                    (
                        obj
                        for obj in self.parsed_deck.categories
                        if obj.name == category_name
                    ),
                    None,
                )
                if found_category:
                    found_key_variant_index = None
                    for count, variant_str in enumerate(found_category.variant_names):
                        if variant_str == variant_name:
                            found_key_variant_index = count
                    if found_key_variant_index != None:
                        for variant in [
                            selectable.variants[found_key_variant_index]
                            for selectable in found_category.selectables
                        ]:
                            if variant == member:
                                found_selectable = True
                    else:
                        self.log_issue(f"Uncaught error with pg subheader")
                        return
                if not found_selectable:
                    self.log_issue(
                        f"Could not find selectable '{member}' in category "
                        f"'{found_category.name}', column {found_key_variant_index}"
                    )
                    return
        self.current_object.pairs.append(line)

    def parse_templates(self, line):
        # Obtain pairgroup name, prep new structure
        if line[0][:3] == "## ":
            ## finalize previous chapter, if it exists
            if self.current_object:
                self.parsed_deck.chapters.append(self.current_object)
                self.current_object = None
            self.current_subheader_str = line[0][3:]
            self.following_subheader = True
            return
        if self.following_subheader:
            if line[0][0] == ">":
                line[0] = line[0][1:]
            else:
                self.log_issue(f"Subheader info line not indented, needs '>'")
            self.num_subheader_columns = len(line)
            # find if any of the side titles is "forced first"
            forced_idx = 0
            for count, name in enumerate(line):
                if name[0] == "^":
                    forced_idx = count
                    line[count] = name[1:]
                    line.insert(0, line.pop(count))

            self.current_object = ParsedChapter(
                self.current_subheader_str, line, forced_idx
            )
            self.following_subheader = False
            return
        if line[0][:6] == ">vocab":
            if len(line) != 4:
                self.log_issue(f"Wrong separators, check semicolon use")
                return
            # interpret vocab line
            self.insert_vocab(line[1:])
            return
        if line[0][0] == "{":
            # TODO detect errant text outside brackets
            self.num_template_sides = 0
            self.current_template = ParsedTemplate()
            return
        elif line[0][0] == "}":
            if self.num_template_sides != self.num_subheader_columns:
                self.log_issue(
                    f"Number of template sides [{self.num_template_sides}] does not "
                    f"match header [{self.num_subheader_columns}]"
                )
            self.current_object.templates.append(self.current_template)
            return
        else:
            # TODO: check vocab integrity
            # templates with {} format do not use separators
            line_str = "".join(line)
            # trim the preceding tab, if it exists
            line_str.lstrip()

            # figure out remap of template side labels for forced first sides
            is_forced_first = False
            true_label_index = 0
            if self.num_template_sides == self.current_object.forced_first_side:
                is_forced_first = True
                true_label_index = 0
            elif self.num_template_sides < self.current_object.forced_first_side:
                true_label_index = self.num_template_sides + 1
            else:
                true_label_index = self.num_template_sides

            # data integrity
            default = self.current_object.column_variants[true_label_index]
            if self.check_template_side_integrity(line_str, default):
                if is_forced_first:
                    self.current_template.sides.insert(0, line_str)
                else:
                    self.current_template.sides.append(line_str)

            self.num_template_sides += 1

    def insert_vocab(self, line):
        # Groups are all on one line
        category_name = line[0]
        key_variant = line[1]
        keys = line[2][1:-1].split(",")

        self.check_group_integrity(category_name, key_variant, keys)

        self.current_object.vocab.append(
            ParsedGroup("vocab", category_name, key_variant, keys)
        )
        return

    def check_template_side_integrity(self, text, default):
        if default[0] == "~":
            default = default[1:]
        replaceables = re.findall(r"\[(.*?)\]", text)
        integrity_good = True
        group_variants = []
        for rep in replaceables:
            rep = rep.split(":")
            group = rep[0]
            if len(rep) == 1:
                variant = default
            else:
                variant = rep[1]
            group_variants.append((group, variant))
        for gv in group_variants:
            found_group = self.get_object_by_name(gv[0], self.parsed_deck.groups)
            if not found_group:
                self.log_issue(f"No group '{gv[0]}' found for side")
                integrity_good = False
            else:
                category = self.get_object_by_name(
                    found_group.category_name, self.parsed_deck.categories
                )
                if not gv[1] in category.variant_names:
                    self.log_issue(
                        f"No variant '{gv[1]}' in category '{category.name}', used "
                        f"in group '{gv[0]}'"
                    )
                    integrity_good = False

        pg_replaceables = re.findall(r"\<(.*?)\>", text)
        first_pg_name = None
        if pg_replaceables and not self.parsed_deck.pair_groups:
            self.log_issue(f"Contains pair group, but no pair groups in deck")
            integrity_good = False
            return
        for pg in pg_replaceables:
            pg = pg.split(":")
            # pair groups need at least a name and alias
            if len(pg) < 2:
                self.log_issue(
                    f"Not enough type information in Pair Group replaceable '{pg}'"
                )
                integrity_good = False
            pg_name = pg[0]
            # only allow one pair group per side
            # TODO: it should be only one per template, too, but that'd be harder to mess up
            if not first_pg_name:
                first_pg_name = pg_name
            else:
                if pg_name != first_pg_name:
                    self.log_issue(
                        f"Pair group name '{pg_name}' does not match others in the side"
                    )
                    integrity_good = False
            # gather other pg information
            pg_alias = pg[1]
            pg_varlabel = None
            if len(pg) == 3:
                pg_varlabel = pg[2]

            pair_group = next(
                (
                    pair_group
                    for pair_group in self.parsed_deck.pair_groups
                    if pair_group.name == pg_name
                ),
                None,
            )
            ## check if the pair group exists
            if not pair_group:
                self.log_issue(f"Could not find pair group '{pg_name}'")
            else:
                aliases = pair_group.column_names
                types = pair_group.column_types
                ## check if the alias exists
                if pg_alias not in aliases:
                    self.log_issue(f"Could not find alias '{pg_alias}'")
                    continue
                else:
                    count = aliases.index(pg_alias)
                    type = types[count].split(":")
                    # we assume the type is good, since it was checked earlier.
                    cata = type[0]
                    # TODO: check if selectable variant label is valid
                    if cata == "selectable":
                        category_name = type[1]
                        category = self.get_object_by_name(
                            category_name, self.parsed_deck.categories
                        )
                        # don't check if category exists, we already did
                        if pg_varlabel:
                            if not pg_varlabel in category.variant_names:
                                self.log_issue(
                                    f"No variant in '{category_name}' named "
                                    f"'{pg_varlabel}'"
                                )
                        else:
                            if not default in category.variant_names:
                                self.log_issue(
                                    f"Autoassigned variant for '{category_name}' "
                                    f"does not match '{default}'"
                                )
                    elif cata == "group":
                        # selectable must be the same across groups, so it'll be the same
                        # as that of the first matching group in the first pair of the pairgroup
                        group_name = pair_group.pairs[0][count]
                        found_group = self.get_object_by_name(
                            group_name, self.parsed_deck.groups
                        )
                        category = self.get_object_by_name(
                            found_group.category_name, self.parsed_deck.categories
                        )
                        if pg_varlabel:
                            if not pg_varlabel in category.variant_names:
                                self.log_issue(
                                    f"No variant for group's category '{category.name}' named "
                                    f"'{pg_varlabel}'"
                                )
                        else:
                            if not default in category.variant_names:
                                self.log_issue(
                                    f"Autoassigned variant for group '{category.name}' "
                                    f"does not match '{default}'"
                                )

        return integrity_good

    def get_object_by_name(self, object_name, object_list):
        object = next(
            (object for object in object_list if object.name == object_name),
            None,
        )
        return object

    def handle_eof(self):
        # process any final, unhandled chapter of templates
        self.parsed_deck.chapters.append(self.current_object)
        # reset all working values
        self.current_state = None
        self.line_index = 0
        self.current_subheader_str = None
        self.extending_object_index = None
        self.current_object = None
        self.following_subheader = False
        self.num_subheader_columns = 0
        self.num_template_sides = 0
        self.current_template = None

    def print_json(self):
        json_data = json.dumps(self.parsed_deck, default=lambda o: o.__dict__, indent=4)
        print(json_data)

    def log_issue(self, str):
        self.issues.append((self.line_index, str))

    def log_info(self, str):
        self.infos.append((self.line_index, str))

    def print_issues(self):
        if len(self.issues) > 0:
            print("ISSUES:")
        for issue in self.issues:
            print(issue)


def parse_file_lines(lacparser: Parser, file_str, verbose, primary=False):
    with open(file_str, "r") as file:
        reader = csv.reader(file, delimiter=";")
        data = list(reader)

    lacparser.line_index = 0
    for line in data:
        if verbose and primary:
            print(",".join(line))
        lacparser.process_line(line)
    lacparser.handle_eof()


if __name__ == "__main__":
    argparser = argparse.ArgumentParser(description="Lacuna Parser")
    argparser.add_argument(
        "primary_file",
        metavar="FILE",
        help="Current deck file to scan for issues",
    )
    argparser.add_argument(
        "-f",
        "--prior-files",
        metavar="PRIOR_FILE",
        nargs="+",
        help="Preceding decks to supply data to the current file",
    )
    argparser.add_argument(
        "-i",
        "--issues-only",
        action="store_true",
        help="Only print list of issues, excluding JSON output",
    )
    argparser.add_argument(
        "-v", "--verbose", action="store_true", help="Print lines as they're processed"
    )
    argparser.add_argument(
        "-d", "--debug", action="store_true", help="Print debug information"
    )
    argparser.add_argument(
        "-l",
        "--list-infos",
        action="store_true",
        help="Show additional information about deck redundancy",
    )

    args = argparser.parse_args()
    lacparser = Parser()
    if args.debug:
        lacparser.debug = True
    if args.prior_files:
        for count, file_str in enumerate(args.prior_files):
            if args.list_infos:
                print(f"PARSING PRIOR FILE: {file_str}")
            parse_file_lines(lacparser, file_str, args.verbose, primary=False)
            if lacparser.issues:
                print(
                    f"Error: precedent file {count} contains issues before primary file"
                )
                exit()

    if args.list_infos:
        print(f"PARSING MAIN FILE: {args.primary_file}")
    parse_file_lines(lacparser, args.primary_file, args.verbose, primary=True)

    lacparser.print_issues()
    if not args.issues_only:
        lacparser.print_json()
    if args.list_infos:
        print("INFO:")
        for info in lacparser.infos:
            print(info)
