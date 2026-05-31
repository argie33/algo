import { useState, useEffect } from "react";
import { Settings as SettingsIcon } from "lucide-react";
import { getSettings, updateSettings } from "../services/api";

const Settings = () => {
  const [tabIndex, setTabIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [settings, setSettings] = useState({});

  useEffect(() => {
    const loadSettings = async () => {
      setLoading(true);
      try {
        const settingsRes = await getSettings();
        setSettings(settingsRes?.data || settingsRes || {});
      } catch (err) {
        setError("Failed to load settings");
        console.error("Settings load error:", err);
      } finally {
        setLoading(false);
      }
    };

    loadSettings();
  }, []);

  const handleSaveGeneralSettings = async () => {
    try {
      setLoading(true);
      await updateSettings(settings);
      setMessage("Settings saved successfully!");
      setTimeout(() => setMessage(""), 3000);
    } catch (err) {
      setError("Failed to save settings");
      console.error("Error:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleNotificationChange = async (key, value) => {
    const updated = {
      ...settings,
      notifications: {
        ...(settings.notifications || {}),
        [key]: value,
      },
    };
    setSettings(updated);

    try {
      await updateSettings(updated);
      setMessage("Preferences updated!");
      setTimeout(() => setMessage(""), 3000);
    } catch (err) {
      setError("Failed to update preferences");
      console.error("Error:", err);
    }
  };

  if (loading && !settings.profile) {
    return (
      <div style={{
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        minHeight: "400px",
        color: 'var(--text-muted)',
      }}>
        <p>Loading settings...</p>
      </div>
    );
  }

  const profile = settings.profile || {};
  const notifications = settings.notifications || {};
  const tabs = [
    { label: "General Settings", id: 0 },
    { label: "Preferences", id: 1 },
    { label: "Account", id: 2 },
  ];

  return (
    <div style={{ maxWidth: '700px', width: '100%', margin: '0 auto', padding: 'var(--space-6)' }}>
      <div style={{ display: "flex", alignItems: "center", marginBottom: 'var(--space-6)', gap: 'var(--space-3)' }}>
        <SettingsIcon size={32} color="var(--text)" />
        <h1 style={{ margin: 0, fontSize: 'var(--t-2xl)', fontWeight: 'var(--w-bold)', color: 'var(--text)' }}>Settings</h1>
      </div>

      {message && (
        <div className="alert alert-success" style={{ marginBottom: 'var(--space-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{message}</span>
          <button onClick={() => setMessage("")} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 'var(--t-lg)', color: 'inherit' }}>×</button>
        </div>
      )}

      {error && (
        <div className="alert alert-danger" style={{ marginBottom: 'var(--space-4)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>{error}</span>
          <button onClick={() => setError("")} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 'var(--t-lg)', color: 'inherit' }}>×</button>
        </div>
      )}

      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        <div style={{
          display: 'flex',
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'var(--bg-2)',
        }}>
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setTabIndex(tab.id)}
              style={{
                flex: 1,
                padding: 'var(--space-3) var(--space-4)',
                border: 'none',
                background: tabIndex === tab.id ? 'var(--surface)' : 'transparent',
                color: tabIndex === tab.id ? 'var(--text)' : 'var(--text-2)',
                fontWeight: tabIndex === tab.id ? 'var(--w-semibold)' : 'var(--w-medium)',
                fontSize: 'var(--t-sm)',
                cursor: 'pointer',
                borderBottom: tabIndex === tab.id ? '2px solid var(--brand)' : 'none',
                transition: 'background var(--t-fast), color var(--t-fast)',
                marginBottom: '-1px',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div style={{ padding: 'var(--space-5)' }}>
          {/* General Settings Tab */}
          {tabIndex === 0 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 'var(--space-4)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                <label style={{ fontSize: 'var(--t-sm)', fontWeight: 'var(--w-medium)', color: 'var(--text)' }}>Theme</label>
                <select
                  value={settings.theme || "dark"}
                  onChange={(e) => setSettings({ ...settings, theme: e.target.value })}
                  className="input"
                >
                  <option value="light">Light</option>
                  <option value="dark">Dark</option>
                </select>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                <label style={{ fontSize: 'var(--t-sm)', fontWeight: 'var(--w-medium)', color: 'var(--text)' }}>Default View</label>
                <select
                  value={settings.defaultView || "market"}
                  onChange={(e) => setSettings({ ...settings, defaultView: e.target.value })}
                  className="input"
                >
                  <option value="market">Market Overview</option>
                  <option value="stocks">Stock Analysis</option>
                  <option value="economic">Economic Data</option>
                </select>
              </div>

              <div style={{ paddingTop: 'var(--space-3)' }}>
                <button
                  className="btn btn-primary"
                  onClick={handleSaveGeneralSettings}
                  disabled={loading}
                >
                  Save Settings
                </button>
              </div>
            </div>
          )}

          {/* Preferences Tab */}
          {tabIndex === 1 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 'var(--space-4)' }}>
              <div className="soitem" style={{ borderBottom: 'none', padding: 0 }}>
                <div style={{ flex: 1 }}>
                  <div className="soitem-label">Email Notifications</div>
                  <div className="soitem-sub">Receive email alerts for important updates</div>
                </div>
                <label style={{
                  position: 'relative',
                  display: 'inline-flex',
                  alignItems: 'center',
                  width: '44px',
                  height: '24px',
                  backgroundColor: notifications.email ? 'var(--brand)' : 'var(--border-2)',
                  borderRadius: 'var(--r-pill)',
                  cursor: 'pointer',
                  transition: 'background var(--t-fast)',
                }}>
                  <input
                    type="checkbox"
                    checked={notifications.email || false}
                    onChange={(e) => handleNotificationChange("email", e.target.checked)}
                    style={{ display: 'none' }}
                  />
                  <div style={{
                    position: 'absolute',
                    width: '20px',
                    height: '20px',
                    backgroundColor: '#fff',
                    borderRadius: '50%',
                    left: notifications.email ? '2px' : '22px',
                    transition: 'left var(--t-fast)',
                  }} />
                </label>
              </div>

              <div className="soitem" style={{ borderBottom: 'none', padding: 0, marginTop: 'var(--space-3)' }}>
                <div style={{ flex: 1 }}>
                  <div className="soitem-label">Push Notifications</div>
                  <div className="soitem-sub">Browser push notifications for trades</div>
                </div>
                <label style={{
                  position: 'relative',
                  display: 'inline-flex',
                  alignItems: 'center',
                  width: '44px',
                  height: '24px',
                  backgroundColor: notifications.push ? 'var(--brand)' : 'var(--border-2)',
                  borderRadius: 'var(--r-pill)',
                  cursor: 'pointer',
                  transition: 'background var(--t-fast)',
                }}>
                  <input
                    type="checkbox"
                    checked={notifications.push || false}
                    onChange={(e) => handleNotificationChange("push", e.target.checked)}
                    style={{ display: 'none' }}
                  />
                  <div style={{
                    position: 'absolute',
                    width: '20px',
                    height: '20px',
                    backgroundColor: '#fff',
                    borderRadius: '50%',
                    left: notifications.push ? '2px' : '22px',
                    transition: 'left var(--t-fast)',
                  }} />
                </label>
              </div>

              <div className="soitem" style={{ borderBottom: 'none', padding: 0, marginTop: 'var(--space-3)' }}>
                <div style={{ flex: 1 }}>
                  <div className="soitem-label">Trading Alerts</div>
                  <div className="soitem-sub">Notifications when trades are executed</div>
                </div>
                <label style={{
                  position: 'relative',
                  display: 'inline-flex',
                  alignItems: 'center',
                  width: '44px',
                  height: '24px',
                  backgroundColor: notifications.alerts ? 'var(--brand)' : 'var(--border-2)',
                  borderRadius: 'var(--r-pill)',
                  cursor: 'pointer',
                  transition: 'background var(--t-fast)',
                }}>
                  <input
                    type="checkbox"
                    checked={notifications.alerts || false}
                    onChange={(e) => handleNotificationChange("alerts", e.target.checked)}
                    style={{ display: 'none' }}
                  />
                  <div style={{
                    position: 'absolute',
                    width: '20px',
                    height: '20px',
                    backgroundColor: '#fff',
                    borderRadius: '50%',
                    left: notifications.alerts ? '2px' : '22px',
                    transition: 'left var(--t-fast)',
                  }} />
                </label>
              </div>

              <div style={{ paddingTop: 'var(--space-2)' }}>
                <p style={{ margin: 0, fontSize: 'var(--t-2xs)', color: 'var(--text-muted)' }}>Changes are automatically saved</p>
              </div>
            </div>
          )}

          {/* Account Tab */}
          {tabIndex === 2 && (
            <div style={{ display: "flex", flexDirection: "column", gap: 'var(--space-4)' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-4)' }}>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                  <label style={{ fontSize: 'var(--t-sm)', fontWeight: 'var(--w-medium)', color: 'var(--text)' }}>First Name</label>
                  <input
                    type="text"
                    className="input"
                    value={profile.firstName || ""}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        profile: { ...profile, firstName: e.target.value },
                      })
                    }
                  />
                </div>

                <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                  <label style={{ fontSize: 'var(--t-sm)', fontWeight: 'var(--w-medium)', color: 'var(--text)' }}>Last Name</label>
                  <input
                    type="text"
                    className="input"
                    value={profile.lastName || ""}
                    onChange={(e) =>
                      setSettings({
                        ...settings,
                        profile: { ...profile, lastName: e.target.value },
                      })
                    }
                  />
                </div>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
                <label style={{ fontSize: 'var(--t-sm)', fontWeight: 'var(--w-medium)', color: 'var(--text)' }}>Email</label>
                <input
                  type="email"
                  className="input"
                  value={profile.email || ""}
                  disabled
                  style={{ opacity: 0.6, cursor: 'not-allowed' }}
                />
                <p style={{ margin: 'var(--space-1) 0 0 0', fontSize: 'var(--t-2xs)', color: 'var(--text-muted)' }}>Email cannot be changed</p>
              </div>

              <div style={{ paddingTop: 'var(--space-3)' }}>
                <button
                  className="btn btn-primary"
                  onClick={handleSaveGeneralSettings}
                  disabled={loading}
                >
                  Save Profile
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default Settings;

