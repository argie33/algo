#!/usr/bin/env python3
"""
IBKR paper-trading order placer.
Auto-connects to IB Gateway, submits a single order, logs status, then disconnects.
"""

import os, sys, threading
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order

# ─── Configuration via ENV ────────────────────────────────────────────────── 
IB_HOST        = os.getenv("IBKR_HOST", "host.docker.internal")
IB_PORT        = int(os.getenv("IBKR_PORT", 4002))            # default Gateway paper 
IB_CLIENT_ID   = int(os.getenv("IBKR_CLIENT_ID", 1))
SYMBOL         = os.getenv("IBKR_SYMBOL", "AAPL")
EXCHANGE       = os.getenv("IBKR_EXCHANGE", "SMART")
CURRENCY       = os.getenv("IBKR_CURRENCY", "USD")
ACTION         = os.getenv("IBKR_ACTION", "BUY")             # BUY or SELL
QUANTITY       = float(os.getenv("IBKR_QUANTITY", "1"))      # shares
ORDER_TYPE     = os.getenv("IBKR_ORDER_TYPE", "MKT")         # MKT or LMT
LIMIT_PRICE    = float(os.getenv("IBKR_LIMIT_PRICE", "0"))   # required if ORDER_TYPE=LMT
TIMEOUT_SEC    = int(os.getenv("IBKR_TIMEOUT_SEC", "10"))    # how long before auto-disconnect

def make_stock_contract(symbol, exchange, currency):
    c = Contract()
    c.symbol = symbol
    c.secType = "STK"
    c.exchange = exchange
    c.currency = currency
    return c

def make_order(action, quantity, order_type, limit_price=None):
    o = Order()
    o.action = action
    o.totalQuantity = quantity
    o.orderType = order_type
    if order_type == "LMT":
        o.lmtPrice = limit_price
    return o

class TradeApp(EWrapper, EClient):
    def __init__(self, contract, order):
        EClient.__init__(self, self)
        self.contract = contract
        self.order    = order

    def error(self, reqId, errorCode, errorString):
        print(f"[ERROR] reqId={reqId} code={errorCode} msg={errorString}")

    def nextValidId(self, orderId):
        print(f"[OK] connected, nextValidOrderId={orderId}")
        print(f"[INFO] placing {self.order.action} {self.order.totalQuantity} {self.contract.symbol} @ {self.order.orderType}"
              + (f" limit {self.order.lmtPrice}" if self.order.orderType=="LMT" else ""))
        self.placeOrder(orderId, self.contract, self.order)
        # schedule auto-disconnect
        threading.Timer(TIMEOUT_SEC, self.disconnect).start()

    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, *args):
        print(f"[ORDER STATUS] id={orderId} status={status} filled={filled} remaining={remaining} avgFillPrice={avgFillPrice}")

    def openOrder(self, orderId, contract, order, orderState):
        print(f"[OPEN ORDER] id={orderId} symbol={contract.symbol} action={order.action} qty={order.totalQuantity} type={order.orderType}")

    def execDetails(self, reqId, contract, execution):
        print(f"[EXEC DETAILS] execId={execution.execId} shares={execution.shares} price={execution.price}")

def main():
    contract = make_stock_contract(SYMBOL, EXCHANGE, CURRENCY)
    order    = make_order(ACTION, QUANTITY, ORDER_TYPE, LIMIT_PRICE)

    app = TradeApp(contract, order)
    print(f"[INFO] connecting to {IB_HOST}:{IB_PORT} (clientId={IB_CLIENT_ID}) …")
    app.connect(IB_HOST, IB_PORT, IB_CLIENT_ID)
    app.run()

if __name__ == "__main__":
    main()
