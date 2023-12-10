import csv
import sys

def cut_columns(csv_file):
    with open(csv_file, 'r') as file:
        reader = csv.reader(file,delimiter=';')
        data = list(reader)

    num_columns = len(data[0])
    swap_positions = []

    print(f"The CSV file has {num_columns} columns.")
    max_columns = int(input(f"Enter the number of columns to keep: "))

    for i in range(len(data)):
        data[i] = data[i][:max_columns]

    with open('cut.csv', 'w', newline='') as file:
        writer = csv.writer(file,delimiter=';')
        writer.writerows(data)

    print("Column cutting complete. Cut data saved in 'cut.csv'.")

# Example usage
if len(sys.argv) < 2:
    print("Usage: python truncator.py <csv_file>")
    sys.exit(1)

csv_file = sys.argv[1]
cut_columns(csv_file)