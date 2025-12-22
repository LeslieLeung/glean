import log from 'loglevel'
import type { LogLevel, Logger, LoggerConfig, NamedLoggerOptions } from './types'

/**
 * Default log level based on environment
 */
const getDefaultLogLevel = (): LogLevel => {
  // Check for environment variable first
  const envLogLevel = import.meta.env?.VITE_LOG_LEVEL as LogLevel
  if (envLogLevel && ['trace', 'debug', 'info', 'warn', 'error'].includes(envLogLevel)) {
    return envLogLevel
  }

  // Check localStorage for user preference
  try {
    const storedLevel = localStorage.getItem('glean_log_level') as LogLevel
    if (storedLevel && ['trace', 'debug', 'info', 'warn', 'error'].includes(storedLevel)) {
      return storedLevel
    }
  } catch {
    // Ignore localStorage errors (e.g., in private browsing)
  }

  // Default based on environment
  return import.meta.env?.MODE === 'production' ? 'error' : 'debug'
}

/**
 * Configure log level with persistence
 */
const setLogLevel = (level: LogLevel, persistent = false): void => {
  log.setLevel(level)

  if (persistent) {
    try {
      localStorage.setItem('glean_log_level', level)
    } catch {
      // Ignore localStorage errors
    }
  }
}

/**
 * Create a logger with optional configuration
 */
const createLogger = (config: LoggerConfig = {}): Logger => {
  const { level = getDefaultLogLevel(), prefix, persistent = false } = config

  // Set the log level
  setLogLevel(level, persistent)

  // Create logger methods
  const logger: Logger = {
    trace: (...args) => log.trace(...args),
    debug: (...args) => log.debug(...args),
    info: (...args) => log.info(...args),
    warn: (...args) => log.warn(...args),
    error: (...args) => log.error(...args),
  }

  // Add prefix if provided
  if (prefix) {
    const originalMethods = { ...logger }

    Object.keys(logger).forEach((level) => {
      const levelKey = level as keyof Logger
      logger[levelKey] = (...args) => {
        originalMethods[levelKey](`[${prefix}]`, ...args)
      }
    })
  }

  return logger
}

/**
 * Create a named logger with consistent formatting
 */
const createNamedLogger = (options: NamedLoggerOptions): Logger => {
  const { name, ...config } = options
  return createLogger({ ...config, prefix: name })
}

/**
 * Default logger instance
 */
export const logger = createLogger({
  level: getDefaultLogLevel(),
  persistent: true,
})

/**
 * Export factory functions and types
 */
export { createLogger, createNamedLogger, setLogLevel }
export type { LogLevel, Logger, LoggerConfig, NamedLoggerOptions }
