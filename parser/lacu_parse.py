import json
import csv
import sys
import re


class ParsedDeck:
    def __init__(self):
        self.subgroups = []
        self.groups = []
        self.pair_groups = []
        self.chapters = []


class ParsedSelectablesSubgroup:
    def __init__(self, name_string, columns_tuple):
        self.name = name_string
        self.variant_names = columns_tuple
        self.num_variants = len(columns_tuple)
        self.selectables = []


class ParsedSelectable:
    def __init__(self, variants_tuple):
        self.variants = variants_tuple


class ParsedGroup:
    def __init__(self, name, subgroup_name, key_variant, keys):
        self.name = name
        self.subgroup_name = subgroup_name
        self.key_variant_name = key_variant
        self.keys = keys


class ParsedPairGroup:
    def __init__(self, name, col_names, col_types, num_col, validity):
        self.name = name
        self.column_names = col_names
        self.column_types = col_types
        self.subgroup_checking = [None] * num_col
        self.pairs = []
        self.valid = validity


class ParsedChapter:
    def __init__(self, name, col_variants, forced_idx):
        self.name = name
        self.column_variants = col_variants
        self.forced_first_side = forced_idx
        self.cards = []
        self.vocab = []


class ParsedCard:
    def __init__(self):
        self.sides = []


