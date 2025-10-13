const LOGIN_HINT_STORAGE_KEY = "devui_msal_login_hint";

const hasWindow = typeof window !== "undefined";

export const getStoredLoginHint = (): string | null => {
  if (!hasWindow) {
    return null;
  }
  try {
    return window.localStorage.getItem(LOGIN_HINT_STORAGE_KEY);
  } catch (error) {
    console.warn("Unable to read login hint from storage", error);
    return null;
  }
};

export const storeLoginHint = (loginHint: string) => {
  if (!hasWindow) {
    return;
  }
  try {
    window.localStorage.setItem(LOGIN_HINT_STORAGE_KEY, loginHint);
  } catch (error) {
    console.warn("Unable to persist login hint", error);
  }
};

export const clearStoredLoginHint = () => {
  if (!hasWindow) {
    return;
  }
  try {
    window.localStorage.removeItem(LOGIN_HINT_STORAGE_KEY);
  } catch (error) {
    console.warn("Unable to clear login hint", error);
  }
};

export { LOGIN_HINT_STORAGE_KEY };
