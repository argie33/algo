# Local Development Setup

Run the complete stock analytics platform locally with Docker Compose.

## Quick Start

```bash
# 1. Copy environment template
cp .env.local.example .env.local

# 2. Start all services
docker-compose up -d

# 3. Wait for services to be ready (~15 seconds)
docker-compose ps

# 4. Run a loader
python3 loadstocksymbols.py

# 5. View database (optional)
# Open http://localhost:5050 in browser
# Server: postgres
# Username: stocks
# Password: stocks_local_password
```

## What's Running

| Service | Port | Purpose |
|---------|------|---------|
| PostgreSQL | 5432 | Main database (TimescaleDB-enabled) |
| LocalStack | 4566 | AWS S3, Secrets Manager, CloudWatch |
| pgAdmin | 5050 | Database GUI inspection |

## Services Status

```bash
docker-compose ps

# Should show all 3 services as "healthy" or "running"
```

## Stop Everything

```bash
docker-compose down

# Keep data
docker-compose down --volumes

# Remove all data
docker-compose down -v
```

## Database Management

### Connect to PostgreSQL

```bash
# Via psql
psql -h localhost -U stocks -d stocks

# Password: stocks_local_password
```

### Reset Database

```bash
# Remove all data and restart
docker-compose restart postgres

# Or nuke it
docker-compose down -v
docker-compose up postgres
```

### Check Database Size

```bash
psql -h localhost -U stocks -d stocks -c "SELECT pg_size_pretty(pg_database_size('stocks'));"
```

## Running Loaders Locally

All loaders work the same as in AWS:

```bash
# Run a single loader
python3 loadpricedaily.py

# Run with specific symbols
python3 loadpricedaily.py --symbols AAPL,MSFT,GOOGL

# Run with parallelism
python3 loadpricedaily.py --parallelism 4

# Backfill 30 days of history
python3 loadpricedaily.py --backfill 30
```

## Environment Variables

**Development** (LocalStack):
```bash
# .env.local points to localhost services
USE_LOCALSTACK=true
DB_HOST=localhost
AWS_ENDPOINT_URL=http://localhost:4566
```

**Production** (AWS):
```bash
# Switch to real AWS
# Update DB_HOST, DB_USER, DB_PASSWORD, DB_SECRET_ARN to RDS values
# Remove AWS_ENDPOINT_URL and USE_LOCALSTACK
```

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov

# Run specific test file
pytest tests/test_loader.py

# Run specific test
pytest tests/test_loader.py::test_price_download
```

## Debugging

### View logs

```bash
# PostgreSQL logs
docker-compose logs postgres

# LocalStack logs
docker-compose logs localstack

# Follow logs
docker-compose logs -f postgres
```

### Connect to container

```bash
# Bash into PostgreSQL container
docker-compose exec postgres bash

# Run psql
docker-compose exec postgres psql -U stocks -d stocks
```

### Check disk usage

```bash
# Docker image sizes
docker system df

# Prune unused (careful!)
docker system prune -a
```

## Performance Tips

1. **Use tmpfs for temporary tables** (LocalStack S3 staging):
   ```bash
   # Already configured in docker-compose.yml
   # Stores staging data in memory for speed
   ```

2. **Reduce logging verbosity** when not debugging:
   ```bash
   LOG_LEVEL=WARNING
   ```

3. **Close unused pgAdmin** to save memory:
   ```bash
   docker-compose stop pgadmin
   ```

4. **Mount code volumes** for live edits (optional):
   ```yaml
   # Add to docker-compose.yml if needed
   volumes:
     - .:/app
   ```

## Troubleshooting

**"Connection refused" on localhost:5432**
```bash
# PostgreSQL not ready yet, wait and retry
docker-compose logs postgres
docker-compose wait postgres  # (not standard, use: docker-compose ps)
```

**"Permission denied" on docker socket (Linux)**
```bash
# Add user to docker group
sudo usermod -aG docker $USER
newgrp docker
```

**LocalStack S3 not working**
```bash
# Check LocalStack is running
docker-compose ps localstack

# Test connection
aws --endpoint-url=http://localhost:4566 s3 ls
```

**Database migrations stuck**
```bash
# Reset and reinitialize
docker-compose down -v
docker-compose up postgres
```

**Out of disk space**
```bash
# Clean up Docker
docker system prune -a --volumes

# Check docker volume size
du -sh /var/lib/docker/volumes/*/
```

## Data Persistence

- **PostgreSQL data**: Persists in `postgres_data` Docker volume
- **LocalStack data**: Ephemeral (reset on restart)
- **Code changes**: Instant (no rebuild needed)

To preserve data across restarts:
```bash
docker-compose down  # keeps volumes

docker-compose up    # restarts with same data
```

To wipe everything:
```bash
docker-compose down -v
```

## Next Steps

1. Set up API keys in `.env.local`
2. Run a loader: `python3 loadstocksymbols.py`
3. Inspect database: http://localhost:5050
4. Iterate on code (changes are instant)
5. Run tests: `pytest`

## Reference

- [Docker Compose docs](https://docs.docker.com/compose/)
- [PostgreSQL docs](https://www.postgresql.org/docs/)
- [LocalStack docs](https://docs.localstack.cloud/)
- [pgAdmin docs](https://www.pgadmin.org/docs/)
