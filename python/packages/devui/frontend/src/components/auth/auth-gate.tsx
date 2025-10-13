import { useEffect, useMemo, useState } from "react";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import {
  InteractionRequiredAuthError,
  InteractionStatus,
} from "@azure/msal-browser";
import type { PropsWithChildren } from "react";
import { LoadingState } from "@/components/ui/loading-state";
import { apiScopes, loginRequest } from "@/lib/auth/msal";
import { apiClient } from "@/services/api";
import { SignInView } from "./sign-in-view";
import { getStoredLoginHint, storeLoginHint } from "@/lib/auth/storage";

export function AuthGate({ children }: PropsWithChildren) {
  const isAuthenticated = useIsAuthenticated();
  const { instance, accounts, inProgress } = useMsal();
  const [apiSessionReady, setApiSessionReady] = useState(
    apiScopes.length === 0
  );
  const [storedLoginHint, setStoredLoginHint] = useState<string | null>(() =>
    getStoredLoginHint()
  );
  const [attemptedSso, setAttemptedSso] = useState(false);
  const [silentLoginLoading, setSilentLoginLoading] = useState(false);
  const activeAccountId = useMemo(
    () =>
      instance.getActiveAccount()?.homeAccountId ??
      accounts[0]?.homeAccountId ??
      null,
    [accounts, instance]
  );

  useEffect(() => {
    const activeAccount = instance.getActiveAccount();
    if (!activeAccount && accounts.length > 0) {
      instance.setActiveAccount(accounts[0]);
    }
  }, [accounts, instance]);

  useEffect(() => {
    const activeAccount = instance.getActiveAccount();
    if (activeAccount?.username) {
      storeLoginHint(activeAccount.username);
      setStoredLoginHint(activeAccount.username);
    }
  }, [activeAccountId, instance]);

  const apiScopesKey = apiScopes.join("|");

  useEffect(() => {
    if (!isAuthenticated || apiScopes.length === 0) {
      apiClient.clearAuthProvider();
      setApiSessionReady(true);
      return;
    }

    if (inProgress !== InteractionStatus.None) {
      setApiSessionReady(false);
      return;
    }

    const authProvider = async () => {
      if (apiScopes.length === 0) {
        return null;
      }

      const account = instance.getActiveAccount();
      if (!account) {
        throw new Error(
          "No active Microsoft Entra account is available for API authentication."
        );
      }

      try {
        const result = await instance.acquireTokenSilent({
          account,
          scopes: apiScopes,
        });
        return result.accessToken;
      } catch (error) {
        if (error instanceof InteractionRequiredAuthError) {
          await instance.acquireTokenRedirect({
            account,
            scopes: apiScopes,
          });
          return null;
        }
        throw error;
      }
    };

    apiClient.setAuthProvider(authProvider);
    setApiSessionReady(true);
    return () => {
      setApiSessionReady(apiScopes.length === 0);
      apiClient.clearAuthProvider(authProvider);
    };
  }, [
    accounts.length,
    activeAccountId,
    apiScopesKey,
    inProgress,
    instance,
    isAuthenticated,
  ]);

  useEffect(() => {
    if (isAuthenticated) {
      setAttemptedSso(true);
      setSilentLoginLoading(false);
      return;
    }

    if (attemptedSso) {
      return;
    }

    if (inProgress !== InteractionStatus.None) {
      return;
    }

    if (!storedLoginHint) {
      setAttemptedSso(true);
      return;
    }

    let cancelled = false;
    setSilentLoginLoading(true);

    instance
      .ssoSilent({
        ...loginRequest,
        authority: instance.getConfiguration().auth.authority,
        redirectUri: instance.getConfiguration().auth.redirectUri,
        loginHint: storedLoginHint,
      })
      .then((result) => {
        if (cancelled) {
          return;
        }
        if (result.account) {
          instance.setActiveAccount(result.account);
        }
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }

        if (error instanceof InteractionRequiredAuthError) {
          // Silent SSO not available; fall back to interactive login.
        } else {
          console.warn("Silent SSO failed", error);
        }
      })
      .finally(() => {
        if (cancelled) {
          return;
        }
        setSilentLoginLoading(false);
        setAttemptedSso(true);
      });

    return () => {
      cancelled = true;
    };
  }, [
    attemptedSso,
    inProgress,
    instance,
    isAuthenticated,
    storedLoginHint,
  ]);

  if (isAuthenticated && !apiSessionReady) {
    return (
      <LoadingState
        message="Preparing secure session..."
        description="Negotiating Microsoft Entra access for the DevUI backend."
        fullPage
      />
    );
  }

  if (inProgress !== InteractionStatus.None) {
    return (
      <LoadingState
        message="Signing you in..."
        description="Completing the Microsoft Entra sign-in flow."
        fullPage
      />
    );
  }

  if (!isAuthenticated) {
    if (!attemptedSso || silentLoginLoading) {
      return (
        <LoadingState
          message="Looking for an existing Microsoft session..."
          description="Checking if you already have an active sign-in."
          fullPage
        />
      );
    }

    const handleSignIn = () => instance.loginRedirect(loginRequest);
    return <SignInView onSignIn={handleSignIn} />;
  }

  return <>{children}</>;
}
