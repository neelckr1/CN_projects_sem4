import socket
import ssl
import threading
import time
import sys

HOST = "0.0.0.0"
PORT = 5000

COUNTDOWN = 10
ROUND_TIME = 40
ROUNDS = 3

clients = []
names = {}
items = []
choice = ""

leaderboard = {}
auction_results = []

# ---------------- Option A: Government Auction ----------------
bids = {}                  # {name: {round_no: bid}}
client_bid_done = {}       # {name: bool}
round_submit_order = {}    # {name: order_number}
current_required_bid = 0

# ---------------- Option B: Private Auction ----------------
private_active = {}            # {name: bool}
private_stage_responded = {}   # {name: bool}
private_current_highest = 0
private_current_winner = None
private_stage_no = 0
private_item_running = False

lock = threading.Lock()


def send_line(conn, msg):
    try:
        conn.sendall((msg + "\n").encode())
    except:
        pass


def get_conn_by_name(target_name):
    for conn, name in names.items():
        if name == target_name:
            return conn
    return None


def broadcast(msg):
    dead = []
    for conn in clients:
        try:
            conn.sendall((msg + "\n").encode())
        except:
            dead.append(conn)

    for conn in dead:
        try:
            clients.remove(conn)
        except:
            pass
        left_name = names.pop(conn, None)
        if left_name is not None:
            client_bid_done.pop(left_name, None)
            private_active.pop(left_name, None)
            private_stage_responded.pop(left_name, None)


def format_server_summary_table(rows):
    line = "=" * 76
    out = []
    out.append(line)
    out.append(" " * 24 + "COMPLETE AUCTION SUMMARY")
    out.append(line)
    out.append(f"{'Item':<15}{'Start':>10}{'Winner':>15}{'WinningBid':>15}{'Profit':>12}")
    out.append("-" * 76)
    for item, start_price, winner, winning_bid, profit in rows:
        out.append(f"{item:<15}{start_price:>10}{winner:>15}{winning_bid:>15}{profit:>12}")
    out.append("-" * 76)
    return "\n".join(out)


def build_leaderboard_data():
    sorted_board = sorted(leaderboard.items(), key=lambda x: (-x[1], x[0].lower()))
    result = []
    rank = 1
    for name, wins in sorted_board:
        result.append((rank, name, wins))
        rank += 1
    return result


def format_server_leaderboard():
    board = build_leaderboard_data()
    line = "=" * 56
    out = []
    out.append(line)
    out.append(" " * 18 + "FINAL LEADERBOARD")
    out.append(line)
    out.append(f"{'Rank':<10}{'Name':<20}{'Wins':<10}")
    out.append("-" * 56)
    for rank, name, wins in board:
        out.append(f"{rank:<10}{name:<20}{wins:<10}")
    out.append("-" * 56)
    return "\n".join(out)


def client_rank_of(name):
    for rank, bidder, wins in build_leaderboard_data():
        if bidder == name:
            return rank, wins
    return None, 0


def send_final_reports_to_clients():
    board = build_leaderboard_data()

    for rank, bidder, wins in board:
        broadcast(f"LEADER|{rank}|{bidder}|{wins}")

    for conn, bidder in list(names.items()):
        rank, wins = client_rank_of(bidder)
        send_line(conn, f"MYRANK|{rank}|{wins}")

    broadcast("END_ALL")


def accept_clients(server, context):
    while True:
        client_socket, _ = server.accept()
        try:
            conn = context.wrap_socket(client_socket, server_side=True)
            threading.Thread(target=handle_client, args=(conn,), daemon=True).start()
        except:
            try:
                client_socket.close()
            except:
                pass


def start_server():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain("server_cert.pem", "server_key.pem")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(10)

    print("\nServer started. Waiting for clients...")
    threading.Thread(target=accept_clients, args=(server, context), daemon=True).start()


def print_countdown(prefix, seconds):
    for i in range(seconds, 0, -1):
        sys.stdout.write(f"\r{prefix}{i} seconds ")
        sys.stdout.flush()
        broadcast(f"COUNTDOWN|{i}")
        time.sleep(1)
    print()


