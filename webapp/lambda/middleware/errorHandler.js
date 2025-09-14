const errorHandler = (err, req, res, _next) => {
  console.error("Error occurred:", {
    message: err.message,
    stack: err.stack,
    url: req.url,
    method: req.method,
    timestamp: new Date().toISOString(),
  });

  // Default error response
  let status = 500;
  let message = "Internal Server Error";
  let details = null;

  // Handle specific error types
  if (err.name === "ValidationError") {
    status = 400;
    message = "Validation Error";
    details = err.message;
  } else if (err.code === "23505") {
    // PostgreSQL unique violation
    status = 409;
    message = "Duplicate entry";
    details = "A record with this information already exists";
  } else if (err.code === "23503") {
    // PostgreSQL foreign key violation
    status = 400;
    message = "Invalid reference";
    details = "Referenced record does not exist";
  } else if (err.code === "42P01") {
    // PostgreSQL table does not exist
    status = 500;
    message = "Database configuration error";
    details = "Required database table not found";
  } else if (err.message) {
    // If we have a custom error message, use it
    if (err.status) status = err.status;
    message = err.message;
  }

  const response = {
    success: false,
    error: message,
    status,
    timestamp: new Date().toISOString(),
    path: req.url,
  };

  // Add details in development mode
  if (process.env.NODE_ENV === "development" && details) {
    response.details = details;
  }

  res.status(status).json(response);
};

module.exports = errorHandler;
