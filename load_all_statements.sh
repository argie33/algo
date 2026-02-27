#!/bin/bash
export PGPASSWORD=bed0elAn
python3 loadannualincomestatement.py 2>&1 | tail -30
python3 loadannualbalancesheet.py 2>&1 | tail -30  
python3 loadannualcashflow.py 2>&1 | tail -30
python3 loadearningshistory.py 2>&1 | tail -30
