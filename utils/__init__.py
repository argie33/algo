#!/usr/bin/env python3
# utils package — import from submodules directly, e.g.:
#   from utils.db.context import DatabaseContext
#   #   from utils.error_handlers import make_error_response
#
# Do NOT add eager imports here. Any import from utils.* triggers this file,
# so eagerly importing heavy submodules (utils.db, signals, loaders) causes
# them to load in every context — including the API Lambda — even when unused.
# That was the root cause of "No module named algo" crashing the entire API.
