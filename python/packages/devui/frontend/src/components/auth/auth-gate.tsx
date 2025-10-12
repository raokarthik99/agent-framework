import { useEffect } from "react";
import { useIsAuthenticated, useMsal } from "@azure/msal-react";
import { InteractionStatus } from "@azure/msal-browser";
import type { PropsWithChildren } from "react";
import { LoadingState } from "@/components/ui/loading-state";
import { loginRequest } from "@/lib/auth/msal";
import { SignInView } from "./sign-in-view";

export function AuthGate({ children }: PropsWithChildren) {
  const isAuthenticated = useIsAuthenticated();
  const { instance, accounts, inProgress } = useMsal();

  useEffect(() => {
    const activeAccount = instance.getActiveAccount();
    if (!activeAccount && accounts.length > 0) {
      instance.setActiveAccount(accounts[0]);
    }
  }, [accounts, instance]);

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
