import csv
import sys

def do_something(csv_file):
    with open(csv_file, 'r') as file:
        reader = csv.reader(file,delimiter=';')
        data = list(reader)
    num_rows = len(data)
    num_columns = len(data[0])

    # Do stuff with the data[] list and number of columns

    # if data has been modified, it can be output to a new file.
    outdata = None
    with open('output.csv', 'w', newline='') as file:
        writer = csv.writer(file,delimiter=';')
        writer.writerows(outdata)
    print("Output saved.")

# Example usage
if len(sys.argv) < 2:
    print("Usage: python generic.py <csv_file>")
    sys.exit(1)

csv_file = sys.argv[1]
do_something(csv_file)