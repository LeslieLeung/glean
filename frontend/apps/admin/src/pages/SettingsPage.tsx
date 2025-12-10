import React, { useEffect, useState } from 'react';
import api from '../lib/api';
import { Card, CardHeader, CardContent, CardTitle, CardDescription, Label, Switch, Alert, AlertTitle, AlertDescription } from '@glean/ui';
import { AlertCircle, Loader2 } from 'lucide-react';

export const SettingsPage: React.FC = () => {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [registrationEnabled, setRegistrationEnabled] = useState(true);
  const [updating, setUpdating] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      setLoading(true);
      const response = await api.get('/settings/registration');
      setRegistrationEnabled(response.data.enabled);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch settings:', err);
      setError('Failed to load settings');
    } finally {
      setLoading(false);
    }
  };

  const handleRegistrationToggle = async (checked: boolean) => {
    try {
      setUpdating(true);
      await api.post(`/settings/registration?enabled=${checked}`);
      setRegistrationEnabled(checked);
      setError(null);
    } catch (err) {
      console.error('Failed to update setting:', err);
      setError('Failed to update registration setting');
      // Revert switch state
      setRegistrationEnabled(!checked);
    } finally {
      setUpdating(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col overflow-hidden">
      {/* Header */}
      <div className="border-b border-border bg-card px-8 py-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-foreground">System Settings</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Manage global configuration for your Glean instance.
            </p>
          </div>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-8">
        <div className="max-w-4xl space-y-8">
          {error && (
            <Alert variant="error">
              <AlertCircle className="h-4 w-4" />
              <AlertTitle>Error</AlertTitle>
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          <Card>
            <CardHeader>
              <CardTitle>User Registration</CardTitle>
              <CardDescription>
                Control whether new users can sign up for an account. Existing users will still be able to log in.
              </CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-between space-x-2">
              <Label htmlFor="registration-mode" className="items-start flex flex-col space-y-1">
                <span>Enable Registration</span>
                <span className="font-normal text-muted-foreground">
                  {registrationEnabled ? "New users can sign up." : "Sign up is disabled."}
                </span>
              </Label>
              <Switch
                id="registration-mode"
                checked={registrationEnabled}
                onCheckedChange={handleRegistrationToggle}
                disabled={updating}
              />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
};
