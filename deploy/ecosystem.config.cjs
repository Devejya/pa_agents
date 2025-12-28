// PM2 Configuration for Yennifer Services
module.exports = {
  apps: [
    // Waitlist/Signup API (Node.js) - Legacy
    {
      name: 'yennifer-waitlist',
      script: './dist/server.js',
      cwd: '/var/www/yennifer/backend',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env: {
        NODE_ENV: 'production',
        PORT: 3001,
      },
      error_file: '/var/log/yennifer/waitlist-error.log',
      out_file: '/var/log/yennifer/waitlist-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },
    // Yennifer Chat API (Python/FastAPI) - New
    {
      name: 'yennifer-chat',
      script: '/var/www/yennifer/yennifer_api/venv/bin/uvicorn',
      args: 'app.main:app --host 127.0.0.1 --port 8000',
      cwd: '/var/www/yennifer/yennifer_api',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '1G',  // LLM operations may need more memory
      interpreter: 'none',
      env: {
        ENVIRONMENT: 'production',
        PORT: 8000,
        PYTHONPATH: '/var/www/yennifer/yennifer_api:/var/www/yennifer/agent/src',
      },
      error_file: '/var/log/yennifer/chat-error.log',
      out_file: '/var/log/yennifer/chat-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },
    // User Network Service (Python/FastAPI)
    {
      name: 'user-network',
      script: '/var/www/yennifer/user_network/venv/bin/uvicorn',
      args: 'src.main:app --host 127.0.0.1 --port 8001',
      cwd: '/var/www/yennifer/user_network',
      instances: 1,
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      interpreter: 'none',
      env: {
        ENVIRONMENT: 'production',
        PORT: 8001,
      },
      error_file: '/var/log/yennifer/user-network-error.log',
      out_file: '/var/log/yennifer/user-network-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },
  ],
}
