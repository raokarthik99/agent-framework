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

export function AuthGate({ children }: PropsWithChildren) {
  const isAuthenticated = useIsAuthenticated();
  const { instance, accounts, inProgress } = useMsal();
  const [apiSessionReady, setApiSessionReady] = useState(
    apiScopes.length === 0
  );

  useEffect(() => {
    const activeAccount = instance.getActiveAccount();
    if (!activeAccount && accounts.length > 0) {
      instance.setActiveAccount(accounts[0]);
    }
  }, [accounts, instance]);

  const activeAccountId = useMemo(
    () =>
      instance.getActiveAccount()?.homeAccountId ??
      accounts[0]?.homeAccountId ??
      null,
    [accounts, instance]
  );
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
    const handleSignIn = () => instance.loginRedirect(loginRequest);
    return <SignInView onSignIn={handleSignIn} />;
  }

  return <>{children}</>;
}
