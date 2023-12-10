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
    def __init__(self, name, col_names, col_types):
        self.name = name
        self.column_names = col_names
        self.column_types = col_types
        self.pairs = []


class ParsedChapter:
    def __init__(self, name, col_variants):
        self.name = name
        self.column_variants = col_variants
        self.cards = []


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

        # cards are multi-line
        self.current_card = None

    def process_line(self, line):
        # print("processing line")
        self.line_index += 1

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
            self.current_state = "ParsePairGroups"
        elif str == "Cards":
            # print("PARSING CARDS")
            # append leftover pairgroup
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
        self.current_object.selectables.append(ParsedSelectable(line))

    def parse_groups(self, line):
        # Groups are all on one line
        group_name = line[0]
        subgroup_name = line[1]
        key_variant = line[2]
        keys = line[3][1:-1].split(",")

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

        self.parsed_deck.groups.append(
            ParsedGroup(group_name, subgroup_name, key_variant, keys)
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
            self.num_subheader_columns = len(line)
            names = []
            types = []
            for section in line:
                names.append(section.split("=")[0])
                types.append(section.split("=")[1])
            # TODO: this needs unfolded type/integrity checking
            self.current_object = ParsedPairGroup(
                self.current_subheader_str, names, types
            )
            self.following_subheader = False
            return
        # Otherwise, start parsing pairs
        if len(line) != self.num_subheader_columns:
            self.log_issue(
                f"Number of pair columns [{len(line)}]does not match header "
                f"[{self.num_subheader_columns}]"
            )
        # Data integrity checking
        for count, member in enumerate(line):
            if self.current_object.column_types[count].split(":")[0] == "group":
                if not member in [group.name for group in self.parsed_deck.groups]:
                    self.log_issue(
                        f"No matching group for pair member '{member}' at index {count}"
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
                if found_subgroup:
                    found_key_variant_index = None
                    for count, variant_str in enumerate(found_subgroup.variant_names):
                        if variant_str == variant_name:
                            found_key_variant_index = count
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
            self.num_subheader_columns = len(line)
            self.current_object = ParsedChapter(self.current_subheader_str, line)
            self.following_subheader = False
            return
        if line[0][0] == "{":
            self.num_card_sides = 0
            self.current_card = ParsedCard()
            return
        elif line[0][0] == "}":
            if self.num_card_sides != self.num_subheader_columns:
                self.log_issue(
                    f"Number of card sides [{self.num_card_sides}]does not "
                    f"match header [{self.num_subheader_columns}]"
                )
            self.current_object.cards.append(self.current_card)
            return
        else:
            self.num_card_sides += 1
            # cards with {} format do not use separators
            line_str = "".join(line)
            # trim the preceding tab, if it exists
            line_str.lstrip()

            # data integrity
            default = self.current_object.column_variants[self.num_card_sides - 1]
            if self.check_card_side_integrity(line_str,default):
                self.current_card.sides.append(line_str)

    def check_card_side_integrity(self, text, default):
        if default[0] == '~':
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
            found_group = None
            for group in self.parsed_deck.groups:
                if group.name == gv[0]:
                    found_group = group
            if not found_group:
                self.log_issue(f"No group '{gv[0]}' found for side")
                integrity_good = False
            else:
                subgroup = next((
                    subgroup
                    for subgroup in self.parsed_deck.subgroups
                    if subgroup.name == found_group.subgroup_name
                ), None)
                if not gv[1] in subgroup.variant_names:
                    self.log_issue(
                        f"No variant '{gv[1]}' in subgroup '{subgroup.name}', used "
                        f"in group '{gv[0]}'"
                    )
                    integrity_good = False
        return integrity_good

    def handle_eof(self):
        # process any final, unhandled chapter of cards
        self.parsed_deck.chapters.append(self.current_object)

    def print_json(self):
        json_data = json.dumps(self.parsed_deck, default=lambda o: o.__dict__, indent=4)
        print(json_data)

    def print_issues(self):
        print("ISSUES:")
        for issue in self.issues:
            print(issue)


def read_file_and_dump(csv_file):
    with open(csv_file, "r") as file:
        reader = csv.reader(file, delimiter=";")
        data = list(reader)

    parser = Parser()
    for count, line in enumerate(data):
        # print(f"parsing line {count}")
        parser.process_line(line)
    parser.handle_eof()
    parser.print_issues()
    parser.print_json()


# Example usage
if len(sys.argv) < 2:
    print("Usage: python parser.py <csv_file>")
    sys.exit(1)

csv_file = sys.argv[1]
read_file_and_dump(csv_file)
