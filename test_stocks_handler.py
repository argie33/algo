import sys

sys.path.insert(0, 'lambda/api')

# Test the stocks handler
try:
    from api_utils.database_context import DatabaseContext
    from routes.stocks import handle

    with DatabaseContext() as cur:
        result = handle(cur, '/api/stocks', 'GET', {}, None, None)
        print(f'Result type: {type(result).__name__}')
        status = result.get('statusCode')
        print(f'Result statusCode: {status}')
        if 'errorType' in result:
            print(f'Error: {result.get("errorType")} - {result.get("message")}')
        else:
            print(f'Success - data keys: {list(result.get("data", {}).keys()) if result.get("data") else "no data"}')
except Exception as e:
    print(f'Exception: {type(e).__name__}: {e}')
    import traceback
    traceback.print_exc()
