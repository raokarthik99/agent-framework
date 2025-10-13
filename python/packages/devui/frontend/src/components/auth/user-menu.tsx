import { useEffect, useMemo, useState } from "react";
import { useMsal } from "@azure/msal-react";
import type { AccountInfo } from "@azure/msal-browser";
import type { User } from "@microsoft/microsoft-graph-types";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { LogOut, User as UserIcon } from "lucide-react";
import { getUserPhoto, getUserProfile } from "@/services/graph";
import { clearStoredLoginHint } from "@/lib/auth/storage";

interface ProfileState {
  account?: AccountInfo;
  profile?: User;
  loading: boolean;
  error?: string;
}

interface PhotoState {
  accountId?: string;
  url?: string;
  loading: boolean;
  error?: string;
}

const getInitials = (input?: string) => {
  if (!input) {
    return "ME";
  }

  const parts = input.trim().split(/\s+/);
  if (parts.length === 1) {
    return parts[0].slice(0, 2).toUpperCase();
  }

  return (
    parts[0].charAt(0).toUpperCase() + parts[parts.length - 1].charAt(0).toUpperCase()
  );
};

export function UserMenu() {
  const { instance, accounts } = useMsal();
  const [profileState, setProfileState] = useState<ProfileState>({
    loading: false,
  });
  const [photoState, setPhotoState] = useState<PhotoState>({ loading: false });

  const activeAccount = useMemo<AccountInfo | null>(() => {
    const current = instance.getActiveAccount();
    return current ?? accounts[0] ?? null;
  }, [accounts, instance]);

  useEffect(() => {
    if (!activeAccount) {
      setProfileState({ account: undefined, profile: undefined, loading: false });
      setPhotoState((prev) => {
        if (prev.url && prev.url.startsWith("blob:")) {
          URL.revokeObjectURL(prev.url);
        }
        return { accountId: undefined, url: undefined, loading: false };
      });
      return;
    }

    const current = instance.getActiveAccount();
    if (!current || current.homeAccountId !== activeAccount.homeAccountId) {
      instance.setActiveAccount(activeAccount);
    }
  }, [activeAccount, instance]);

  useEffect(() => {
    if (!activeAccount) {
      setProfileState({ account: undefined, profile: undefined, loading: false });
      return;
    }

    let cancelled = false;

    setProfileState((prev) => {
      if (
        prev.account?.homeAccountId === activeAccount.homeAccountId &&
        (prev.loading || prev.profile)
      ) {
        return prev;
      }

      return {
        account: activeAccount,
        profile:
          prev.account?.homeAccountId === activeAccount.homeAccountId
            ? prev.profile
            : undefined,
        loading: true,
        error: undefined,
      };
    });

    getUserProfile(activeAccount)
      .then((profile) => {
        if (cancelled) {
          return;
        }
        setProfileState({
          account: activeAccount,
          profile,
          loading: false,
          error: undefined,
        });
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }
        setProfileState({
          account: activeAccount,
          profile: undefined,
          loading: false,
          error:
            error instanceof Error
              ? error.message
              : "Failed to load profile information.",
        });
      });

    return () => {
      cancelled = true;
    };
  }, [activeAccount?.homeAccountId]);

  useEffect(() => {
    if (!activeAccount) {
      setPhotoState({ accountId: undefined, url: undefined, loading: false });
      return;
    }

    let cancelled = false;
    let objectUrl: string | undefined;
    let previousUrl: string | undefined;

    setPhotoState((prev) => {
      if (prev.accountId === activeAccount.homeAccountId) {
        previousUrl = prev.url;
        return {
          accountId: activeAccount.homeAccountId,
          url: prev.url,
          loading: true,
          error: undefined,
        };
      }
      previousUrl = prev.url;
      if (
        previousUrl &&
        previousUrl.startsWith("blob:")
      ) {
        URL.revokeObjectURL(previousUrl);
        previousUrl = undefined;
      }
      return {
        accountId: activeAccount.homeAccountId,
        url: undefined,
        loading: true,
        error: undefined,
      };
    });

    getUserPhoto(activeAccount)
      .then((photo) => {
        if (cancelled) {
          return;
        }

        if (!photo) {
          setPhotoState({
            accountId: activeAccount.homeAccountId,
            url: undefined,
            loading: false,
            error: undefined,
          });
        if (
          previousUrl &&
          previousUrl.startsWith("blob:")
        ) {
          URL.revokeObjectURL(previousUrl);
          previousUrl = undefined;
        }
        return;
      }

        objectUrl = URL.createObjectURL(photo);
        setPhotoState({
          accountId: activeAccount.homeAccountId,
          url: objectUrl,
          loading: false,
          error: undefined,
        });
        if (
          previousUrl &&
          previousUrl !== objectUrl &&
          previousUrl.startsWith("blob:")
        ) {
          URL.revokeObjectURL(previousUrl);
          previousUrl = undefined;
        }
      })
      .catch((error) => {
        if (cancelled) {
          return;
        }

        const statusCode =
          typeof (error as { statusCode?: number })?.statusCode === "number"
            ? (error as { statusCode?: number }).statusCode
            : undefined;

        if (statusCode === 404) {
          setPhotoState({
            accountId: activeAccount.homeAccountId,
            url: undefined,
            loading: false,
            error: undefined,
          });
        if (
          previousUrl &&
          previousUrl.startsWith("blob:")
        ) {
          URL.revokeObjectURL(previousUrl);
          previousUrl = undefined;
        }
        return;
        }

        console.warn("Failed to load profile photo", error);
        setPhotoState({
          accountId: activeAccount.homeAccountId,
          url: undefined,
          loading: false,
          error:
            error instanceof Error
              ? error.message
              : "Failed to load profile photo.",
        });
        if (
          previousUrl &&
          previousUrl.startsWith("blob:")
        ) {
          URL.revokeObjectURL(previousUrl);
          previousUrl = undefined;
        }
      });

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [activeAccount?.homeAccountId]);

  if (!activeAccount) {
    return null;
  }

  const { profile, loading, error } = profileState;
  const { url: photoUrl, loading: photoLoading } = photoState;
  const displayName =
    profile?.displayName ?? activeAccount.name ?? activeAccount.username;
  const email = profile?.mail ?? profile?.userPrincipalName ?? activeAccount.username;
  const initials = loading ? null : getInitials(displayName);

  const handleSignOut = () => {
    clearStoredLoginHint();
    instance.logoutRedirect({ account: activeAccount });
  };

  const showSpinner = (loading || photoLoading) && !photoUrl;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="gap-2 px-2 py-1.5 h-9 rounded-full border border-border/60"
        >
          <span className="relative flex h-7 w-7 items-center justify-center overflow-hidden rounded-full border border-border/60 bg-primary/5 text-xs font-semibold text-foreground">
            {photoUrl ? (
              <img
                src={photoUrl}
                alt=""
                aria-hidden="true"
                className="h-full w-full object-cover"
                draggable={false}
              />
            ) : showSpinner ? (
              <LoadingSpinner size="sm" className="text-primary" />
            ) : (
              initials ?? <UserIcon className="h-4 w-4" />
            )}
          </span>
          <span className="max-w-[140px] truncate text-sm font-medium text-foreground">
            {displayName}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="flex flex-col items-start gap-0.5">
          <span className="text-sm font-semibold text-foreground">
            {displayName}
          </span>
          {email && (
            <span className="text-xs text-muted-foreground truncate">{email}</span>
          )}
        </DropdownMenuLabel>
        {error && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuItem disabled className="text-xs text-destructive">
              {error}
            </DropdownMenuItem>
          </>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleSignOut}>
          <LogOut className="h-4 w-4" />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
