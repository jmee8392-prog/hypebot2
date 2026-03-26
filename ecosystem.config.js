module.exports = {
  apps: [
    {
      name: "hyperliquid-bot",
      script: "hyperliquid_trading_bot.py",
      interpreter: "./venv/bin/python3",
      cwd: "/home/hyperliquid-bot",
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      env: {
        NODE_ENV: "production",
      },
      log_date_format: "YYYY-MM-DD HH:mm:ss Z",
      error_file: "/home/hyperliquid-bot/logs/error.log",
      out_file: "/home/hyperliquid-bot/logs/output.log",
      merge_logs: true,
      max_memory_restart: "300M",
    },
  ],
};
