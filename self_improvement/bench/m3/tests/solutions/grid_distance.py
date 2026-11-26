from collections import deque

def distance(grid, start, end):
    def open_cell(position):
        row, col = position
        return 0 <= row < len(grid) and 0 <= col < len(grid[0]) and grid[row][col] == "."

    if not open_cell(start) or not open_cell(end):
        return None
    queue = deque([(start, 0)])
    seen = {start}
    while queue:
        (row, col), moves = queue.popleft()
        if (row, col) == end:
            return moves
        for position in [(row-1,col),(row+1,col),(row,col-1),(row,col+1)]:
            if position not in seen and open_cell(position):
                seen.add(position)
                queue.append((position, moves + 1))
    return None