class Parser:
    def __init__(self):
        self.current_state = None
        self.line_index = 0
        self.issues = []
        self.current_subheader_str = None
        self.current_object = None
        self.following_subheader = False
        self.num_subheader_columns = 0
        self.num_card_sides = 0
        self.parsed_deck = ParsedDeck()
        self.has_pair_groups = False

        # cards are multi-line
        self.current_card = None

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
            elif self.current_state == "ParseCards":
                self.parse_cards(line)
            else:
                pass  # may be on lines before or after valid headers.
        except:
            self.log_issue(f"Unidentifiable error - may be caused by prior errors")

    def change_state(self, str):
        # TODO: ensure all transitions are in this order
        if str == "Selectables":
            # print("PARSING SELECTABLES")
            self.current_state = "ParseSelectables"
        elif str == "Groups":
            # print("PARSING GROUPS")
            # append leftover selectable
            self.parsed_deck.subgroups.append(self.current_object)
            self.current_object = None
            self.current_subheader_str = None

            self.current_state = "ParseGroups"
        elif str == "Pair Groups" or str == "PairGroups":
            # print("PARSING PAIR GROUPS")
            # groups do not have leftovers
            self.has_pair_groups = True
            self.current_state = "ParsePairGroups"
        elif str == "Cards":
            # print("PARSING CARDS")
            # append leftover pairgroup
            if self.has_pair_groups:
                self.parsed_deck.pair_groups.append(self.current_object)
            self.current_subheader_str = None
            self.current_object = None

            self.current_state = "ParseCards"
        else:
            self.current_state == None
            self.log_issue(f"Bad header '{str}'")

    def log_issue(self, str):
        self.issues.append((self.line_index, str))

    def parse_selectables(self, line):
        # TODO: duplicate checking
        if line[0][:3] == "## ":
            ## finalize previous subgroup, if it exists
            if self.current_object:
                self.parsed_deck.subgroups.append(self.current_object)
                self.current_object = None
            self.current_subheader_str = line[0][3:]
            self.following_subheader = True
            return

        # collect labels from the immediately following line
        if self.following_subheader:
            # check for indentation, but don't mess stuff up if it's missing
            if line[0][0] == ">":
                line[0] = line[0][1:]
            else:
                self.log_issue(f"Subheader info line not indented, needs '>'")
            self.num_subheader_columns = len(line)
            self.current_object = ParsedSelectablesSubgroup(
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
            self.current_object.selectables.append(ParsedSelectable(line))

    def parse_groups(self, line):
        # Groups are all on one line
        group_name = line[0]
        subgroup_name = line[1]
        key_variant = line[2]
        keys = line[3][1:-1].split(",")

        self.check_group_integrity(subgroup_name, key_variant, keys)

        self.parsed_deck.groups.append(
            ParsedGroup(group_name, subgroup_name, key_variant, keys)
        )

    def check_group_integrity(self, subgroup_name, key_variant, keys):
        # TODO: duplicate checking
        # Data integrity checking
        found_subgroup = None
        # check if the subgroup exists
        for subgroup in self.parsed_deck.subgroups:
            if subgroup.name == subgroup_name:
                found_subgroup = subgroup
                break  # Exit the loop once a match is found
        if not found_subgroup:
            self.log_issue(f"No selectable subgroup '{subgroup_name}' found for group")
        else:
            # check if the key variant exists in the subgroup
            found_key_variant_index = None
            for count, variant_name in enumerate(found_subgroup.variant_names):
                if variant_name == key_variant:
                    found_key_variant_index = count
            if found_key_variant_index == None:
                self.log_issue(
                    f"No selectable variant '{key_variant}' found in"
                    f"selectable subgroup '{subgroup_name}'"
                )
                return
            # check if all group keys can be found in the selectable subgroup column
            for key in keys:
                found_key = False
                for selectable in found_subgroup.selectables:
                    if key == selectable.variants[found_key_variant_index]:
                        found_key = True
                if not found_key:
                    self.log_issue(
                        f"No selectable '{key}' under column '{key_variant}' "
                        f"found in selectable subgroup '{subgroup_name}'"
                    )

    def parse_pairgroups(self, line):
        # print(line)
        # TODO: duplicate checking
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
                    ## check that the subgroup exists
                    subgroup_name = type.split(":")[1]
                    variant_name = type.split(":")[2]
                    found_subgroup = False
                    for subgroup in self.parsed_deck.subgroups:
                        if subgroup.name == subgroup_name:
                            found_subgroup = subgroup
                    if not found_subgroup:
                        validity = False
                        self.log_issue(
                            f"Subgroup '{subgroup_name}' for column '{name}' not found"
                        )
                    else:
                        ## check that the variant exists in the subgroup
                        if variant_name not in found_subgroup.variant_names:
                            validity = False
                            self.log_issue(
                                f"Variant name '{variant_name }' not found in "
                                f"'{subgroup_name}' for column '{name}'"
                            )
                elif type_category != "group":
                    validity = False
                    self.log_issue(f"Pair members must be either groups or selectables")

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
                if not self.current_object.subgroup_checking[count]:
                    self.current_object.subgroup_checking[count] = group.subgroup_name
                else:
                    if (
                        group.subgroup_name
                        != self.current_object.subgroup_checking[count]
                    ):
                        self.log_issue(
                            f"Group's subgroup '{group.subgroup_name}' must match subgroups "
                            f"in other groups of this column "
                            f"({self.current_object.subgroup_checking[count]})"
                        )
            if self.current_object.column_types[count].split(":")[0] == "selectable":
                subgroup_name = self.current_object.column_types[count].split(":")[1]
                variant_name = self.current_object.column_types[count].split(":")[2]
                found_subgroup = None
                found_selectable = False
                # check if the subgroup exists
                for subgroup in self.parsed_deck.subgroups:
                    if subgroup.name == subgroup_name:
                        found_subgroup = subgroup
                        break  # Exit the loop once a match is found
                if not found_subgroup:
                    self.log_issue(f"Could not find sugbroup name '{subgroup_name}'")
                    return
                if found_subgroup:
                    found_key_variant_index = None
                    for count, variant_str in enumerate(found_subgroup.variant_names):
                        if variant_str == variant_name:
                            found_key_variant_index = count
                    if not found_key_variant_index:
                        self.log_issue(f"Did not find variant '{variant_name}'")
                        return
                    if found_key_variant_index:
                        for variant in [
                            selectable.variants[found_key_variant_index]
                            for selectable in found_subgroup.selectables
                        ]:
                            if variant == member:
                                found_selectable = True
                if not found_selectable:
                    self.log_issue(
                        f"Could not find selectable '{member}' in subgroup "
                        f"'{found_subgroup.name}', column {found_key_variant_index}"
                    )
                    return
        self.current_object.pairs.append(line)

    def parse_cards(self, line):
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
            if len(line[0]) > 6:
                self.log_issue(f"vocab sections must be separated by semicolons (;)")
                return
            # interpret vocab line
            self.insert_vocab(line[1:])
            return
        if line[0][0] == "{":
            # TODO detect errant text outside brackets
            self.num_card_sides = 0
            self.current_card = ParsedCard()
            return
        elif line[0][0] == "}":
            if self.num_card_sides != self.num_subheader_columns:
                self.log_issue(
                    f"Number of card sides [{self.num_card_sides}] does not "
                    f"match header [{self.num_subheader_columns}]"
                )
            self.current_object.cards.append(self.current_card)
            return
        else:
            # TODO: check vocab integrity
            # cards with {} format do not use separators
            line_str = "".join(line)
            # trim the preceding tab, if it exists
            line_str.lstrip()

            # figure out remap of card side labels for forced first sides
            is_forced_first = False
            true_label_index = 0
            if self.num_card_sides == self.current_object.forced_first_side:
                is_forced_first = True
                true_label_index = 0
            elif self.num_card_sides < self.current_object.forced_first_side:
                true_label_index = self.num_card_sides + 1
            else:
                true_label_index = self.num_card_sides

            # data integrity
            default = self.current_object.column_variants[true_label_index]
            if self.check_card_side_integrity(line_str, default):
                if is_forced_first:
                    self.current_card.sides.insert(0, line_str)
                else:
                    self.current_card.sides.append(line_str)

            self.num_card_sides += 1

    def insert_vocab(self, line):
        # Groups are all on one line
        subgroup_name = line[0]
        key_variant = line[1]
        keys = line[2][1:-1].split(",")

        self.check_group_integrity(subgroup_name, key_variant, keys)

        self.current_object.vocab.append(
            ParsedGroup("vocab", subgroup_name, key_variant, keys)
        )
        return

    def check_card_side_integrity(self, text, default):
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
                subgroup = self.get_object_by_name(
                    found_group.subgroup_name, self.parsed_deck.subgroups
                )
                if not gv[1] in subgroup.variant_names:
                    self.log_issue(
                        f"No variant '{gv[1]}' in subgroup '{subgroup.name}', used "
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
            # TODO: it should be only one per card, too, but that'd be harder to mess up
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
                        subgroup_name = type[1]
                        subgroup = self.get_object_by_name(
                            subgroup_name, self.parsed_deck.subgroups
                        )
                        # don't check if subgroup exists, we already did
                        if pg_varlabel:
                            if not pg_varlabel in subgroup.variant_names:
                                self.log_issue(
                                    f"No variant in '{subgroup_name}' named "
                                    f"'{pg_varlabel}'"
                                )
                        else:
                            if not default in subgroup.variant_names:
                                self.log_issue(
                                    f"Autoassigned variant for '{subgroup_name}' "
                                    f"does not match '{default}'"
                                )
                    elif cata == "group":
                        # selectable must be the same across groups, so it'll be the same
                        # as that of the first matching group in the first pair of the pairgroup
                        group_name = pair_group.pairs[0][count]
                        found_group = self.get_object_by_name(
                            group_name, self.parsed_deck.groups
                        )
                        subgroup = self.get_object_by_name(
                            found_group.subgroup_name, self.parsed_deck.subgroups
                        )
                        if pg_varlabel:
                            if not pg_varlabel in subgroup.variant_names:
                                self.log_issue(
                                    f"No variant for group's subgroup '{subgroup.name}' named "
                                    f"'{pg_varlabel}'"
                                )
                        else:
                            if not default in subgroup.variant_names:
                                self.log_issue(
                                    f"Autoassigned variant for group '{subgroup.name}' "
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
        # process any final, unhandled chapter of cards
        self.parsed_deck.chapters.append(self.current_object)

    def print_json(self):
        json_data = json.dumps(self.parsed_deck, default=lambda o: o.__dict__, indent=4)
        print(json_data)

    def print_issues(self):
        if len(self.issues) > 0:
            print("ISSUES:")
        for issue in self.issues:
            print(issue)


def read_file_and_dump(csv_file, issues_only):
    with open(csv_file, "r") as file:
        reader = csv.reader(file, delimiter=";")
        data = list(reader)

    parser = Parser()
    for count, line in enumerate(data):
        # print(f"parsing line {count}")
        parser.process_line(line)
    parser.handle_eof()
    parser.print_issues()
    if not issues_only:
        parser.print_json()


# Example usage
if len(sys.argv) < 2:
    print("Usage: python parser.py <csv_file>")
    sys.exit(1)

issues_only = False
csv_file = sys.argv[1]
if len(sys.argv) >= 3:
    if sys.argv[2] == "-issues-only":
        issues_only = True

read_file_and_dump(csv_file, issues_only)
