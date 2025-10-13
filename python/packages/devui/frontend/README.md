# DevUI Frontend

## Build Instructions

```bash
cd frontend
yarn install

# Create .env.local with backend URL and Microsoft Entra settings
cat <<'EOF' > .env.local
VITE_API_BASE_URL=http://127.0.0.1:8080
VITE_AZURE_AD_CLIENT_ID=<your-app-client-id>
VITE_AZURE_AD_TENANT_ID=<your-tenant-id>
VITE_AZURE_AD_REDIRECT_URI=/auth/callback
VITE_AZURE_AD_POST_LOGOUT_REDIRECT_URI=/auth/callback
VITE_GRAPH_SCOPES=User.Read
VITE_AZURE_AD_API_SCOPES=api://<your-api-client-id>/.default
EOF

# Create .env.production (empty for relative URLs)
echo '' > .env.production

# Development
yarn dev

# Build (copies to backend)
yarn build
```

## Authentication Setup

This project now requires Microsoft Entra ID (Azure AD) authentication before accessing the UI. Follow these steps to configure it:

- Register a **Single Page Application** in the [Azure portal](https://entra.microsoft.com/).
- Add the following redirect URIs:
  - `http://localhost:5173` (development)
  - Any production origins you plan to deploy this UI to.
- Grant the **Microsoft Graph** delegated permission `User.Read`.
- Copy the values into `.env.local` as shown above. You can also set:
  - `VITE_AZURE_AD_AUTHORITY` if you need a custom authority URL (e.g., for national clouds or B2C).
  - `VITE_GRAPH_SCOPES` to request additional Graph scopes (comma or space separated).
  - `VITE_AZURE_AD_API_SCOPES` with the backend API scope(s) you expose (space or comma separated). Use an `.default` scope when consent is handled centrally.
- When `VITE_AZURE_AD_REDIRECT_URI` (and the logout equivalent) is set to a path such as `/auth/callback`, DevUI automatically prefixes it with the current browser origin, so you can run the UI on any port without editing the config.

On sign-in, the app requests a Microsoft identity token and silently retrieves both Microsoft Graph and backend API access tokens. Graph enables personalization, while the backend scope secures every DevUI API call automatically.

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default tseslint.config([
  globalIgnores(["dist"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      ...tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      ...tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      ...tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ["./tsconfig.node.json", "./tsconfig.app.json"],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
]);
```

You can also install [eslint-plugin-react-x](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://github.com/Rel1cx/eslint-react/tree/main/packages/plugins/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from "eslint-plugin-react-x";
import reactDom from "eslint-plugin-react-dom";

export default tseslint.config([
  globalIgnores(["dist"]),
  {
    files: ["**/*.{ts,tsx}"],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs["recommended-typescript"],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ["./tsconfig.node.json", "./tsconfig.app.json"],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
]);
```
