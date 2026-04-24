# Socket Programming - Auction System

This is a simple auction program that lets multiple people connect and bid on items using Python.

## What You Need

- Python 3
- pyOpenSSL (install with: `pip install pyOpenSSL`)

## How to Run

### Step 1: Create the certificates

```bash
python generate_cert.py
```

### Step 2: Start the server

Open a terminal and run:

```bash
python server_ssl.py
```

### Step 3: Start a client

Open another terminal and run:

```bash
python client_ssl.py
```

Enter the server IP address (like `127.0.0.1`) and your name.

### Step 4: Add more players

Open more terminals and repeat Step 3 to add more players.

## Files

- `server_ssl.py` - The auction server
- `client_ssl.py` - The auction player
- `generate_cert.py` - Creates security certificates

## How It Works

- The server runs and waits for players to join
- Each player connects with their name
- Players can bid on items
- The server keeps track of bids and winners
