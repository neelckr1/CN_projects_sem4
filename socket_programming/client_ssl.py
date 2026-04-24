import socket
import ssl
import threading
import sys
import time

HOST = input("Enter server IP: ")
PORT = 5000
name = input("Enter your name: ")

context = ssl._create_unverified_context()
sock = socket.socket(socket.AF_INET)
conn = context.wrap_socket(sock, server_hostname=HOST)
conn.connect((HOST, PORT))
conn.sendall((name + "\n").encode())

buffer = ""
mode = "A"

current_item = ""
start_price = 0

# ---------------- Option A ----------------
current_round = 0
current_required_bid = 0
bid_prompt_open = False

# ---------------- Option B ----------------
private_stage_no = 0
private_required_bid = 0
private_prompt_open = False
private_active = True
private_waiting_bid_amount = False

# ---------------- Common client tracking ----------------
my_bids = {}
history = []
final_results = []
leader_rows = []
my_rank = None
my_wins = 0


def safe_print(text=""):
    sys.stdout.write("\r" + " " * 120 + "\r")
    print(text, flush=True)


def format_client_summary_table(rows):
    line = "=" * 108
    out = []
    out.append(line)
    out.append(" " * 34 + "YOUR AUCTION SUMMARY")
    out.append(line)
    out.append(
        f"{'Item':<14}{'Start':>10}{'YourBid':>12}{'Winner':>14}{'WinningBid':>14}{'Your Result':>30}"
    )
    out.append("-" * 108)

    for item, start, my_bid, winner, winning_bid, status_text in rows:
        my_bid_text = "-" if my_bid is None else str(my_bid)
        out.append(
            f"{item:<14}{start:>10}{my_bid_text:>12}{winner:>14}{winning_bid:>14}{status_text:>30}"
        )

    out.append("-" * 108)
    return "\n".join(out)


def format_leaderboard_table(rows):
    line = "=" * 56
    out = []
    out.append(line)
    out.append(" " * 18 + "FINAL LEADERBOARD")
    out.append(line)
    out.append(f"{'Rank':<10}{'Name':<20}{'Wins':<10}")
    out.append("-" * 56)
    for rank, bidder, wins in rows:
        out.append(f"{rank:<10}{bidder:<20}{wins:<10}")
    out.append("-" * 56)
    return "\n".join(out)


def compute_status_text(item, start, my_bid, winner, winning_bid):
    if winner == name:
        extra = winning_bid - start
        return f"WON, paid +{extra} extra"

    if winner == "No Winner":
        return "NO WINNER"

    if my_bid is None:
        return "NO BID"

    diff = winning_bid - my_bid
    return f"LOST by {diff}"


def add_result_row(item, start, winner, winning_bid):
    my_bid = my_bids.get(item)
    status_text = compute_status_text(item, start, my_bid, winner, winning_bid)
    final_results.append((item, start, my_bid, winner, winning_bid, status_text))


