from japverbconj.constants.enumerated_types import VerbClass
from japverbconj.verb_form_gen import generate_japanese_verb_by_str
import csv
import sys


def conjugate(csv_file):
    with open(csv_file, 'r') as file:
        reader = csv.reader(file,delimiter=';')
        data = list(reader)

    print("dict;a_stem;i_stem;pot_stem;pascau_stem;past_form;te_form;imp_form")

    for row in data:
        verb = row[1]
        outrow = []
        vclass = None
        if row[0] == "g":
            # u verbs
            vclass = VerbClass.GODAN
        elif row[0] == "i":
            # ru verbs
            vclass = VerbClass.ICHIDAN
        elif row[0] == "x":
            # irregular
            vclass = VerbClass.IRREGULAR
        else:
            sys.exit("You have goofened a verbclass")

        # dict stem
        outrow.append(generate_japanese_verb_by_str(verb, vclass, "pla"))

        # a stem
        # 買わない -> 買わ
        outrow.append(generate_japanese_verb_by_str(verb, vclass, "pla", "neg")[:-2])

        # i stem
        # 買います -> 買い
        outrow.append(generate_japanese_verb_by_str(verb, vclass, "pol")[:-2])

        # potential stem (e stem?)
        outrow.append(generate_japanese_verb_by_str(verb, vclass, "pot")[:-2])

        # passive/causative stem
        outrow.append(generate_japanese_verb_by_str(verb, vclass, "pass")[:-2])

        # past informal form
        outrow.append(generate_japanese_verb_by_str(verb, vclass, "pla", "past"))

        # te form
        outrow.append(generate_japanese_verb_by_str(verb, vclass, "te"))

        # imperative form
        outrow.append(generate_japanese_verb_by_str(verb, vclass, "imp"))

        print(";".join(outrow))

        # # Non-past
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pla"))
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pla", "neg"))

        # # Non-past, polite
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pol"))
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pol", "neg"))

        # # Past
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pla", "past"))
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pla", "past", "neg"))

        # # Past, polite
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pol", "past"))
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pol", "past", "neg"))

        # # Te-form
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "te"))
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "te", "neg"))

        # # Te-polite
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pol", "te"))
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pol", "te", "neg"))

        # # Potential
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pot"))
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pot", "neg"))

        # # Passive
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pass"))
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "pass", "neg"))

        # # Causative
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "caus"))
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "caus", "neg"))

        # # Causative Passive

        # # Imperative
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "caus"))
        # outrow.append(generate_japanese_verb_by_str(verb, vclass, "caus", "neg"))

# Example usage
if len(sys.argv) < 2:
    print("Usage: python verb_conjugator.py <csv_file> >> output.txt")
    sys.exit(1)

csv_file = sys.argv[1]
conjugate(csv_file)