def get_round_highest(round_no, fallback_value):
    highest_bid = fallback_value
    winner = None
    winner_order = None

    with lock:
        for bidder in bids:
            if round_no in bids[bidder]:
                value = bids[bidder][round_no]
                order = round_submit_order.get(bidder, 10**9)

                if value > highest_bid:
                    highest_bid = value
                    winner = bidder
                    winner_order = order
                elif value == highest_bid:
                    if winner is None or order < winner_order:
                        winner = bidder
                        winner_order = order

    return highest_bid, winner


def private_active_count():
    with lock:
        return sum(1 for v in private_active.values() if v)


def private_everyone_responded():
    with lock:
        active_names = [n for n in private_active if private_active[n]]
        if not active_names:
            return True
        return all(private_stage_responded.get(n, False) for n in active_names)


def send_private_stage(stage_no, required_bid, exclude_bidder=None):
    with lock:
        active_names = [n for n in private_active if private_active[n]]

    for bidder in active_names:
        conn = get_conn_by_name(bidder)
        if conn is None:
            continue

        if exclude_bidder is not None and bidder == exclude_bidder:
            send_line(conn, f"PRIVATE_WAIT|You are currently the highest bidder at {required_bid}. Waiting for others...")
        else:
            send_line(conn, f"PRIVATE_STAGE|{stage_no}|{required_bid}")


def handle_client(conn):
    global choice, current_required_bid
    global private_current_highest, private_current_winner, private_stage_no

    buffer = ""
    name = ""

    try:
        while "\n" not in buffer:
            data = conn.recv(1024).decode()
            if not data:
                return
            buffer += data

        name, buffer = buffer.split("\n", 1)
        name = name.strip()

        if not name:
            return

        with lock:
            names[conn] = name
            clients.append(conn)
            client_bid_done[name] = False
            private_active[name] = True
            private_stage_responded[name] = False
            leaderboard.setdefault(name, 0)

        print(f"\nClient connected: {name}")

        send_line(conn, "WELCOME|Welcome to the Auction System!")
        send_line(conn, f"MODE|{choice}")
        send_line(conn, "INFO|Items in today's auction:")
        for item_name, price in items:
            send_line(conn, f"INFO|- {item_name} (Starting price {price})")
        send_line(conn, "INFO|Waiting for server to start the auction...")

        while True:
            if "\n" not in buffer:
                data = conn.recv(1024).decode()
                if not data:
                    break
                buffer += data
                continue

            msg, buffer = buffer.split("\n", 1)
            msg = msg.strip()
            if not msg:
                continue

            # ---------------- Option A ----------------
            if choice == "A":
                if msg.startswith("BID|"):
                    parts = msg.split("|")
                    if len(parts) != 3:
                        continue

                    try:
                        round_no = int(parts[1])
                        bid_value = int(parts[2])
                    except:
                        continue

                    with lock:
                        if name not in client_bid_done:
                            continue

                        if client_bid_done[name]:
                            send_line(conn, "BID_REJECT|You have already submitted for this round.")
                            continue

                        if bid_value <= current_required_bid:
                            send_line(conn, f"BID_REJECT|Bid too low. Enter an amount greater than {current_required_bid}.")
                            continue

                        bids.setdefault(name, {})[round_no] = bid_value
                        client_bid_done[name] = True
                        round_submit_order[name] = len(round_submit_order) + 1

                    send_line(conn, f"BID_OK|{bid_value}")
                    print(f"Round {round_no} -> {name}: {bid_value}")

            # ---------------- Option B ----------------
            elif choice == "B":
                if msg.startswith("PRIVATE|"):
                    parts = msg.split("|", 2)
                    if len(parts) < 2:
                        continue

                    action = parts[1]

                    with lock:
                        if not private_item_running:
                            continue

                        if not private_active.get(name, False):
                            send_line(conn, "PRIVATE_INFO|You have already withdrawn from this item.")
                            continue

                        stage_snapshot = private_stage_no

                        if private_stage_responded.get(name, False):
                            send_line(conn, "PRIVATE_INFO|You have already responded for this stage.")
                            continue

                    if action == "NO":
                        with lock:
                            if stage_snapshot != private_stage_no:
                                send_line(conn, f"PRIVATE_SYNC|{private_current_highest}")
                                continue

                            private_active[name] = False
                            private_stage_responded[name] = True

                        send_line(conn, "PRIVATE_WITHDRAWN|You have withdrawn from this item.")
                        print(f"{name} withdrew from bidding.")

                    elif action == "BID":
                        if len(parts) < 3:
                            send_line(conn, f"PRIVATE_REJECT|Invalid bid. Enter an amount greater than {private_current_highest}.")
                            continue

                        try:
                            bid_value = int(parts[2])
                        except:
                            send_line(conn, f"PRIVATE_REJECT|Invalid bid. Enter an amount greater than {private_current_highest}.")
                            continue

                        with lock:
                            if stage_snapshot != private_stage_no:
                                send_line(conn, f"PRIVATE_SYNC|{private_current_highest}")
                                continue

                            if bid_value <= private_current_highest:
                                send_line(conn, f"PRIVATE_REJECT|Invalid bid. Enter an amount greater than {private_current_highest}.")
                                continue

                            private_current_highest = bid_value
                            private_current_winner = name

                            for bidder in private_active:
                                if not private_active[bidder]:
                                    private_stage_responded[bidder] = True
                                elif bidder == name:
                                    private_stage_responded[bidder] = True
                                else:
                                    private_stage_responded[bidder] = False

                            private_stage_no += 1
                            next_stage = private_stage_no
                            latest_highest = private_current_highest

                        send_line(conn, f"PRIVATE_OK|{bid_value}")
                        broadcast(f"LIVE|New highest bid {bid_value} by {name}")
                        send_private_stage(next_stage, latest_highest, exclude_bidder=name)
                        print(f"New highest bid {bid_value} by {name}")

    except:
        pass

    finally:
        with lock:
            if conn in clients:
                clients.remove(conn)
            left_name = names.pop(conn, None)
            if left_name is not None:
                client_bid_done.pop(left_name, None)
                private_active.pop(left_name, None)
                private_stage_responded.pop(left_name, None)

        try:
            conn.close()
        except:
            pass


