// pm2 process file. Used by pm2-runtime inside the Docker image, and by plain `pm2 start ecosystem.config.cjs` on a server.
module.exports = {
  apps: [{
    name: 'shaxed-site',
    script: 'server/index.js',
    node_args: '--disable-warning=ExperimentalWarning --env-file-if-exists=.env',
    exec_mode: 'fork',
    instances: 1,                 // one process: the blog is a single SQLite file and login throttling is kept in memory
    max_memory_restart: '300M',
    env: { NODE_ENV: 'production' },
  }],
};
