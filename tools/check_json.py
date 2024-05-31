# really simple checker just to make sure character encoding in json will work

import sys
import json

def do_something(json_file):
    with open(json_file, 'r') as f:
        data = json.load(f)

    for parsed_category in data["categories"]:
        print("in category: " + parsed_category["name"])
        for parsed_selectable in parsed_category["selectables"]:
            for count, parsed_variant in enumerate(parsed_selectable["variants"]):
                print(parsed_variant)
                return

# Example usage
if len(sys.argv) < 2:
    print("Usage: python generic.py <json_file>")
    sys.exit(1)

json_file = sys.argv[1]
do_something(json_file)