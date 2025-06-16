import pino from 'pino';

export function createLogger(name: string): pino.Logger {
  const logLevel = process.env.LOG_LEVEL || 'info';
  const isDevelopment = process.env.NODE_ENV === 'development';
  
  const logger = pino({
    name,
    level: logLevel,
    timestamp: pino.stdTimeFunctions.isoTime,
    formatters: {
      level: (label) => {
        return { level: label.toUpperCase() };
      }
    },
    transport: isDevelopment ? {
      target: 'pino-pretty',
      options: {
        translateTime: 'HH:MM:ss Z',
        ignore: 'pid,hostname',
        colorize: true
      }
    } : undefined,
    base: {
      pid: process.pid,
      hostname: process.env.HOSTNAME || require('os').hostname()
    }
  });

  return logger;
}