# ==================== OPTION A ====================

def run_government_auction():
    global bids, current_required_bid, round_submit_order

    for item, start_price in items:
        while True:
            ans = input(f"\nStart auction for '{item}' at starting price {start_price}? (yes/no): ").strip().lower()
            if ans in ("yes", "y"):
                break
            elif ans in ("no", "n"):
                print("Auction not started yet. Type yes when ready.")
            else:
                print("Please enter yes or no.")

        print("\n=================================")
        print("      GOVERNMENT AUCTION")
        print("=================================")
        print(f"Item: {item}")
        print(f"Starting Price: {start_price}")

        with lock:
            bids = {name: {} for name in names.values()}
            for bidder in list(client_bid_done.keys()):
                client_bid_done[bidder] = False

        broadcast(f"ITEM|{item}|{start_price}")

        print("\nAuction Countdown:")
        print_countdown("Auction begins in ", COUNTDOWN)

        print("Auction Started!")
        broadcast("START")

        previous_round_highest = start_price
        final_winner = None
        final_highest = start_price

        for round_no in range(1, ROUNDS + 1):
            with lock:
                round_submit_order = {}
                current_required_bid = previous_round_highest
                for bidder in list(client_bid_done.keys()):
                    client_bid_done[bidder] = False

            print(f"\nROUND {round_no} STARTED")
            print(f"Minimum valid bid: greater than {current_required_bid}")
            broadcast(f"ROUND|{round_no}|{current_required_bid}")

            start_time = time.time()
            while time.time() - start_time < ROUND_TIME:
                left = int(ROUND_TIME - (time.time() - start_time))
                sys.stdout.write(f"\rTime left in Round {round_no}: {left:2d} sec ")
                sys.stdout.flush()

                with lock:
                    everyone_done = bool(client_bid_done) and all(client_bid_done.values())

                if everyone_done:
                    break

                time.sleep(1)
            print()

            round_highest, round_winner = get_round_highest(round_no, previous_round_highest)

            print(f"\nROUND {round_no} SUMMARY")
            broadcast(f"ROUND_SUMMARY|{round_no}")

            with lock:
                for bidder in bids:
                    value = bids[bidder].get(round_no, "No Bid")
                    print(f"{bidder} : {value}")
                    broadcast(f"SUMMARY|{bidder}|{value}")

            if round_highest > previous_round_highest:
                previous_round_highest = round_highest
                final_highest = round_highest
                final_winner = round_winner

        winner_text = final_winner if final_winner else "No Winner"
        profit = final_highest - start_price if final_winner else 0

        if final_winner:
            leaderboard[final_winner] = leaderboard.get(final_winner, 0) + 1

        auction_results.append((item, start_price, winner_text, final_highest, profit))

        with lock:
            for bidder in bids:
                history = [str(bids[bidder].get(i, "-")) for i in range(1, ROUNDS + 1)]
                broadcast("HISTORY|" + bidder + "|" + "|".join(history))

        broadcast(f"RESULT|{item}|{start_price}|{winner_text}|{final_highest}")
        print(f"\nWinner: {winner_text} with {final_highest}")

    print()
    print(format_server_summary_table(auction_results))
    print()
    print(format_server_leaderboard())
    send_final_reports_to_clients()


