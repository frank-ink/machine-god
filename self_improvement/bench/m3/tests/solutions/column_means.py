import csv
from io import StringIO
from statistics import mean

def column_means(csv_text):
    reader = csv.reader(StringIO(csv_text))
    columns = {name: [] for name in next(reader)}
    for row in reader:
        for name, cell in zip(columns, row):
            if cell.strip():
                columns[name].append(float(cell))
    return {name: mean(values) if values else None for name, values in columns.items()}
