# Two-minute demo script

## Preparation

Run the app, open `http://127.0.0.1:8000`, and keep `/docs` in another tab. Use a fresh email address for the recording.

## Walkthrough

1. **0:00–0:15:** Introduce Stockroom as a production-ready REST API with a small client. State that the walkthrough covers authentication, CRUD, role control, and the API contract.
2. **0:15–0:35:** Register a workspace. Point out that the dashboard is a new, private workspace.
3. **0:35–1:05:** Add “Field notebook,” SKU `NOTE-A5-CRM`, category “Stationery,” quantity 16, price 12.99, reorder point 6. Show the product, metrics, and audit entry. Add a second product with quantity 2 to show low stock.
4. **1:05–1:25:** Edit the notebook quantity to 4, show its low-stock label, filter to low stock, and export the inventory CSV.
5. **1:25–1:45:** In Settings, add a Viewer. Explain owner, editor, and viewer capabilities and that every query is scoped to its workspace.
6. **1:45–2:00:** Open `/docs`, show the authentication, inventory, workspace, and health endpoint groups. Mention Argon2 hashing, opaque bearer tokens or HttpOnly cookies, validation, limits, audit events, migrations, tests, and Docker configuration.

## Closing line

“The repository includes the implementation, migrations, tests, deployment configuration, and this walkthrough. Thank you.”
