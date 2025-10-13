import { LogLevel, PublicClientApplication } from "@azure/msal-browser";

const isBrowser = typeof window !== "undefined";

const requireEnv = (key: keyof ImportMetaEnv & string): string => {
  const value = import.meta.env[key];
  if (!value) {
    throw new Error(`Missing required environment variable: ${key}`);
  }
  return value;
};

const resolveAuthority = (): string => {
  const explicitAuthority = import.meta.env.VITE_AZURE_AD_AUTHORITY;
  if (explicitAuthority) {
    return explicitAuthority;
  }

  const tenantId = import.meta.env.VITE_AZURE_AD_TENANT_ID;
  if (!tenantId) {
    throw new Error(
      "Either VITE_AZURE_AD_AUTHORITY or VITE_AZURE_AD_TENANT_ID must be provided."
    );
  }

  return `https://login.microsoftonline.com/${tenantId}`;
};

type ResolveUriOptions = {
  fallback?: string;
  relativeTo?: string;
};

const resolveUri = (
  key: keyof ImportMetaEnv & string,
  { fallback, relativeTo }: ResolveUriOptions = {}
): string => {
  const configured = import.meta.env[key];

  const toAbsolute = (value: string): string => {
    try {
      return new URL(value).toString();
    } catch {
      if (!relativeTo) {
        throw new Error(
          `Unable to resolve relative URI "${value}" for ${key}. Provide an absolute URL or ensure a browser origin is available.`
        );
      }
      return new URL(value, relativeTo).toString();
    }
  };

  if (configured) {
    return toAbsolute(configured);
  }

  if (fallback) {
    return toAbsolute(fallback);
  }

  throw new Error(
    `Unable to determine value for ${key}. Set it explicitly in your environment.`
  );
};

const parseScopes = (value: string | undefined, fallback: string[] = []): string[] =>
  value
    ? value
        .split(/[ ,]+/)
        .map((scope) => scope.trim())
        .filter(Boolean)
    : fallback;

const browserOrigin = isBrowser ? window.location.origin : undefined;

const clientId = requireEnv("VITE_AZURE_AD_CLIENT_ID");
const authority = resolveAuthority();
const redirectUri = resolveUri("VITE_AZURE_AD_REDIRECT_URI", {
  fallback: "/auth/callback",
  relativeTo: browserOrigin,
});
const postLogoutRedirectUri = resolveUri(
  "VITE_AZURE_AD_POST_LOGOUT_REDIRECT_URI",
  {
    fallback: redirectUri,
    relativeTo: browserOrigin,
  }
);

export const graphScopes = parseScopes(import.meta.env.VITE_GRAPH_SCOPES, [
  "User.Read",
]);
export const apiScopes = parseScopes(import.meta.env.VITE_AZURE_AD_API_SCOPES, []);

export const loginRequest = {
  scopes: graphScopes,
};

export const msalInstance = new PublicClientApplication({
  auth: {
    clientId,
    authority,
    redirectUri,
    postLogoutRedirectUri,
  },
  cache: {
    cacheLocation: "sessionStorage",
    storeAuthStateInCookie:
      isBrowser &&
      (window.navigator.userAgent.includes("MSIE") ||
        window.navigator.userAgent.includes("Trident")),
  },
  system: {
    loggerOptions: {
      logLevel: LogLevel.Warning,
      loggerCallback(level, message, containsPii) {
        if (containsPii) {
          return;
        }
        if (level === LogLevel.Error) {
          console.error(message);
        } else if (level === LogLevel.Warning) {
          console.warn(message);
        }
      },
    },
  },
});
