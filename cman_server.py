import socket
import select
import time
import sys
from cman_game import Game, Player, Direction, State  # Assume game logic is in a separate file

# Constants
SERVER_PORT = 1337
SERVER_IP = '0.0.0.0'
TIMEOUT = 0.01  # Timeout for select, adjust as needed
MAX_ATTEMPTS = 3
WIN_SCORE = 32

# Game instance
game = None

server_socket = None  # Server socket for communication
# List of clients and their roles
clients = {}
roles = {0:Player.NONE, 1:Player.CMAN, 2:Player.SPIRIT}  # Keep track of CMAN and SPIRIT

spectators = []

def get_game_update(addr):
    """Get the game update message for a client."""
    cords = game.get_current_players_coords()
    c_coords = cords[Player.CMAN] if Player.CMAN in clients.values() else (0xFF, 0xFF)
    s_coords = cords[Player.SPIRIT] if Player.SPIRIT in clients.values() else (0xFF, 0xFF)
    # feeze is 0 if the player can send move requests, 1 otherwise
    freeze = (roles[clients[addr]] != Player.NONE) and game.can_move(clients[addr])
    points = game.get_points()

    # convert the points dict into bytes where each bit represents a point, 5 bytes for 40 points
    collected = [0] * 5
    # sort the points by their coordinates, lexigraphically
    i = 0
    for point in sorted(points.keys()):
        if points[point] == 0:
            collected[i//8] |= 1 << (i%8)
        i += 1
    
    lives, score = game.get_game_progress()
    attempts = MAX_ATTEMPTS - lives

    message = bytes([0x80, freeze, c_coords[0], c_coords[1], s_coords[0], s_coords[1], attempts] + collected)
    return message

def send_update_to_all():
    """Send a game update message to all clients."""
    for client_addr in clients.keys():
        send_message(client_addr, get_game_update(client_addr))

def send_message(client_addr, message):
    """Send a message to a client."""
    server_socket.sendto(message, client_addr)
    print(f"Sent message to {client_addr}")
    
def send_message_to_all(message):
    """Send a message to all clients."""
    for client_addr in clients:
        send_message(client_addr, message)

def handle_join_request(client_addr, role):
    """Handles a join request from a client."""
    if role in [0,1,2]:
        if role == 0:
            clients[client_addr] = roles[role]
            print(f"Client {client_addr} joined as {roles[role]}")
        if role == 1:
            if Player.CMAN in clients.values():
                # CMAN already taken, send error message
                #send_message(client_addr, get_game_update(client_addr))
                send_message(client_addr, bytes([0xFF, 0x03]))
            else:
                clients[client_addr] = roles[role]
                print(f"Client {client_addr} joined as {roles[role]}")
                send_update_to_all()
        if role == 2:
            if Player.SPIRIT in clients.values():
                # SPIRIT already taken, send error message
                #send_message(client_addr, get_game_update(client_addr))
                send_message(client_addr, bytes([0xFF, 0x04]))
            else:
                clients[client_addr] = roles[role]
                print(f"Client {client_addr} joined as {roles[role]}")
                send_update_to_all()
    else:
        # error message
        send_message(client_addr, bytes([0xFF, 0x05]))
        return
    # Send the game state update to the client

    
    

def handle_move_request(client_addr, direction):
    """Handle a move request from a client."""
    role = clients[client_addr]
  

    if game.state == State.WAIT:
        print("game is waiting")
        send_message(client_addr, bytes([0xFF, 0x00]))  # Error opcode, code 0x02 (waiting for players)
    elif game.state == State.START and roles[clients[client_addr]] == Player.SPIRIT:
        print("spirit cant move")
        send_message(client_addr, bytes([0xFF, 0x01]))
    
    elif game.apply_move(role, direction):
        print("applyed move")
        if game.state == State.START:
            game.state = State.PLAY
        send_update_to_all()
        return 
    else:
        # send error message
        send_message(client_addr, bytes([0xFF, 0x02]))  # Error opcode, code 0x01 (invalid move)
        print(f"invalid move by {client_addr}")
    
    
def handle_exit_request(client_addr):
    """Handles a client exit request."""
    if client_addr in clients:
        role = roles[clients[client_addr]]
        
        if role == Player.CMAN or role == Player.SPIRIT:
            if game.state == State.WAIT:
                clients.pop(client_addr)
                print(f"Client {client_addr} exited")
                send_update_to_all()
            else:
                game.declare_winner(Player.SPIRIT if role == Player.CMAN else Player.CMAN)
                print(f"Client {client_addr} exited, winner: {role}")

    else:
        send_message(client_addr, bytes([0xFF, 0x03]))  # Error opcode, code 0x03 (not in game)

def main():
    global game, server_socket, clients
    # UDP server socket setup
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    server_socket.bind((SERVER_IP, SERVER_PORT))
    server_socket.setblocking(False)  # Non-blocking mode
    # Initialize the game with the map file
    game = Game("map.txt")
    
    print("Server started, waiting for clients...")

    while True:
        # Use select to handle multiple clients without blocking
        previous_state = game.state
        readable, _, _ = select.select([server_socket], [], [], TIMEOUT)
        
        for sock in readable:
            if sock is server_socket:
                # Receive data from clients
                data, client_addr = server_socket.recvfrom(1024)
                if not data:
                    continue
                
                opcode = data[0]
                print(f"Received message with opcode {opcode} from {client_addr}")

                if opcode == 0x00:  # Join request
                    role = data[1]  # Role byte
                    print(f"Join request from {client_addr} with role {role}")
                    handle_join_request(client_addr, role)
                
                elif opcode == 0x01:  # Player move request
                    direction = Direction(data[1])  # Direction byte
                    handle_move_request(client_addr, direction)
                    
                
                elif opcode == 0x0F:  # Quit request
                    handle_exit_request(client_addr)
        
        if Player.CMAN in clients.values() and Player.SPIRIT in clients.values():
            # Start the game if both roles are taken
            if game.state == State.WAIT:
                game.state = State.START
                print("start the game")
        # Continue to check for clients and update the game state
        if game.state != previous_state:
            print("state changed")
            send_update_to_all()  # Game state update
        # If game ends
        if game.state == State.WIN:
            winner = game.get_winner()
            print(f"Game ended, winner: {winner}")
            c_score = MAX_ATTEMPTS - game.get_game_progress()[0]
            s_score = game.get_game_progress()[1]
            send_update_to_all()
            send_message_to_all(bytes([0x8F, winner, s_score, c_score]))  # Game end message
            time.sleep(10)  # Wait for a few seconds before restarting
            clients.clear()
            game.restart_game()  # Restart the game after a winner is declared

            send_message_to_all(bytes([0x80, 0x00]))  # Game restart

if __name__ == "__main__":
    # get port from args of given
    if len(sys.argv) > 1:
        SERVER_PORT = int(sys.argv[1])
    
    main()