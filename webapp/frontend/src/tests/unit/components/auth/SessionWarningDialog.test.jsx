import {
  render,
  screen,
  fireEvent,
  waitFor,
  act,
} from "@testing-library/react";
import { vi } from "vitest";
import SessionWarningDialog from "../../../../components/auth/SessionWarningDialog";

describe("SessionWarningDialog", () => {
  const defaultProps = {
    open: true,
    timeRemaining: 300000, // 5 minutes
    onExtend: vi.fn(),
    onLogout: vi.fn(),
    onClose: vi.fn(),
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
  });

  describe("Basic Functionality", () => {
    test("renders session warning dialog when open", () => {
      render(<SessionWarningDialog {...defaultProps} />);

      expect(screen.getByText("Session Expiring Soon")).toBeInTheDocument();
      expect(
        screen.getByText(/Your session will expire in/)
      ).toBeInTheDocument();
      expect(screen.getByText("5:00")).toBeInTheDocument();
      expect(screen.getByText("Stay Signed In")).toBeInTheDocument();
      expect(screen.getByText("Sign Out Now")).toBeInTheDocument();
    });

    test("does not render when closed", () => {
      render(<SessionWarningDialog {...defaultProps} open={false} />);

      expect(
        screen.queryByText("Session Expiring Soon")
      ).not.toBeInTheDocument();
    });

    test("displays correct initial time formatting", () => {
      render(<SessionWarningDialog {...defaultProps} timeRemaining={125000} />);

      expect(screen.getByText("2:05")).toBeInTheDocument();
    });

    test("displays seconds with leading zeros", () => {
      render(<SessionWarningDialog {...defaultProps} timeRemaining={65000} />);

      expect(screen.getByText("1:05")).toBeInTheDocument();
    });
  });

  describe("Countdown Timer", () => {
    test("updates countdown every second", async () => {
      render(<SessionWarningDialog {...defaultProps} timeRemaining={5000} />);

      expect(screen.getByText("0:05")).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(1000);
      });

      await waitFor(() => {
        expect(screen.getByText("0:04")).toBeInTheDocument();
      });

      act(() => {
        vi.advanceTimersByTime(1000);
      });

      await waitFor(() => {
        expect(screen.getByText("0:03")).toBeInTheDocument();
      });
    });

    test("calls onLogout when countdown reaches zero", async () => {
      const onLogout = vi.fn();
      render(
        <SessionWarningDialog
          {...defaultProps}
          timeRemaining={2000}
          onLogout={onLogout}
        />
      );

      expect(screen.getByText("0:02")).toBeInTheDocument();

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      await waitFor(() => {
        expect(onLogout).toHaveBeenCalledTimes(1);
      });
    });

    test("stops countdown when dialog is closed", async () => {
      const { rerender } = render(
        <SessionWarningDialog {...defaultProps} timeRemaining={5000} />
      );

      expect(screen.getByText("0:05")).toBeInTheDocument();

      rerender(
        <SessionWarningDialog
          {...defaultProps}
          open={false}
          timeRemaining={5000}
        />
      );

      act(() => {
        vi.advanceTimersByTime(2000);
      });

      // Since dialog is closed, timer should not update
      rerender(
        <SessionWarningDialog
          {...defaultProps}
          open={true}
          timeRemaining={5000}
        />
      );
      expect(screen.getByText("0:05")).toBeInTheDocument();
    });

    test("updates countdown when timeRemaining prop changes", () => {
      const { rerender } = render(
        <SessionWarningDialog {...defaultProps} timeRemaining={5000} />
      );

      expect(screen.getByText("0:05")).toBeInTheDocument();

      rerender(
        <SessionWarningDialog {...defaultProps} timeRemaining={10000} />
      );

      expect(screen.getByText("0:10")).toBeInTheDocument();
    });
  });

  describe("Progress Bar", () => {
    test("displays progress bar with correct color for normal time", () => {
      render(<SessionWarningDialog {...defaultProps} timeRemaining={300000} />);

      const progressBar = screen.getByRole("progressbar");
      expect(progressBar).toBeInTheDocument();
    });

    test("changes progress bar color when time is critical", () => {
      render(<SessionWarningDialog {...defaultProps} timeRemaining={30000} />);

      const progressBar = screen.getByRole("progressbar");
      expect(progressBar).toBeInTheDocument();
    });

    test("updates progress bar as time decreases", async () => {
      render(<SessionWarningDialog {...defaultProps} timeRemaining={4000} />);

      const progressBar = screen.getByRole("progressbar");
      const initialValue = progressBar.getAttribute("aria-valuenow");

      act(() => {
        vi.advanceTimersByTime(1000);
      });

      await waitFor(() => {
        const newValue = progressBar.getAttribute("aria-valuenow");
        expect(newValue).not.toBe(initialValue);
      });
    });
  });

  describe("User Actions", () => {
    test("calls onLogout when Sign Out Now is clicked", () => {
      const onLogout = vi.fn();
      render(<SessionWarningDialog {...defaultProps} onLogout={onLogout} />);

      const signOutButton = screen.getByText("Sign Out Now");
      fireEvent.click(signOutButton);

      expect(onLogout).toHaveBeenCalledTimes(1);
    });

    test("calls onExtend and onClose when Stay Signed In is clicked", async () => {
      const onExtend = vi.fn().mockResolvedValue();
      const onClose = vi.fn();
      render(
        <SessionWarningDialog
          {...defaultProps}
          onExtend={onExtend}
          onClose={onClose}
        />
      );

      const staySignedInButton = screen.getByText("Stay Signed In");
      fireEvent.click(staySignedInButton);

      expect(onExtend).toHaveBeenCalledTimes(1);

      await waitFor(() => {
        expect(onClose).toHaveBeenCalledTimes(1);
      });
    });

    test("shows loading state when extending session", async () => {
      const onExtend = vi
        .fn()
        .mockImplementation(
          () => new Promise((resolve) => setTimeout(resolve, 100))
        );
      render(<SessionWarningDialog {...defaultProps} onExtend={onExtend} />);

      const staySignedInButton = screen.getByText("Stay Signed In");
      fireEvent.click(staySignedInButton);

      expect(screen.getByText("Extending...")).toBeInTheDocument();

      const buttons = screen.getAllByRole("button");
      buttons.forEach((button) => {
        expect(button).toBeDisabled();
      });

      await waitFor(() => {
        expect(screen.getByText("Stay Signed In")).toBeInTheDocument();
      });
    });

    test("handles extend session error gracefully", async () => {
      const consoleErrorSpy = vi
        .spyOn(console, "error")
        .mockImplementation(() => {});
      const onExtend = vi.fn().mockRejectedValue(new Error("Extend failed"));
      render(<SessionWarningDialog {...defaultProps} onExtend={onExtend} />);

      const staySignedInButton = screen.getByText("Stay Signed In");
      fireEvent.click(staySignedInButton);

      await waitFor(() => {
        expect(consoleErrorSpy).toHaveBeenCalledWith(
          "Failed to extend session:",
          expect.any(Error)
        );
      });

      expect(screen.getByText("Stay Signed In")).toBeInTheDocument();

      consoleErrorSpy.mockRestore();
    });
  });

  describe("Dialog Behavior", () => {
    test("disables escape key close", () => {
      render(<SessionWarningDialog {...defaultProps} />);

      const dialog = screen.getByRole("dialog");
      expect(dialog).toBeInTheDocument();

      fireEvent.keyDown(dialog, { key: "Escape", code: "Escape" });

      // onClose should not be called when escape is pressed
      expect(defaultProps.onClose).not.toHaveBeenCalled();
    });

    test("applies warning border styling", () => {
      render(<SessionWarningDialog {...defaultProps} />);

      const dialog = screen.getByRole("dialog");
      expect(dialog).toBeInTheDocument();
    });
  });

  describe("Time Formatting", () => {
    const timeTests = [
      { ms: 0, expected: "0:00" },
      { ms: 1000, expected: "0:01" },
      { ms: 59000, expected: "0:59" },
      { ms: 60000, expected: "1:00" },
      { ms: 61000, expected: "1:01" },
      { ms: 3661000, expected: "61:01" },
    ];

    timeTests.forEach(({ ms, expected }) => {
      test(`formats ${ms}ms as ${expected}`, () => {
        render(<SessionWarningDialog {...defaultProps} timeRemaining={ms} />);
        expect(screen.getByText(expected)).toBeInTheDocument();
      });
    });
  });

  describe("Component Lifecycle", () => {
    test("cleans up timers on unmount", () => {
      const { unmount } = render(<SessionWarningDialog {...defaultProps} />);

      unmount();

      // Advance timers after unmount - should not cause errors
      act(() => {
        vi.advanceTimersByTime(5000);
      });
    });

    test("handles rapid open/close cycles", () => {
      const { rerender } = render(
        <SessionWarningDialog {...defaultProps} open={false} />
      );

      rerender(<SessionWarningDialog {...defaultProps} open={true} />);
      rerender(<SessionWarningDialog {...defaultProps} open={false} />);
      rerender(<SessionWarningDialog {...defaultProps} open={true} />);

      expect(screen.getByText("Session Expiring Soon")).toBeInTheDocument();
    });
  });

  describe("Edge Cases", () => {
    test("handles zero time remaining", () => {
      render(<SessionWarningDialog {...defaultProps} timeRemaining={0} />);

      expect(screen.getByText("0:00")).toBeInTheDocument();
    });

    test("handles negative time remaining", () => {
      render(<SessionWarningDialog {...defaultProps} timeRemaining={-1000} />);

      expect(screen.getByText("0:00")).toBeInTheDocument();
    });

    test("handles very large time values", () => {
      render(
        <SessionWarningDialog {...defaultProps} timeRemaining={3600000} />
      );

      expect(screen.getByText("60:00")).toBeInTheDocument();
    });
  });
});
