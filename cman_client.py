import socket
import time
import sys
import select
from cman_utils import get_pressed_keys, clear_print, _flush_input  # Importing utils functions
from cman_game import Game, Player, Direction  # Assuming these classes are defined in game_logic.py
from cman_game_map import read_map  # Importing read_map function from game_map.py
# Constants
TIMEOUT = 0.01
SERVER_PORT = 1337
POINT_CHAR = 'P'
FREE_CHAR = 'F'
CMAN_CHAR = 'C'
SPIRIT_CHAR = 'S'
WALL_CHAR = 'W'

# Client socket setup
client_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Global variables
role = None  # Player's role in the game
game_active = True  # Game status

def send_message(message):
    """Send a message to the server."""
    client_socket.sendto(message, (addr, SERVER_PORT))

def handle_join(role):
    """Send a join request to the server."""
    message = bytes([0x00, role])  # 0x00 is the JOIN opcode, role is the second byte
    send_message(message)

def handle_move(direction):
    """Send a player movement request to the server."""
    message = bytes([0x01, direction.value])  # 0x01 is the MOVE opcode, direction is the second byte
    send_message(message)

def handle_quit():
    """Send a quit request to the server."""
    message = bytes([0x0F])  # 0x0F is the QUIT opcode
    send_message(message)

def update_and_print_map(map_data, points, freeze, c_coords, s_coords, attempts, collected):
    """
    Updates the map with the current game state and prints it.

    Parameters:
    - map_data (list[str]): Original map lines
    - freeze (int): Freeze status (0: not frozen, 1: frozen)
    - c_coords (tuple): Coordinates of Cman (row, col) or None if not active
    - s_coords (tuple): Coordinates of Spirit (row, col) or None if not active
    - attempts (int): Number of times Cman was caught by Spirit
    - collected (list[int]): 40-bit list of collected points (1: collected, 0: not collected)
    """
    # Copy the map to update without modifying the original
    updated_map = [list(line) for line in map_data]
    # Update collected points
    rows, cols = len(updated_map), len(updated_map[0])
    
    for r in range(rows):
        for c in range(cols):
            if updated_map[r][c] in {CMAN_CHAR, SPIRIT_CHAR}:
                updated_map[r][c] = FREE_CHAR

    
    for i, point in enumerate(sorted(points.keys())):
        if collected[i] == 1:
            updated_map[point[0]][point[1]] = ' '
    
    # Update player positions
    if c_coords != (0xFF, 0xFF):  # Check if Cman is active
        updated_map[c_coords[0]][c_coords[1]] = CMAN_CHAR

    if s_coords != (0xFF, 0xFF):  # Check if Spirit is active
        updated_map[s_coords[0]][s_coords[1]] = SPIRIT_CHAR

    # replace free space with ' '
    for i in range(len(updated_map)):
        updated_map[i] = [x if x != FREE_CHAR else ' ' for x in updated_map[i]]
        updated_map[i] = [x if x != WALL_CHAR else '#' for x in updated_map[i]]
        updated_map[i] = [x if x != POINT_CHAR else 'o' for x in updated_map[i]]
        
  
    
    # Print the updated map
    clear_print(" ")
    print("Game Map:")
    print("+" + "-" * (cols * 2 - 1) + "+")
    for row in updated_map:
        print("| " + " ".join(row) + " |")
    print("+" + "-" * (cols * 2 - 1) + "+")
    
    # Print the game status
    print("\nGame Status:")
    if c_coords == (0xFF, 0xFF) or s_coords == (0xFF, 0xFF):
        print("  Waiting for another player.")
    print(f"  You are playing as: {role}")
    print(f"  Freeze: {'Yes' if freeze else 'No'}")
    print(f"  Cman Caught Attempts: {attempts}")
    remaining_points = collected.count(0)
    print(f"  Remaining Points: {remaining_points}")
    print(f"  CMAN has {len(points) - remaining_points} points.\n")


def main():
    global role, game_active
    roles_dict = {'cman': 1, 'spirit': 2, 'watcher': 0}
    map_data = read_map('map.txt').split('\n')
    points = Game('map.txt').get_points()
    if role in roles_dict.keys():
        handle_join(roles_dict[role])  # Send join request
    else:
        print(f"Invalid role: {role}")
        exit(1)
    # Wait for server response
    while True:
        # Prepare the list of file descriptors to watch (socket and stdin)
        
        rlist, _, _ = select.select([client_socket], [], [], TIMEOUT)  # 1 second timeout
        
        for ready in rlist:
            if ready == client_socket:
                # Receive a message from the server
                data, addr = client_socket.recvfrom(1024)
                if addr != (addr_server, SERVER_PORT):
                    print(f"Received message from unknown address {addr}. Ignoring.")
                    continue
                opcode = data[0]
                #print(f"Received message with opcode {opcode}")
                
                # Handle game state update
                if opcode == 0x80:  # Game state update (0x80)
                    freeze = data[1]
                    c_coords = (data[2], data[3])
                    s_coords = (data[4], data[5])
                    attempts = data[6]
                    # unpack 5 bytes of collected to a list of 40 ints
                    collected = []
                    for i in range(7, 12):
                        byte = data[i]
                        for j in range(8):
                            collected.append((byte >> j) & 1)
                    
                    update_and_print_map(map_data, points, freeze, c_coords, s_coords, attempts, collected)
                    break
                    
                elif opcode == 0x8F:  # Game end (0x8F)
                    winner = "CMAN" if data[1] == 1 else "Spirit"
                    print(f"Game Over! The winner is {winner}")
                    print(f"CMAN Score: {data[2]}")
                    print(f"Spirit Score: {data[3]}")
                    exit(0)
                    break
              
                elif opcode == 0xFF:
                    error_code = data[1]
                    if error_code == 0x00:
                        print("waiting for players")
                    elif error_code == 0x01:
                        print("Spirit cannot move yet, CMAN has to move first.")
                    elif error_code == 0x03:
                        print("CMAN already taken.")
                        exit(1)
                    elif error_code == 0x04:
                        print("Spirit already taken.")
                        exit(1)
                    elif error_code == 0x05:
                        print("Invalid role.")                        
                        exit(1)
                        
            
        keys = get_pressed_keys()

        if keys != []:
            if 'q' in keys:
                print("Quitting game.")
                handle_quit()
                exit(0)
            if role != 'watcher':
                if 'w' in keys:
                    handle_move(Direction.UP)
                elif 'a' in keys:
                    handle_move(Direction.LEFT)
                elif 's' in keys:
                    handle_move(Direction.DOWN)
                elif 'd' in keys:
                    handle_move(Direction.RIGHT)
            else:
                print("Watcher cannot move.")    

    print("Game ended. Closing client.")

if __name__ == "__main__":
    # get args from command line
    try :
        role = sys.argv[1]
        addr_server = sys.argv[2]
    except ValueError:
        print("Invalid command line arguments. Exiting.")
        sys.exit(1)
    
    if role not in ['cman', 'spirit', 'watcher']:
        print("Invalid role. Exiting.")
        sys.exit(1)
    
    if len(sys.argv) > 3:
        try :
            SERVER_PORT = int(sys.argv[3])
        except ValueError:
            print("Invalid port. Exiting.")
            sys.exit(1)
    main()
