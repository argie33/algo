#!/bin/bash
set -eux

# 1) System update + tooling
yum update -y
yum install -y curl jq aws-cli

# 2) Add PGDG repo & install psql 10
curl -fsSL \
  https://download.postgresql.org/pub/repos/yum/reporpms/EL-7-x86_64/pgdg-redhat-repo-latest.noarch.rpm \
  -o /tmp/pgdg.rpm
rpm -Uvh /tmp/pgdg.rpm
yum remove -y postgresql postgresql-libs
yum install -y postgresql10

# 3) Set AWS CLI region
aws configure set region ${AWS_DEFAULT_REGION}

# 4) Fetch DB creds
CREDS=$(aws secretsmanager get-secret-value \
  --secret-id "${DB_SECRET_NAME}" \
  --query SecretString --output text)
DB_USER=$(echo "$CREDS" | jq -r .username)
DB_PASS=$(echo "$CREDS" | jq -r .password)
DB_NAME=$(echo "$CREDS" | jq -r .dbname)

# 5) Lookup RDS endpoint & port
DB_HOST=$(aws cloudformation describe-stacks \
  --stack-name "${DB_STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='DBEndpoint'].OutputValue" \
  --output text)
DB_PORT=$(aws cloudformation describe-stacks \
  --stack-name "${DB_STACK_NAME}" \
  --query "Stacks[0].Outputs[?OutputKey=='DBPort'].OutputValue" \
  --output text)

# 6) Write .pgpass
echo "${DB_HOST}:${DB_PORT}:${DB_NAME}:${DB_USER}:${DB_PASS}" \
  > /home/ec2-user/.pgpass
chmod 600 /home/ec2-user/.pgpass
chown ec2-user:ec2-user /home/ec2-user/.pgpass

# 7) Export env for interactive sessions
cat >> /home/ec2-user/.bash_profile <<'EOF'
export PGHOST=${DB_HOST}
export PGPORT=${DB_PORT}
export PGUSER=${DB_USER}
export PGPASSWORD=${DB_PASS}
export PGDATABASE=${DB_NAME}
EOF
chown ec2-user:ec2-user /home/ec2-user/.bash_profile
