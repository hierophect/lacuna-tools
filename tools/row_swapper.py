import csv
import sys

def swap_columns(csv_file):
    with open(csv_file, 'r') as file:
        reader = csv.reader(file,delimiter=';')
        data = list(reader)

    num_columns = len(data[0])
    swap_positions = []

    print(f"The CSV file has {num_columns} columns.")
    print("Enter the new position (0-indexed) for each column:")

    for i in range(num_columns):
        new_position = int(input(f"Enter the new position for column {i + 1}: "))
        swap_positions.append(new_position)

    new_data = []

    for row in data:
        new_row = []
        for i in range(num_columns):
            new_row.append(row[swap_positions[i]-1])
        new_data.append(new_row)

    with open('swapped.csv', 'w', newline='') as file:
        writer = csv.writer(file,delimiter=';')
        writer.writerows(new_data)

    print("Column swapping complete. Swapped data saved in 'swapped.csv'.")

# Example usage
if len(sys.argv) < 2:
    print("Usage: python column_swap.py <csv_file>")
    sys.exit(1)

csv_file = sys.argv[1]
swap_columns(csv_file)