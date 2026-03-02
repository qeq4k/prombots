interpreter: "python3", module.exports = {
  apps: [
    {
      name: "cinema",
      script: "movie.py",
      interpreter: "python3",
      cwd: "/root/projectss",
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 4000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8"
      },
      error_file: "/root/projectss/logs/cinema-error.log",
      out_file: "/root/projectss/logs/cinema-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      time: true
    },
    {
      name: "economy",
      script: "economika.py",
      interpreter: "python3",
      cwd: "/root/projectss",
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 4000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8"
      },
      error_file: "/root/projectss/logs/economy-error.log",
      out_file: "/root/projectss/logs/economy-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      time: true
    },
    {
      name: "politics",
      script: "politika.py",
      interpreter: "python3",
      cwd: "/root/projectss",
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 4000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8"
      },
      error_file: "/root/projectss/logs/politics-error.log",
      out_file: "/root/projectss/logs/politics-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      time: true
    },
    {
      name: "bot_handler",
      script: "bot_handler.py",
      interpreter: "python3",
      cwd: "/root/projectss",
      autorestart: true,
      watch: false,
      max_memory_restart: "300M",
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 4000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8"
      },
      error_file: "/root/projectss/logs/bot_handler-error.log",
      out_file: "/root/projectss/logs/bot_handler-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      time: true
    },
    {
      name: "checker",
      script: "bot.py",
      interpreter: "python3",
      cwd: "/root/projectss/checkerrr",
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 4000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8"
      },
      error_file: "/root/projectss/logs/checker-error.log",
      out_file: "/root/projectss/logs/checker-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      time: true
    },
    {
      name: "urgent_news",
      script: "urgent_news.py",
      interpreter: "python3",
      cwd: "/root/projectss",
      autorestart: true,
      watch: false,
      max_memory_restart: "300M",
      max_restarts: 10,
      min_uptime: "10s",
      restart_delay: 4000,
      env: {
        PYTHONUNBUFFERED: "1",
        PYTHONIOENCODING: "utf-8"
      },
      error_file: "/root/projectss/logs/urgent-error.log",
      out_file: "/root/projectss/logs/urgent-out.log",
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      merge_logs: true,
      time: true
    }
  ]
};