def receive_messages():
    global buffer, mode
    global current_item, start_price
    global current_round, current_required_bid, bid_prompt_open
    global private_stage_no, private_required_bid, private_prompt_open, private_active, private_waiting_bid_amount
    global my_rank, my_wins

    while True:
        try:
            data = conn.recv(4096).decode()
            if not data:
                break

            buffer += data

            while "\n" in buffer:
                msg, buffer = buffer.split("\n", 1)
                msg = msg.strip()

                if not msg:
                    continue

                parts = msg.split("|")
                tag = parts[0]

                if tag == "WELCOME":
                    safe_print("\n" + parts[1])

                elif tag == "MODE":
                    mode = parts[1]

                elif tag == "INFO":
                    safe_print(parts[1])

                elif tag == "ITEM":
                    current_item = parts[1]
                    start_price = int(parts[2])
                    private_active = True
                    private_prompt_open = False
                    private_waiting_bid_amount = False
                    safe_print("\n=================================")
                    safe_print(f"NEW ITEM: {current_item}")
                    safe_print(f"START PRICE: {start_price}")
                    safe_print("=================================")

                elif tag == "COUNTDOWN":
                    sys.stdout.write(f"\rAuction begins in {parts[1]} seconds ")
                    sys.stdout.flush()

                # ---------------- Option A ----------------
                elif tag == "START":
                    safe_print("\nAuction started.")

                elif tag == "ROUND":
                    current_round = int(parts[1])
                    current_required_bid = int(parts[2])
                    bid_prompt_open = True
                    safe_print(f"\nROUND {current_round} STARTED")
                    safe_print(f"Minimum valid bid: greater than {current_required_bid}")

                elif tag == "BID_OK":
                    bid_prompt_open = False
                    accepted_bid = int(parts[1])
                    my_bids[current_item] = accepted_bid
                    safe_print(f"Bid submitted successfully: {accepted_bid}")

                elif tag == "BID_REJECT":
                    bid_prompt_open = True
                    safe_print(parts[1])

                elif tag == "ROUND_SUMMARY":
                    bid_prompt_open = False
                    safe_print("\nROUND SUMMARY")

                elif tag == "SUMMARY":
                    safe_print(f"{parts[1]} : {parts[2]}")

                elif tag == "HISTORY":
                    history.append(parts[1:])

                # ---------------- Option B ----------------
                elif tag == "PRIVATE_START":
                    safe_print("\nPrivate bidding started.")

                elif tag == "PRIVATE_STAGE":
                    private_stage_no = int(parts[1])
                    private_required_bid = int(parts[2])

                    if private_active:
                        private_prompt_open = True
                        private_waiting_bid_amount = False
                        safe_print(f"\nPRIVATE STAGE {private_stage_no}")
                        safe_print(f"Current minimum required bid: greater than {private_required_bid}")

                elif tag == "PRIVATE_WAIT":
                    private_prompt_open = False
                    private_waiting_bid_amount = False
                    safe_print("\n" + parts[1])

                elif tag == "PRIVATE_OK":
                    private_prompt_open = False
                    private_waiting_bid_amount = False
                    accepted_bid = int(parts[1])
                    my_bids[current_item] = accepted_bid
                    safe_print(f"Bid submitted successfully: {accepted_bid}")

                elif tag == "PRIVATE_REJECT":
                    private_prompt_open = True
                    private_waiting_bid_amount = True
                    safe_print(parts[1])

                elif tag == "PRIVATE_SYNC":
                    private_required_bid = int(parts[1])
                    private_prompt_open = True
                    private_waiting_bid_amount = False
                    safe_print(f"\nCurrent highest bid updated to {private_required_bid}.")

                elif tag == "PRIVATE_WITHDRAWN":
                    private_prompt_open = False
                    private_waiting_bid_amount = False
                    private_active = False
                    safe_print(parts[1])

                elif tag == "PRIVATE_INFO":
                    safe_print(parts[1])

                elif tag == "LIVE":
                    safe_print("\n" + parts[1])

                # ---------------- Common item result ----------------
                elif tag == "RESULT":
                    bid_prompt_open = False
                    private_prompt_open = False
                    private_waiting_bid_amount = False

                    item = parts[1]
                    start = int(parts[2])
                    winner = parts[3]
                    winning_bid = int(parts[4])

                    if history:
                        safe_print("\n==============================")
                        safe_print("BID HISTORY")
                        safe_print("==============================")
                        for h in history:
                            safe_print(f"{h[0]} : {h[1]} -> {h[2]} -> {h[3]}")
                        history.clear()

                    add_result_row(item, start, winner, winning_bid)

                    if winner == name:
                        safe_print(f"\nCongratulations! You won the bid for {item} with {winning_bid}.")
                    elif winner == "No Winner":
                        safe_print(f"\nNo winner for {item}.")
                    else:
                        safe_print(f"\nResult for {item}: Winner is {winner} with {winning_bid}.")

                # ---------------- Final leaderboard / conclusion ----------------
                elif tag == "LEADER":
                    rank = int(parts[1])
                    bidder = parts[2]
                    wins = int(parts[3])
                    leader_rows.append((rank, bidder, wins))

                elif tag == "MYRANK":
                    my_rank = int(parts[1]) if parts[1] != "None" else None
                    my_wins = int(parts[2])

                elif tag == "END_ALL":
                    safe_print()
                    safe_print(format_client_summary_table(final_results))
                    safe_print()
                    safe_print(format_leaderboard_table(leader_rows))
                    if my_rank is not None:
                        safe_print(f"\nYour final rank today: {my_rank}")
                        safe_print(f"Your total wins today: {my_wins}")
                    safe_print("Thank you for participating!")

        except:
            break


def send_bids():
    global bid_prompt_open
    global private_prompt_open, private_active, private_waiting_bid_amount

    while True:
        # ---------------- Option A ----------------
        if mode == "A" and bid_prompt_open:
            try:
                bid = input(f"\nEnter your bid (greater than {current_required_bid}): ").strip()
            except EOFError:
                break

            if not bid_prompt_open:
                continue

            if not bid.isdigit():
                safe_print("Please enter numbers only.")
                continue

            bid_value = int(bid)
            conn.sendall(f"BID|{current_round}|{bid_value}\n".encode())
            continue

        # ---------------- Option B ----------------
        if mode == "B" and private_prompt_open and private_active:
            if not private_waiting_bid_amount:
                try:
                    ans = input(
                        f"\nCurrent highest is {private_required_bid}. "
                        f"Do you want to bid more? (yes/no): "
                    ).strip().lower()
                except EOFError:
                    break

                if not private_prompt_open:
                    continue

                if ans in ("no", "n"):
                    conn.sendall("PRIVATE|NO|0\n".encode())
                    continue

                if ans in ("yes", "y"):
                    private_waiting_bid_amount = True
                else:
                    safe_print("Please enter yes or no.")
                    continue

            try:
                bid = input(f"Enter your bid (greater than {private_required_bid}): ").strip()
            except EOFError:
                break

            if not private_prompt_open:
                continue

            if not bid.isdigit():
                safe_print("Please enter numbers only.")
                continue

            bid_value = int(bid)
            conn.sendall(f"PRIVATE|BID|{bid_value}\n".encode())
            continue

        time.sleep(0.1)


threading.Thread(target=receive_messages, daemon=True).start()
send_bids()