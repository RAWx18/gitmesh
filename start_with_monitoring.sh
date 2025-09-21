#!/bin/bash

# GitMesh Startup Script with Rate Limiting Monitoring
# This script starts all GitMesh services with enhanced monitoring

set -e

echo "Starting GitMesh with Enhanced Rate Limiting..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in the right directory
if [ ! -f "backend/app.py" ] || [ ! -f "ui/package.json" ]; then
    print_error "Please run this script from the GitMesh root directory"
    exit 1
fi

# Check if virtual environment exists
if [ ! -d "backend/venv" ]; then
    print_warning "Virtual environment not found, creating one..."
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cd ..
fi

# Check if node_modules exists
if [ ! -d "ui/node_modules" ]; then
    print_warning "Node modules not found, installing..."
    cd ui
    npm install
    cd ..
fi

# Function to start backend
start_backend() {
    print_status "Starting backend server..."
    cd backend
    source venv/bin/activate
    export PYTHONPATH="${PYTHONPATH}:$(pwd)"
    
    # Start backend in background
    nohup python -m uvicorn app:app --host 0.0.0.0 --port 8000 --reload > logs/backend.log 2>&1 &
    BACKEND_PID=$!
    echo $BACKEND_PID > backend.pid
    
    cd ..
    print_status "Backend started with PID: $BACKEND_PID"
}

# Function to start frontend
start_frontend() {
    print_status "Starting frontend server..."
    cd ui
    
    # Build if needed
    if [ ! -d ".next" ]; then
        print_status "Building frontend..."
        npm run build
    fi
    
    # Start frontend in background
    nohup npm run start > ../backend/logs/frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > frontend.pid
    
    cd ..
    print_status "Frontend started with PID: $FRONTEND_PID"
}

# Function to start monitoring
start_monitoring() {
    print_status "Starting rate limit monitoring..."
    cd backend
    source venv/bin/activate
    export PYTHONPATH="${PYTHONPATH}:$(pwd)"
    
    # Start monitoring in background
    nohup python scripts/restart_on_rate_limit.py > logs/monitor.log 2>&1 &
    MONITOR_PID=$!
    echo $MONITOR_PID > monitor.pid
    
    cd ..
    print_status "Monitoring started with PID: $MONITOR_PID"
}

# Function to check if service is running
check_service() {
    local service_name=$1
    local pid_file=$2
    local port=$3
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p $pid > /dev/null 2>&1; then
            if [ -n "$port" ]; then
                if netstat -tuln | grep ":$port " > /dev/null 2>&1; then
                    print_status "$service_name is running (PID: $pid, Port: $port)"
                    return 0
                else
                    print_warning "$service_name process exists but port $port is not listening"
                    return 1
                fi
            else
                print_status "$service_name is running (PID: $pid)"
                return 0
            fi
        else
            print_warning "$service_name PID file exists but process is not running"
            rm -f "$pid_file"
            return 1
        fi
    else
        return 1
    fi
}

# Function to stop services
stop_services() {
    print_status "Stopping GitMesh services..."
    
    # Stop backend
    if [ -f "backend/backend.pid" ]; then
        local pid=$(cat "backend/backend.pid")
        if ps -p $pid > /dev/null 2>&1; then
            kill $pid
            print_status "Backend stopped"
        fi
        rm -f "backend/backend.pid"
    fi
    
    # Stop frontend
    if [ -f "ui/frontend.pid" ]; then
        local pid=$(cat "ui/frontend.pid")
        if ps -p $pid > /dev/null 2>&1; then
            kill $pid
            print_status "Frontend stopped"
        fi
        rm -f "ui/frontend.pid"
    fi
    
    # Stop monitoring
    if [ -f "backend/monitor.pid" ]; then
        local pid=$(cat "backend/monitor.pid")
        if ps -p $pid > /dev/null 2>&1; then
            kill $pid
            print_status "Monitoring stopped"
        fi
        rm -f "backend/monitor.pid"
    fi
}

# Function to show status
show_status() {
    echo "GitMesh Service Status:"
    echo "======================"
    
    check_service "Backend" "backend/backend.pid" "8000" || print_warning "Backend is not running"
    check_service "Frontend" "ui/frontend.pid" "3000" || print_warning "Frontend is not running"
    check_service "Monitoring" "backend/monitor.pid" || print_warning "Monitoring is not running"
    
    echo ""
    echo "URLs:"
    echo "- Backend: http://localhost:8000"
    echo "- Frontend: http://localhost:3000"
    echo "- API Docs: http://localhost:8000/docs"
    echo ""
    echo "Logs:"
    echo "- Backend: backend/logs/backend.log"
    echo "- Frontend: backend/logs/frontend.log"
    echo "- Monitor: backend/logs/monitor.log"
}

# Create logs directory
mkdir -p backend/logs

# Handle command line arguments
case "${1:-start}" in
    start)
        print_status "Starting GitMesh services..."
        
        # Check if services are already running
        if check_service "Backend" "backend/backend.pid" "8000" && 
           check_service "Frontend" "ui/frontend.pid" "3000" && 
           check_service "Monitoring" "backend/monitor.pid"; then
            print_warning "All services are already running"
            show_status
            exit 0
        fi
        
        # Start services
        start_backend
        sleep 3  # Wait for backend to start
        
        start_frontend
        sleep 2  # Wait for frontend to start
        
        start_monitoring
        sleep 1  # Wait for monitoring to start
        
        print_status "All services started successfully!"
        show_status
        
        # Setup signal handlers for graceful shutdown
        trap 'print_status "Received interrupt signal, stopping services..."; stop_services; exit 0' INT TERM
        
        # Keep script running
        print_status "Press Ctrl+C to stop all services"
        while true; do
            sleep 10
            # Check if all services are still running
            if ! check_service "Backend" "backend/backend.pid" "8000" > /dev/null 2>&1; then
                print_error "Backend service died, restarting..."
                start_backend
            fi
            if ! check_service "Frontend" "ui/frontend.pid" "3000" > /dev/null 2>&1; then
                print_error "Frontend service died, restarting..."
                start_frontend
            fi
            if ! check_service "Monitoring" "backend/monitor.pid" > /dev/null 2>&1; then
                print_error "Monitoring service died, restarting..."
                start_monitoring
            fi
        done
        ;;
    
    stop)
        stop_services
        ;;
    
    restart)
        stop_services
        sleep 2
        $0 start
        ;;
    
    status)
        show_status
        ;;
    
    logs)
        case "${2:-all}" in
            backend)
                tail -f backend/logs/backend.log
                ;;
            frontend)
                tail -f backend/logs/frontend.log
                ;;
            monitor)
                tail -f backend/logs/monitor.log
                ;;
            all|*)
                print_status "Showing all logs (Ctrl+C to stop):"
                tail -f backend/logs/*.log
                ;;
        esac
        ;;
    
    *)
        echo "Usage: $0 {start|stop|restart|status|logs [backend|frontend|monitor|all]}"
        echo ""
        echo "Commands:"
        echo "  start    - Start all GitMesh services with monitoring"
        echo "  stop     - Stop all GitMesh services"
        echo "  restart  - Restart all GitMesh services"
        echo "  status   - Show status of all services"
        echo "  logs     - Show logs (optionally specify service)"
        echo ""
        echo "Examples:"
        echo "  $0 start          # Start all services"
        echo "  $0 logs backend   # Show backend logs"
        echo "  $0 status         # Check service status"
        exit 1
        ;;
esac