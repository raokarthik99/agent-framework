import { ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import signInLight from "@/assets/ms-symbollockup_signin_light.svg";
import signInDark from "@/assets/ms-symbollockup_signin_dark.svg";

interface SignInViewProps {
  onSignIn: () => void;
}

export function SignInView({ onSignIn }: SignInViewProps) {
  return (
    <div className="min-h-screen bg-background flex items-center justify-center px-6">
      <div className="w-full max-w-md space-y-8 text-center">
        <div className="flex justify-center">
          <div className="rounded-full bg-primary/10 p-4">
            <ShieldCheck className="h-10 w-10 text-primary" />
          </div>
        </div>

        <div className="space-y-2">
          <h1 className="text-2xl font-semibold text-foreground">
            Sign in to DevUI
          </h1>
          <p className="text-sm text-muted-foreground">
            Use your Microsoft Entra account to continue. We only request access
            to your basic profile to personalize the experience.
          </p>
        </div>

        <div className="space-y-3">
          <Button
            type="button"
            onClick={onSignIn}
            variant="ghost"
            aria-label="Sign in with Microsoft"
            className="flex w-full justify-center p-0 h-auto bg-transparent hover:bg-transparent focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-primary/60 cursor-pointer"
          >
            <img
              src={signInLight}
              alt=""
              aria-hidden="true"
              className="block dark:hidden w-full max-w-xs select-none"
              draggable={false}
            />
            <img
              src={signInDark}
              alt=""
              aria-hidden="true"
              className="hidden dark:block w-full max-w-xs select-none"
              draggable={false}
            />
          </Button>
          <p className="text-xs text-muted-foreground">
            You may be redirected to Microsoft to complete the sign-in flow.
          </p>
        </div>
      </div>
    </div>
  );
}
