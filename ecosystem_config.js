module.exports = {
  apps: [
    {
      name: 'anvel-js',
      script: 'native/js_app/index.js',
      env: {
        ANVEL_LOG_STDOUT: '1'
      }
    }
  ]
};
