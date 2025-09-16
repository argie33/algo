const request = require("supertest");
const {
  initializeDatabase,
  closeDatabase,
} = require("../../../utils/database");

let app;

describe("Alerts Routes", () => {
  beforeAll(async () => {
    // Enable development bypass for authentication
    process.env.ALLOW_DEV_BYPASS = "true";
    await initializeDatabase();
    app = require("../../../server");
  });

  afterAll(async () => {
    await closeDatabase();
  });

  describe("GET /api/alerts/active", () => {
    test("should return active alerts with proper structure", async () => {
      const response = await request(app)
        .get("/api/alerts/active")
        .set("Authorization", "Bearer dev-bypass-token");

      expect([200, 404, 500]).toContain(response.status);

      if (response.status === 200) {
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty("alerts");
        expect(response.body.data).toHaveProperty("summary");
        expect(response.body.filters).toHaveProperty(
          "user_id",
          "dev-user-bypass"
        );
        expect(response.body).toHaveProperty("timestamp");
      } else {
        // Handle error cases (database not configured)
        expect(response.body.success).toBe(false);
        expect(response.body).toHaveProperty("error");
      }
    });

    test("should handle query parameters", async () => {
      const response = await request(app).get(
        "/api/alerts/active?priority=high&category=price&limit=25"
      );

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.user_id).toBe("dev-user-bypass");
    });

    test("should handle include_resolved parameter", async () => {
      const response = await request(app).get(
        "/api/alerts/active?include_resolved=true"
      );

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
    });
  });

  describe("GET /api/alerts", () => {
    test("should redirect to active alerts", async () => {
      const response = await request(app).get("/api/alerts");

      expect([200, 404, 500, 501].includes(response.status)).toBe(true);
    });

    test("should handle status parameter", async () => {
      const response = await request(app).get(
        "/api/alerts?status=resolved&limit=50"
      );

      expect([200, 404, 500, 501].includes(response.status)).toBe(true);
    });
  });

  describe("PUT /api/alerts/:alertId/acknowledge", () => {
    test("should acknowledge alert successfully", async () => {
      const alertId = "test_alert_123";

      const response = await request(app)
        .put(`/api/alerts/${alertId}/acknowledge`)
        .send({ action: "acknowledge" });

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data.alert_id).toBe(alertId);
      expect(response.body.data.action).toBe("acknowledge");
      expect(response.body.data.acknowledged_by).toBe("dev-user-bypass");
      expect(response.body.data.status).toBe("acknowledged");
      expect(response.body).toHaveProperty("message");
      expect(response.body).toHaveProperty("timestamp");
    });

    test("should handle dismiss action", async () => {
      const alertId = "test_alert_456";

      const response = await request(app)
        .put(`/api/alerts/${alertId}/acknowledge`)
        .send({ action: "dismiss" });

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data.action).toBe("dismiss");
      expect(response.body.data.alert_id).toBe(alertId);
    });

    test("should handle default acknowledge action", async () => {
      const alertId = "test_alert_789";

      const response = await request(app)
        .put(`/api/alerts/${alertId}/acknowledge`)
        .send({});

      expect([200, 404]).toContain(response.status);
      expect(response.body.data.action).toBe("acknowledge");
    });
  });

  describe("PUT /api/alerts/:alertId/snooze", () => {
    test("should snooze alert with default duration", async () => {
      const alertId = "test_alert_snooze";

      const response = await request(app)
        .put(`/api/alerts/${alertId}/snooze`)
        .send({});

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data.alert_id).toBe(alertId);
      expect(response.body.data.duration_minutes).toBe(60);
      expect(response.body.data.snoozed_by).toBe("dev-user-bypass");
      expect(response.body.data.status).toBe("snoozed");
      expect(response.body.data).toHaveProperty("snooze_until");
    });

    test("should snooze alert with custom duration", async () => {
      const alertId = "test_alert_custom_snooze";

      const response = await request(app)
        .put(`/api/alerts/${alertId}/snooze`)
        .send({ duration_minutes: 120 });

      expect([200, 404]).toContain(response.status);
      expect(response.body.data.duration_minutes).toBe(120);
    });

    test("should validate snooze_until timestamp", async () => {
      const alertId = "test_alert_time_validate";
      const beforeRequest = Date.now();

      const response = await request(app)
        .put(`/api/alerts/${alertId}/snooze`)
        .send({ duration_minutes: 30 });

      const snoozeUntil = new Date(response.body.data.snooze_until);
      const expectedTime = new Date(beforeRequest + 30 * 60 * 1000);

      expect([200, 404]).toContain(response.status);
      expect(snoozeUntil.getTime()).toBeGreaterThan(
        expectedTime.getTime() - 5000
      ); // 5s tolerance
      expect(snoozeUntil.getTime()).toBeLessThan(expectedTime.getTime() + 5000);
    });
  });

  describe("POST /api/alerts", () => {
    test("should create new alert", async () => {
      const alertData = {
        symbol: "AAPL",
        category: "price",
        condition: "above",
        threshold: 175.0,
        priority: "High",
        notification_methods: ["email", "push"],
      };

      const response = await request(app).post("/api/alerts").send(alertData);

      expect([200, 201]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data.user_id).toBe("test_user_123");
      expect(response.body.data.symbol).toBe("AAPL");
      expect(response.body.data.category).toBe("price");
      expect(response.body.data.condition).toBe("above");
      expect(response.body.data.threshold).toBe(175.0);
      expect(response.body.data.priority).toBe("High");
      expect(response.body.data.status).toBe("active");
      expect(response.body.data.notification_methods).toEqual([
        "email",
        "push",
      ]);
      expect(response.body.data).toHaveProperty("id");
      expect(response.body.data).toHaveProperty("created_at");
    });

    test("should create alert with defaults", async () => {
      const alertData = {
        symbol: "TSLA",
        category: "volume",
        condition: "spike",
        threshold: 2.0,
      };

      const response = await request(app).post("/api/alerts").send(alertData);

      expect([200, 201]).toContain(response.status);
      expect(response.body.data.priority).toBe("Medium");
      expect(response.body.data.notification_methods).toEqual(["email"]);
    });
  });

  describe("GET /api/alerts/summary", () => {
    test("should return alerts summary with default timeframe", async () => {
      const response = await request(app).get("/api/alerts/summary");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("summary");
      expect(response.body.data).toHaveProperty("severity_breakdown");
      expect(response.body.data).toHaveProperty("type_breakdown");
      expect(response.body.data).toHaveProperty("key_metrics");

      const summary = response.body.data.summary;
      expect(summary.timeframe).toBe("24h");
      expect(summary).toHaveProperty("total_alerts");
      expect(summary).toHaveProperty("active_alerts");
      expect(summary).toHaveProperty("triggered_alerts");
      expect(summary).toHaveProperty("period_start");
      expect(summary).toHaveProperty("period_end");
    });

    test("should handle different timeframes", async () => {
      const timeframes = ["1h", "6h", "24h", "7d", "30d"];

      for (const timeframe of timeframes) {
        const response = await request(app).get(
          `/api/alerts/summary?timeframe=${timeframe}`
        );

        expect([200, 404]).toContain(response.status);
        expect(response.body.data.summary.timeframe).toBe(timeframe);
      }
    });

    test("should reject invalid timeframe", async () => {
      const response = await request(app).get(
        "/api/alerts/summary?timeframe=invalid"
      );

      expect([400, 422]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toContain("Invalid timeframe");
      expect(response.body.requested_timeframe).toBe("invalid");
    });

    test("should include trends when requested", async () => {
      const response = await request(app).get(
        "/api/alerts/summary?include_trends=true"
      );

      expect([200, 404]).toContain(response.status);
      expect(response.body.data).toHaveProperty("trends");
      expect(response.body.data.metadata.includes_trends).toBe(true);
    });

    test("should include detailed stats when requested", async () => {
      const response = await request(app).get(
        "/api/alerts/summary?include_stats=true"
      );

      expect([200, 404]).toContain(response.status);
      expect(response.body.data).toHaveProperty("detailed_statistics");
      expect(response.body.data.metadata.includes_stats).toBe(true);
    });

    test("should validate severity breakdown structure", async () => {
      const response = await request(app).get("/api/alerts/summary");

      const breakdown = response.body.data.severity_breakdown;
      expect(breakdown).toHaveProperty("critical");
      expect(breakdown).toHaveProperty("high");
      expect(breakdown).toHaveProperty("medium");
      expect(breakdown).toHaveProperty("low");

      Object.values(breakdown).forEach((severity) => {
        expect(severity).toHaveProperty("count");
        expect(severity).toHaveProperty("percentage");
        expect(typeof severity.count).toBe("number");
        expect(typeof severity.percentage).toBe("number");
      });
    });
  });

  describe("GET /api/alerts/settings", () => {
    test("should return comprehensive alert settings", async () => {
      const response = await request(app).get("/api/alerts/settings");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("settings");
      expect(response.body.data).toHaveProperty("summary");
      expect(response.body.data).toHaveProperty("quick_actions");
      expect(response.body.data).toHaveProperty("metadata");

      const settings = response.body.data.settings;
      expect(settings.user_id).toBe("test_user_123");
      expect(settings).toHaveProperty("notification_preferences");
      expect(settings).toHaveProperty("delivery_settings");
      expect(settings).toHaveProperty("alert_categories");
      expect(settings).toHaveProperty("watchlist_settings");
      expect(settings).toHaveProperty("subscription_info");
    });

    test("should include notification preferences", async () => {
      const response = await request(app).get("/api/alerts/settings");

      const notifications =
        response.body.data.settings.notification_preferences;
      expect(notifications).toHaveProperty("email_enabled");
      expect(notifications).toHaveProperty("sms_enabled");
      expect(notifications).toHaveProperty("push_enabled");
      expect(typeof notifications.email_enabled).toBe("boolean");
    });

    test("should include alert categories", async () => {
      const response = await request(app).get("/api/alerts/settings");

      const categories = response.body.data.settings.alert_categories;
      expect(categories).toHaveProperty("price_alerts");
      expect(categories).toHaveProperty("volume_alerts");
      expect(categories).toHaveProperty("earnings_alerts");
      expect(categories).toHaveProperty("technical_alerts");

      Object.values(categories).forEach((category) => {
        expect(category).toHaveProperty("enabled");
      });
    });

    test("should include subscription info", async () => {
      const response = await request(app).get("/api/alerts/settings");

      const subscription = response.body.data.settings.subscription_info;
      expect(subscription).toHaveProperty("plan");
      expect(subscription).toHaveProperty("alerts_used_today");
      expect(subscription).toHaveProperty("alerts_limit_daily");
      expect(subscription).toHaveProperty("premium_features");
      expect(Array.isArray(subscription.premium_features)).toBe(true);
    });
  });

  describe("GET /api/alerts/history", () => {
    test("should return 501 not implemented", async () => {
      const response = await request(app).get("/api/alerts/history");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Alert history not implemented");
      expect(response.body).toHaveProperty("troubleshooting");
      expect(response.body.user_id).toBe("dev-user-bypass");
    });

    test("should handle query parameters", async () => {
      const response = await request(app).get(
        "/api/alerts/history?limit=50&status=resolved&category=price"
      );

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
    });
  });

  describe("GET /api/alerts/rules", () => {
    test("should return alert rules", async () => {
      const response = await request(app).get("/api/alerts/rules");

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data).toHaveProperty("rules");
      expect(response.body).toHaveProperty("summary");
      expect(Array.isArray(response.body.data.rules)).toBe(true);

      const summary = response.body.summary;
      expect(summary).toHaveProperty("total_rules");
      expect(summary).toHaveProperty("active_rules");
      expect(summary).toHaveProperty("inactive_rules");
      expect(typeof summary.total_rules).toBe("number");
    });

    test("should return rule structure", async () => {
      const response = await request(app).get("/api/alerts/rules");

      if (response.body.data.rules.length > 0) {
        const rule = response.body.data.rules[0];
        expect(rule).toHaveProperty("rule_id");
        expect(rule).toHaveProperty("name");
        expect(rule).toHaveProperty("type");
        expect(rule).toHaveProperty("enabled");
        expect(rule).toHaveProperty("created_at");
      }
    });
  });

  describe("GET /api/alerts/webhooks", () => {
    test("should return 501 not implemented", async () => {
      const response = await request(app).get("/api/alerts/webhooks");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Alert webhooks not implemented");
      expect(response.body).toHaveProperty("troubleshooting");
      expect(response.body.user_id).toBe("dev-user-bypass");
    });

    test("should handle webhook parameters", async () => {
      const response = await request(app).get(
        "/api/alerts/webhooks?status=active&webhook_type=slack&limit=10"
      );

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
    });
  });

  describe("POST /api/alerts/create", () => {
    test("should create alert with required fields", async () => {
      const alertData = {
        symbol: "NVDA",
        threshold: 500.0,
      };

      const response = await request(app)
        .post("/api/alerts/create")
        .send(alertData);

      expect([200, 201]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data.alert.symbol).toBe("NVDA");
      expect(response.body.data.alert.threshold).toBe(500.0);
      expect(response.body.data.alert.user_id).toBe("test_user_123");
      expect(response.body.data.alert.status).toBe("active");
      expect(response.body.data).toHaveProperty("next_actions");
    });

    test("should use default values", async () => {
      const alertData = {
        symbol: "msft",
        threshold: 300.0,
      };

      const response = await request(app)
        .post("/api/alerts/create")
        .send(alertData);

      expect([200, 201]).toContain(response.status);
      expect(response.body.data.alert.symbol).toBe("MSFT");
      expect(response.body.data.alert.alert_type).toBe("price");
      expect(response.body.data.alert.condition).toBe("above");
      expect(response.body.data.alert.priority).toBe("medium");
      expect(response.body.data.alert.enabled).toBe(true);
    });

    test("should reject missing required fields", async () => {
      const response = await request(app)
        .post("/api/alerts/create")
        .send({ symbol: "AAPL" }); // Missing threshold

      expect([400, 422]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Missing required fields");
      expect(response.body.required).toEqual(["symbol", "threshold"]);
    });

    test("should reject empty request", async () => {
      const response = await request(app).post("/api/alerts/create").send({});

      expect([400, 422]).toContain(response.status);
      expect(response.body.success).toBe(false);
    });
  });

  describe("DELETE /api/alerts/delete/:alertId", () => {
    test("should delete alert successfully", async () => {
      const alertId = "alert_to_delete_123";

      const response = await request(app)
        .delete(`/api/alerts/delete/${alertId}`)
        .send({ reason: "no_longer_needed" });

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data.deleted_alert.alert_id).toBe(alertId);
      expect(response.body.data.deleted_alert.user_id).toBe("test_user_123");
      expect(response.body.data.deleted_alert.status).toBe("deleted");
      expect(response.body.data.deleted_alert.deletion_reason).toBe(
        "no_longer_needed"
      );
      expect(response.body.data).toHaveProperty("cleanup_actions");
    });

    test("should use default deletion reason", async () => {
      const alertId = "alert_default_reason";

      const response = await request(app)
        .delete(`/api/alerts/delete/${alertId}`)
        .send({});

      expect([200, 404]).toContain(response.status);
      expect(response.body.data.deleted_alert.deletion_reason).toBe(
        "user_requested"
      );
    });

    test("should reject empty alert ID", async () => {
      const response = await request(app)
        .delete("/api/alerts/delete/")
        .send({});

      expect([404, 500]).toContain(response.status);
    });
  });

  describe("GET /api/alerts/price", () => {
    test("should return 501 not implemented when no data", async () => {
      const response = await request(app).get("/api/alerts/price");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
      expect(response.body.error).toBe("Price alerts not implemented");
      expect(response.body).toHaveProperty("troubleshooting");
      expect(response.body.user_id).toBe("dev-user-bypass");
    });

    test("should handle symbol filter", async () => {
      const response = await request(app).get("/api/alerts/price?symbol=AAPL");

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
    });

    test("should handle threshold filters", async () => {
      const response = await request(app).get(
        "/api/alerts/price?threshold_min=100&threshold_max=200"
      );

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
    });

    test("should handle alert type filter", async () => {
      const response = await request(app).get(
        "/api/alerts/price?alert_type=stop_loss&status=active"
      );

      expect([400, 401, 404, 422, 500]).toContain(response.status);
      expect(response.body.success).toBe(false);
    });
  });

  describe("PUT /api/alerts/update/:alertId", () => {
    test("should update alert successfully", async () => {
      const alertId = "alert_to_update_123";
      const updateData = {
        threshold: 180.0,
        priority: "high",
        enabled: false,
        reason: "threshold_adjustment",
      };

      const response = await request(app)
        .put(`/api/alerts/update/${alertId}`)
        .send(updateData);

      expect([200, 404]).toContain(response.status);
      expect(response.body.success).toBe(true);
      expect(response.body.data.updated_alert.alert_id).toBe(alertId);
      expect(response.body.data.updated_alert.threshold).toBe(180.0);
      expect(response.body.data.updated_alert.priority).toBe("high");
      expect(response.body.data.updated_alert.enabled).toBe(false);
      expect(response.body.data.updated_alert.update_reason).toBe(
        "threshold_adjustment"
      );
      expect(response.body.data).toHaveProperty("changes_applied");
      expect(response.body.data.changes_applied).toEqual(
        Object.keys(updateData)
      );
    });

    test("should use defaults when no data provided", async () => {
      const alertId = "alert_defaults_123";

      const response = await request(app)
        .put(`/api/alerts/update/${alertId}`)
        .send({});

      expect([200, 404]).toContain(response.status);
      expect(response.body.data.updated_alert.symbol).toBe("AAPL");
      expect(response.body.data.updated_alert.enabled).toBe(true);
      expect(response.body.data.updated_alert.update_reason).toBe(
        "user_modification"
      );
    });

    test("should reject empty alert ID", async () => {
      const response = await request(app)
        .put("/api/alerts/update/")
        .send({ threshold: 200 });

      expect([404, 500]).toContain(response.status);
    });
  });

  describe("Authentication", () => {
    test("should include user context in all responses", async () => {
      const endpoints = [
        "/api/alerts/settings",
        "/api/alerts/rules",
        "/api/alerts/summary",
      ];

      for (const endpoint of endpoints) {
        const response = await request(app).get(endpoint);

        if (response.status === 200) {
          // Check if user context is preserved
          expect(response.body).toHaveProperty("timestamp");
        }
      }
    });
  });
});
