import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MsalProvider } from "@azure/msal-react";
import "./index.css";
import App from "./App.tsx";
import { ThemeProvider } from "./components/theme-provider";
import { AuthGate } from "./components/auth/auth-gate";
import { msalInstance } from "./lib/auth/msal";

const container = document.getElementById("root");

if (!container) {
  throw new Error("Root container element with id 'root' was not found.");
}

const root = createRoot(container);

msalInstance
  .initialize()
  .then(() => {
    root.render(
      <StrictMode>
        <MsalProvider instance={msalInstance}>
          <ThemeProvider
            attribute="class"
            defaultTheme="dark"
            enableSystem
            disableTransitionOnChange
          >
            <AuthGate>
              <App />
            </AuthGate>
          </ThemeProvider>
        </MsalProvider>
      </StrictMode>
    );
  })
  .catch((error) => {
    console.error("Failed to initialize MSAL instance", error);
    root.render(
      <StrictMode>
        <div className="min-h-screen bg-background text-foreground flex items-center justify-center p-6">
          <div className="max-w-md text-center space-y-4">
            <h1 className="text-2xl font-semibold">
              Failed to start authentication
            </h1>
            <p className="text-muted-foreground text-sm">
              We couldn't initialize Microsoft sign-in. Check your environment
              variables and reload the page.
            </p>
          </div>
        </div>
      </StrictMode>
    );
  });
