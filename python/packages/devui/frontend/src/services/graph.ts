import type { AccountInfo } from "@azure/msal-browser";
import { InteractionType } from "@azure/msal-browser";
import { Client, ResponseType } from "@microsoft/microsoft-graph-client";
import { AuthCodeMSALBrowserAuthenticationProvider } from "@microsoft/microsoft-graph-client/authProviders/authCodeMsalBrowser";
import type { GraphError } from "@microsoft/microsoft-graph-client";
import type { User } from "@microsoft/microsoft-graph-types";
import { graphScopes, msalInstance } from "@/lib/auth/msal";

const createAuthProvider = (account: AccountInfo) =>
  new AuthCodeMSALBrowserAuthenticationProvider(msalInstance, {
    account,
    scopes: graphScopes,
    interactionType: InteractionType.Popup,
  });

export const createGraphClient = (account: AccountInfo) =>
  Client.initWithMiddleware({
    authProvider: createAuthProvider(account),
  });

export async function getUserProfile(account: AccountInfo): Promise<User> {
  const client = createGraphClient(account);
  return client.api("/me").get();
}

export async function getUserPhoto(account: AccountInfo): Promise<Blob | null> {
  const client = createGraphClient(account);
  try {
    const blob = (await client
      .api("/me/photo/$value")
      .responseType(ResponseType.BLOB)
      .get()) as Blob;
    return blob instanceof Blob ? blob : new Blob([blob]);
  } catch (error) {
    const statusCode =
      typeof (error as GraphError)?.statusCode === "number"
        ? (error as GraphError).statusCode
        : typeof (error as { statusCode?: number })?.statusCode === "number"
        ? (error as { statusCode?: number }).statusCode
        : undefined;
    if (statusCode === 404) {
      return null;
    }
    throw error;
  }
}
