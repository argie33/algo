const express = require("express");
const request = require("supertest");
const { cacheMiddleware, globalCache } = require("../../../middleware/cacheMiddleware");

describe("cacheMiddleware user scoping", () => {
  beforeEach(() => {
    globalCache.clear();
  });

  test("does not leak one authenticated user's cached response to a different user", async () => {
    // Regression test: /api/trades is mounted as
    // authenticateToken -> cacheMiddleware(90) -> tradesRoutes and returns data
    // filtered by req.user.sub. The cache key generator previously used only
    // the URL+query string, so two different users hitting the same URL within
    // the TTL window would get served the FIRST user's response - a real
    // cross-user data leak of live trade/position data.
    const app = express();
    app.use((req, res, next) => {
      req.user = { sub: req.headers["x-test-user"] };
      next();
    });
    app.use(cacheMiddleware(90));
    app.get("/api/trades", (req, res) => {
      res.status(200).json({ success: true, owner: req.user.sub });
    });

    const userAResponse = await request(app)
      .get("/api/trades")
      .set("x-test-user", "user-a");
    expect(userAResponse.body.owner).toBe("user-a");

    const userBResponse = await request(app)
      .get("/api/trades")
      .set("x-test-user", "user-b");

    expect(userBResponse.body.owner).toBe("user-b");
    expect(userBResponse.headers["x-cache"]).toBe("MISS");
  });

  test("still serves a cache HIT for the same user requesting the same URL twice", async () => {
    const app = express();
    app.use((req, res, next) => {
      req.user = { sub: "user-a" };
      next();
    });
    app.use(cacheMiddleware(90));
    let callCount = 0;
    app.get("/api/trades", (req, res) => {
      callCount++;
      res.status(200).json({ success: true, callCount });
    });

    const first = await request(app).get("/api/trades");
    expect(first.body.callCount).toBe(1);

    const second = await request(app).get("/api/trades");
    expect(second.body.callCount).toBe(1);
    expect(second.headers["x-cache"]).toBe("HIT");
  });
});
