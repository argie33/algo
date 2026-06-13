"""Config handlers - get, update, reset configuration keys."""
import logging
import sys
from pathlib import Path
from typing import Dict

_routes_dir = str(Path(__file__).parent.parent)
if _routes_dir not in sys.path:
    sys.path.insert(0, _routes_dir)

from algo_original import (
    _get_algo_config, _get_algo_config_key, _update_algo_config_key,
    _reset_algo_config_key
)
from routes.utils import error_response

logger = logging.getLogger(__name__)

handle_get_config = _get_algo_config


def handle_config_key(cur, key: str, method: str, body: Dict, actor: str) -> Dict:
    """Handle individual config key operations (GET/PUT/DELETE)."""
    if method == 'GET':
        return _get_algo_config_key(cur, key)
    elif method == 'PUT':
        return _update_algo_config_key(cur, key, body, actor)
    elif method == 'DELETE':
        return _reset_algo_config_key(cur, key, actor)
    else:
        return error_response(405, 'method_not_allowed', f'Method {method} not allowed for config key')


__all__ = ['handle_get_config', 'handle_config_key']
