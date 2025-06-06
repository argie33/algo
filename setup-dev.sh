#!/bin/bash

# Development setup script for the Financial Data Web Application
# This script helps set up and run the application locally

set -e

echo "🚀 Financial Data Web Application - Development Setup"
echo "=================================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if Node.js is installed
check_node() {
    if ! command -v node &> /dev/null; then
        print_error "Node.js is not installed. Please install Node.js 18 or higher."
        exit 1
    fi
    
    NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
    if [ "$NODE_VERSION" -lt 18 ]; then
        print_error "Node.js version 18 or higher is required. Current version: $(node --version)"
        exit 1
    fi
    
    print_success "Node.js $(node --version) is installed"
}

# Check if npm is installed
check_npm() {
    if ! command -v npm &> /dev/null; then
        print_error "npm is not installed. Please install npm."
        exit 1
    fi
    
    print_success "npm $(npm --version) is installed"
}

# Function to install dependencies
install_dependencies() {
    print_status "Installing dependencies..."
    
    # Install backend dependencies
    print_status "Installing backend dependencies..."
    cd webapp/backend
    npm install
    cd ../..
    
    # Install frontend dependencies
    print_status "Installing frontend dependencies..."
    cd webapp/frontend
    npm install
    cd ../..
    
    print_success "All dependencies installed successfully"
}

# Function to set up environment files
setup_environment() {
    print_status "Setting up environment files..."
    
    # Backend environment
    if [ ! -f "webapp/backend/.env" ]; then
        print_status "Creating backend .env file..."
        cat > webapp/backend/.env << EOF
NODE_ENV=development
PORT=3001
LOG_LEVEL=debug

# Database Configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=fundamentals
DB_USER=postgres
DB_PASSWORD=password

# AWS Configuration (for production)
AWS_REGION=us-east-1
AWS_SECRETS_MANAGER_SECRET_NAME=rds-db-credentials/cluster-fundamentals

# CORS Configuration
CORS_ORIGIN=http://localhost:5173
EOF
        print_success "Backend .env file created"
    else
        print_warning "Backend .env file already exists"
    fi
    
    # Frontend environment
    if [ ! -f "webapp/frontend/.env" ]; then
        print_status "Creating frontend .env file..."
        cat > webapp/frontend/.env << EOF
VITE_API_URL=http://localhost:3001/api
VITE_APP_TITLE=Financial Data Platform
VITE_APP_DESCRIPTION=Professional financial data analysis platform
EOF
        print_success "Frontend .env file created"
    else
        print_warning "Frontend .env file already exists"
    fi
}

# Function to run database checks
check_database() {
    print_status "Checking database connection..."
    
    # Check if PostgreSQL is running (basic check)
    if command -v pg_isready &> /dev/null; then
        if pg_isready -h localhost -p 5432 &> /dev/null; then
            print_success "PostgreSQL is running"
        else
            print_warning "PostgreSQL may not be running on localhost:5432"
            print_warning "Make sure your database is accessible and credentials are correct"
        fi
    else
        print_warning "pg_isready not found. Cannot check PostgreSQL status"
        print_warning "Make sure PostgreSQL is installed and running"
    fi
}

# Function to run tests
run_tests() {
    print_status "Running tests..."
    
    # Backend tests
    print_status "Running backend tests..."
    cd webapp/backend
    if npm test; then
        print_success "Backend tests passed"
    else
        print_warning "Backend tests failed or not configured"
    fi
    cd ../..
    
    # Frontend tests
    print_status "Running frontend tests..."
    cd webapp/frontend
    if npm test -- --run; then
        print_success "Frontend tests passed"
    else
        print_warning "Frontend tests failed or not configured"
    fi
    cd ../..
}

# Function to build the application
build_application() {
    print_status "Building application..."
    
    # Build frontend
    print_status "Building frontend..."
    cd webapp/frontend
    npm run build
    cd ../..
    
    print_success "Application built successfully"
}

# Function to start development servers
start_dev_servers() {
    print_status "Starting development servers..."
    
    # Create a simple script to run both servers
    cat > start-dev.sh << 'EOF'
#!/bin/bash

# Function to cleanup background processes
cleanup() {
    echo "Shutting down servers..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit 0
}

# Set up trap for cleanup
trap cleanup SIGINT SIGTERM

echo "Starting backend server..."
cd webapp/backend
npm run dev &
BACKEND_PID=$!

echo "Starting frontend server..."
cd ../frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "🚀 Development servers started!"
echo "Frontend: http://localhost:5173"
echo "Backend:  http://localhost:3001"
echo "API Health: http://localhost:3001/api/health"
echo ""
echo "Press Ctrl+C to stop all servers"

# Wait for background processes
wait $BACKEND_PID $FRONTEND_PID
EOF
    
    chmod +x start-dev.sh
    
    print_success "Development startup script created: ./start-dev.sh"
    print_status "Run './start-dev.sh' to start both servers"
}

# Function to create Docker development setup
setup_docker() {
    print_status "Setting up Docker development environment..."
    
    # Create docker-compose for development
    cat > docker-compose.dev.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: fundamentals
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init-db.sql:/docker-entrypoint-initdb.d/init-db.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 10s
      timeout: 5s
      retries: 5

  backend:
    build:
      context: ./webapp/backend
      dockerfile: Dockerfile
    ports:
      - "3001:3001"
    environment:
      NODE_ENV: development
      DB_HOST: postgres
      DB_PORT: 5432
      DB_NAME: fundamentals
      DB_USER: postgres
      DB_PASSWORD: password
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      - ./webapp/backend:/app
      - /app/node_modules
    command: npm run dev

  frontend:
    build:
      context: ./webapp/frontend
      dockerfile: Dockerfile.dev
    ports:
      - "5173:5173"
    environment:
      VITE_API_URL: http://localhost:3001/api
    volumes:
      - ./webapp/frontend:/app
      - /app/node_modules
    command: npm run dev -- --host

volumes:
  postgres_data:
EOF

    # Create development Dockerfile for frontend
    cat > webapp/frontend/Dockerfile.dev << 'EOF'
FROM node:18-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host"]
EOF

    print_success "Docker development setup created"
    print_status "Run 'docker-compose -f docker-compose.dev.yml up' to start with Docker"
}

# Function to show help
show_help() {
    echo "Usage: $0 [OPTION]"
    echo ""
    echo "Options:"
    echo "  setup     - Full setup (install dependencies, environment, etc.)"
    echo "  install   - Install dependencies only"
    echo "  env       - Set up environment files only"
    echo "  test      - Run tests"
    echo "  build     - Build the application"
    echo "  dev       - Start development servers"
    echo "  docker    - Set up Docker development environment"
    echo "  check     - Check system requirements"
    echo "  help      - Show this help message"
    echo ""
}

# Main execution
main() {
    case "${1:-setup}" in
        "setup")
            check_node
            check_npm
            install_dependencies
            setup_environment
            check_database
            start_dev_servers
            setup_docker
            print_success "Development setup complete!"
            print_status "Next steps:"
            print_status "1. Make sure your database is running and accessible"
            print_status "2. Run './start-dev.sh' to start development servers"
            print_status "3. Visit http://localhost:5173 to view the application"
            ;;
        "install")
            check_node
            check_npm
            install_dependencies
            ;;
        "env")
            setup_environment
            ;;
        "test")
            run_tests
            ;;
        "build")
            build_application
            ;;
        "dev")
            start_dev_servers
            ;;
        "docker")
            setup_docker
            ;;
        "check")
            check_node
            check_npm
            check_database
            ;;
        "help")
            show_help
            ;;
        *)
            print_error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
