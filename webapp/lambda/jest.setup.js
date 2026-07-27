// Jest setup file
//
// CRITICAL FIX: this used to eagerly require utils/database and call the REAL,
// unmocked initializeDatabase() for every single test file (unit and integration
// alike). setupFilesAfterEnv runs before a test file's own jest.mock("pg", ...) is
// registered (jest.mock is file-local), and Node's require cache means that first,
// unmocked require of utils/database.js got cached for the rest of that test file's
// run - so even a test file that mocks "pg" itself and requires utils/database.js to
// test it directly (tests/unit/utils/database.test.js) got back the already-cached,
// really-connected-to-Postgres instance, not one built against its own mock. That
// caused spurious "role ... does not exist" failures. It also never actually
// synchronized anything - the promise was fire-and-forget (.then/.catch, never awaited
// by Jest), so it gave no real guarantee the DB was ready before tests ran even for
// integration tests. Tests that need a live database should initialize (and close) it
// themselves, scoped to their own suite.
