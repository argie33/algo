#!/usr/bin/env python3
"""
Basic IBKR connectivity test using the official Python API.
Attempts to connect to TWS/IBG and prints the next valid order ID on success.
"""

import os
import sys
from ibapi.client import EClient
from ibapi.wrapper import EWrapper

# Read connection parameters from env (with sensible defaults)
IB_HOST      = os.getenv("IBKR_HOST", "host.docker.internal")
IB_PORT      = int(os.getenv("IBKR_PORT", 7497))
IB_CLIENT_ID = int(os.getenv("IBKR_CLIENT_ID", 1))

class IBTestApp(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)

    def error(self, reqId, errorCode, errorString):
        print(f"[ERROR] reqId={reqId} code={errorCode} msg={errorString}")

    def nextValidId(self, orderId):
        print(f"[OK] Connected! NextValidOrderId = {orderId}")
        # cleanly disconnect once we’ve confirmed connectivity
        self.disconnect()

def main():
    app = IBTestApp()
    print(f"Connecting to IBKR at {IB_HOST}:{IB_PORT} (clientId={IB_CLIENT_ID})…")
    try:
        app.connect(IB_HOST, IB_PORT, IB_CLIENT_ID)
    except Exception as e:
        print(f"[EXCEPTION] Failed to connect: {e}")
        sys.exit(1)
    # enters the message loop until disconnect()
    app.run()

if __name__ == "__main__":
    main()
