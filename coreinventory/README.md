# CoreInventory

A modular Inventory Management System (IMS) built for hackathon use.

## Features
- Signup/Login + OTP password reset
- Inventory dashboard with KPI cards and dynamic filters
- Product management (SKU, category, UOM, reorder level)
- Receipts, Deliveries, Internal Transfers, Stock Adjustments
- Multi-warehouse and location-level stock tracking
- Immutable stock ledger and movement history
- Profile view and logout

## Quick Start
1. Create and activate a virtual environment (recommended):
    - Windows PowerShell:
       - `python -m venv .venv`
       - `.\.venv\Scripts\Activate.ps1`
2. Install dependencies:
    - `pip install -r requirements.txt`
3. Run server:
    - `uvicorn app.main:app --reload`
4. Open:
    - `http://127.0.0.1:8000`

## What is Included
- Authentication:
   - Signup / Login / Logout
   - OTP-based password reset (demo OTP shown in response + server log)
- Dashboard:
   - KPI cards
   - Dynamic filters (document type, status, warehouse, category)
   - Recent movements
   - Low-stock alert table
- Products:
   - Create/update products
   - SKU search + category filter
   - Stock availability per location
   - Reorder level support
- Operations:
   - Receipts (incoming)
   - Delivery Orders (outgoing)
   - Internal Transfers
   - Inventory Adjustments
   - Validate/cancel workflow
- Move History:
   - Immutable stock ledger
- Settings:
   - Warehouses
   - Locations
   - Categories
- Profile:
   - My profile
   - Logout

## Default Seed Data
On first startup, the app auto-creates:
- Warehouse: `Main Warehouse`
- Location: `Main Store` (`MAIN-STORE`)
- Category: `General`

## Demo Note
For OTP reset in hackathon/demo mode, the generated OTP is returned in API response and printed in server logs.
