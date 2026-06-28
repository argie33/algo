#!/bin/bash
set -e

# ============================================================
# Bastion Host Setup Script
# ============================================================

# Update system
yum update -y
yum install -y postgresql15-client tmux vim git

# Install AWS CLI v2
curl "https://awscli.amazonaws.com/awscliv2.zip" -o "awscliv2.zip"
unzip awscliv2.zip
sudo ./aws/install

# Install Terraform (optional, for testing)
curl -fsSL https://apt.releases.hashicorp.com/gpg | sudo apt-key add -
apt-add-repository "deb [arch=amd64] https://apt.releases.hashicorp.com $(lsb_release -cs) main"
apt-get update && apt-get install -y terraform

# CloudWatch logs for SSM sessions
yum install -y amazon-cloudwatch-agent

# Configure CloudWatch agent for SSM logs
cat > /opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<EOF
{
  "logs": {
    "logs_collected": {
      "files": {
        "collect_list": [
          {
            "file_path": "/var/log/secure",
            "log_group_name": "/aws/ssm/${region}-bastion",
            "log_stream_name": "/var/log/secure"
          }
        ]
      }
    }
  }
}
EOF

# Start CloudWatch agent
/opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl \
  -a fetch-config \
  -m ec2 \
  -s \
  -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json

# Signal completion
echo "Bastion setup complete" > /tmp/bastion-setup-complete.log
