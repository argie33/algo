# React Component Unit Tests

This directory contains **pure React component unit tests** that focus on testing individual components in isolation.

## Test Structure

```
unit/components/
├── ui/                          # UI component tests (buttons, cards, inputs)
│   ├── Button.unit.test.jsx     # Button component props, variants, events
│   ├── Card.unit.test.jsx       # Card composition and rendering
│   └── ...
├── domain/                      # Business domain components
│   ├── MarketStatusBar.unit.test.jsx  # Market status logic
│   ├── RealTimePriceWidget.unit.test.jsx  # Price display logic
│   └── ...
├── auth/                        # Authentication components
│   ├── LoginForm.unit.test.jsx  # Already exists
│   └── ...
└── test-helpers/                # Shared test utilities
    └── component-test-utils.js  # Mock data, render helpers
```

## What These Tests Cover

### ✅ **Pure React Component Testing**

- **Props testing**: Component renders correctly with different props
- **State testing**: Component state changes work as expected
- **Event handling**: onClick, onChange, onSubmit handlers work
- **Conditional rendering**: Component shows/hides content based on props/state
- **Accessibility**: ARIA attributes, keyboard navigation, screen readers
- **Error boundaries**: Component handles errors gracefully

### ❌ **What These Tests DON'T Cover**

- API integration (covered by integration tests)
- Full user workflows (covered by E2E tests)
- Authentication flows (covered by integration tests)
- Database operations (covered by backend tests)
- Cross-browser compatibility (covered by E2E tests)

## Test Principles

1. **Isolated Testing**: Mock all external dependencies
2. **Props-Driven**: Test component behavior based on props
3. **Fast Execution**: No network calls, no real APIs
4. **Deterministic**: Same inputs always produce same outputs
5. **Focused**: One component per test file

## Test Utilities

Use `test-helpers/component-test-utils.js` for:

- **renderWithTheme**: Render components with MUI theme
- **createMockData**: Generate consistent test data
- **createMockEventHandlers**: Mock event functions
- **buildProps**: Build component props with defaults

## Example Test Structure

```jsx
describe("ComponentName", () => {
  describe("Rendering", () => {
    it("should render with default props");
    it("should render with custom props");
  });

  describe("Props", () => {
    it("should handle variant prop");
    it("should apply className");
  });

  describe("Events", () => {
    it("should handle click events");
    it("should handle form submission");
  });

  describe("State", () => {
    it("should update state on interaction");
  });

  describe("Accessibility", () => {
    it("should be keyboard accessible");
    it("should have proper ARIA labels");
  });
});
```

## Running Tests

```bash
# Run all component unit tests
npm test src/tests/unit/components/

# Run specific component test
npm test Button.unit.test.jsx

# Run with coverage
npm test -- --coverage src/tests/unit/components/

# Watch mode
npm test -- --watch src/tests/unit/components/
```

## Integration with Other Tests

- **Unit Tests** (this directory): Individual component behavior
- **Integration Tests**: Component + API + business logic
- **E2E Tests**: Full user workflows across pages
- **Accessibility Tests**: WCAG compliance across full pages

This creates comprehensive test coverage without duplication.
