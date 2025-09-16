/**
 * Response Formatter Middleware
 * Adds standard response formatting methods to Express res object
 */

const responseFormatter = require("../utils/responseFormatter");

/**
 * Middleware to add standard response methods to res object
 * @param {Object} req - Express request object
 * @param {Object} res - Express response object
 * @param {Function} next - Express next function
 */
const responseFormatterMiddleware = (req, res, next) => {
  // Add API version header
  res.set("Api-Version", "v1.0");

  // Add success method
  res.success = (data, statusCode = 200, meta = {}) => {
    const formatted = responseFormatter.success(data, statusCode, meta);
    return res.status(formatted.statusCode).json(formatted.response);
  };

  // Add error method
  res.error = (message, statusCode = 400, details = {}) => {
    const formatted = responseFormatter.error(message, statusCode, details);
    return res.status(formatted.statusCode).json(formatted.response);
  };

  // Add paginated method
  res.paginated = (data, pagination, meta = {}) => {
    const formatted = responseFormatter.paginated(data, pagination, meta);
    return res.status(formatted.statusCode).json(formatted.response);
  };

  // Add validation error method
  res.validationError = (errors) => {
    const formatted = responseFormatter.validationError(errors);
    return res.status(formatted.statusCode).json(formatted.response);
  };

  // Add not found method
  res.notFound = (resource = "Resource") => {
    const formatted = responseFormatter.notFound(resource);
    return res.status(formatted.statusCode).json(formatted.response);
  };

  // Add unauthorized method
  res.unauthorized = (message = "Unauthorized access") => {
    const formatted = responseFormatter.unauthorized(message);
    return res.status(formatted.statusCode).json(formatted.response);
  };

  // Add forbidden method
  res.forbidden = (message = "Access forbidden") => {
    const formatted = responseFormatter.forbidden(message);
    return res.status(formatted.statusCode).json(formatted.response);
  };

  // Add server error method
  res.serverError = (message = "Internal server error", details = {}) => {
    const formatted = responseFormatter.serverError(message, details);
    return res.status(formatted.statusCode).json(formatted.response);
  };

  next();
};

module.exports = responseFormatterMiddleware;