# ==================== OPTION B ====================

def run_private_auction():
    global private_current_highest, private_current_winner, private_stage_no, private_item_running

    for item, start_price in items:
        while True:
            ans = input(f"\nStart auction for '{item}' at starting price {start_price}? (yes/no): ").strip().lower()
            if ans in ("yes", "y"):
                break
            elif ans in ("no", "n"):
                print("Auction not started yet. Type yes when ready.")
            else:
                print("Please enter yes or no.")

        print("\n=================================")
        print("        PRIVATE AUCTION")
        print("=================================")
        print(f"Item: {item}")
        print(f"Starting Price: {start_price}")

        with lock:
            private_current_highest = start_price
            private_current_winner = None
            private_stage_no = 1
            private_item_running = True

            for bidder in list(names.values()):
                private_active[bidder] = True
                private_stage_responded[bidder] = False

        broadcast(f"ITEM|{item}|{start_price}")

        print("\nAuction Countdown:")
        print_countdown("Auction begins in ", COUNTDOWN)

        print("Private bidding started!")
        broadcast("PRIVATE_START")
        send_private_stage(1, start_price)

        while True:
            time.sleep(0.2)

            remaining = private_active_count()

            if remaining == 0:
                winner_text = "No Winner"
                winning_bid = start_price
                profit = 0
                auction_results.append((item, start_price, winner_text, winning_bid, profit))
                broadcast(f"RESULT|{item}|{start_price}|{winner_text}|{winning_bid}")
                print(f"\nAuction ended for {item}. Winner: No Winner with bid {winning_bid}")
                break

            if remaining == 1:
                with lock:
                    last_active = None
                    for bidder in private_active:
                        if private_active[bidder]:
                            last_active = bidder
                            break

                    if private_current_winner is None:
                        private_current_winner = last_active

                    winner_text = private_current_winner if private_current_winner else "No Winner"
                    winning_bid = private_current_highest

                profit = winning_bid - start_price if winner_text != "No Winner" else 0

                if winner_text != "No Winner":
                    leaderboard[winner_text] = leaderboard.get(winner_text, 0) + 1

                auction_results.append((item, start_price, winner_text, winning_bid, profit))
                broadcast(f"RESULT|{item}|{start_price}|{winner_text}|{winning_bid}")
                print(f"\nAuction ended for {item}. Winner: {winner_text} with bid {winning_bid}")
                break

            if private_everyone_responded():
                with lock:
                    for bidder in private_active:
                        if private_active[bidder]:
                            private_stage_responded[bidder] = False
                        else:
                            private_stage_responded[bidder] = True

                    private_stage_no += 1
                    stage = private_stage_no
                    required = private_current_highest

                send_private_stage(stage, required)

        with lock:
            private_item_running = False

    print()
    print(format_server_summary_table(auction_results))
    print()
    print(format_server_leaderboard())
    send_final_reports_to_clients()


def main():
    global choice

    print("ONLINE AUCTION ENGINE")
    print("A. Government Auction")
    print("B. Private Auction")
    choice = input("Enter choice: ").strip().upper()

    if choice not in ("A", "B"):
        print("Invalid choice")
        return

    try:
        n = int(input("Number of items: "))
    except:
        print("Invalid number of items")
        return

    for _ in range(n):
        item_name = input("Item name: ").strip()
        try:
            price = int(input("Starting price: ").strip())
        except:
            print("Invalid starting price")
            return
        items.append((item_name, price))

    start_server()
    input("\nPress ENTER when all clients connected...")
    print("\nStarting Auction...")

    if choice == "A":
        run_government_auction()
    else:
        run_private_auction()


if __name__ == "__main__":
    main()