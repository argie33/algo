// Minimal diagnostic handler for testing Lambda execution
exports.handler = async (event) => {
  console.log('Event:', JSON.stringify(event, null, 2));
  console.log('Environment:', {
    NODE_ENV: process.env.NODE_ENV,
    DB_ENDPOINT: process.env.DB_ENDPOINT,
    DB_NAME: process.env.DB_NAME,
    DB_SECRET_ARN: process.env.DB_SECRET_ARN,
    LAMBDA_TASK_ROOT: process.env.LAMBDA_TASK_ROOT
  });

  return {
    statusCode: 200,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      message: 'Diagnostic endpoint working',
      timestamp: new Date().toISOString(),
      environment: process.env.NODE_ENV
    })
  };
};
