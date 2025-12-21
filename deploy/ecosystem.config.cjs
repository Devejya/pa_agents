// PM2 Configuration for Yennifer API
module.exports = {
  apps: [
    {
      name: 'yennifer-api',
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
      error_file: '/var/log/yennifer/error.log',
      out_file: '/var/log/yennifer/out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
    },
  ],
}

