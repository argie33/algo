const createValidationMiddleware = (schema) => {
  return (req, res, next) => {
    try {
      if (schema && typeof schema === "object") {
        const errors = [];

        for (const field in schema) {
          const rules = schema[field];
          const value =
            req.body[field] || req.params[field] || req.query[field];

          if (
            rules.required &&
            (value === undefined || value === null || value === "")
          ) {
            errors.push(`${field} is required`);
          }

          if (value !== undefined && rules.type) {
            if (rules.type === "string" && typeof value !== "string") {
              errors.push(`${field} must be a string`);
            }
            if (rules.type === "number" && isNaN(Number(value))) {
              errors.push(`${field} must be a number`);
            }
            if (
              rules.type === "email" &&
              !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
            ) {
              errors.push(`${field} must be a valid email`);
            }
          }

          if (value !== undefined && rules.min && value.length < rules.min) {
            errors.push(`${field} must be at least ${rules.min} characters`);
          }

          if (value !== undefined && rules.max && value.length > rules.max) {
            errors.push(`${field} must be at most ${rules.max} characters`);
          }
        }

        if (errors.length > 0) {
          return res.status(400).json({
            success: false,
            error: "Validation failed",
            details: errors,
          });
        }
      }

      next();
    } catch (error) {
      console.error("Validation middleware error:", error);
      res.status(500).json({
        success: false,
        error: "Internal validation error",
      });
    }
  };
};

module.exports = {
  createValidationMiddleware,
};
