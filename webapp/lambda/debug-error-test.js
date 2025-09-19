const express = require("express");
const request = require("supertest");

const errorHandler = require("./middleware/errorHandler");

const app = express();

app.get("/test-unknown-pg-error", (req, res, next) => {
  const err = new Error("Unknown PostgreSQL error");
  err.code = "12345"; // Unknown code
  next(err);
});

app.use(errorHandler);

async function testError() {
  const response = await request(app).get("/test-unknown-pg-error");
  console.log("Status:", response.status);
  console.log("Body:", JSON.stringify(response.body, null, 2));
  console.log("Error exists:", !!response.body.error);
  if (response.body.error) {
    console.log("Error message:", response.body.error.message);
  }
}

testError().catch(console.error);