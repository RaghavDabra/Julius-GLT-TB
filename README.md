# Julius GLT-TB — General Ledger & Trial Balance Analysis Platform

![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)
![React](https://img.shields.io/badge/React-18-61dafb.svg)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178c6.svg)
![Vite](https://img.shields.io/badge/Vite-5-646cff.svg)

A data-analysis platform for working with **General Ledger (GL)** and **Trial
Balance (TB)** data. It pairs a React + TypeScript frontend (Vite, MUI, Tailwind,
Chart.js / Recharts) with a Python API backend so accounting exports can be
uploaded, cleaned, analysed and visualised in the browser.

> This is a sibling project to
> [LedgerLens](https://github.com/RaghavDabra/Julius-Financial-Ledger) and shares its
> chart-driven, upload-and-analyse approach to ledger data.

## Features

- **File upload & ingestion** — drag-and-drop CSV/data files via `react-dropzone`
  into the analysis backend.
- **Interactive dashboards** — charts and tables built with Chart.js
  (`react-chartjs-2`) and Recharts, styled with MUI and Tailwind.
- **Markdown-rendered insights** — analysis output rendered with `react-markdown`
  + `remark-gfm`.
- **Python analysis API** — the `api/` service performs the data processing the UI
  requests over HTTP (`axios`), with data-fetching managed by `react-query`.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, TypeScript, Vite |
| UI | MUI (Material UI), Tailwind CSS, Emotion |
| Charts | Chart.js (`react-chartjs-2`), Recharts |
| Data fetching | `react-query`, `axios` |
| Backend | Python API (`api/`), see `requirements.txt` |

## Getting started

### Prerequisites

- Node.js 18+ and npm
- Python 3.10+ (for the `api/` backend)

### Frontend

```bash
# install dependencies
npm install

# start the dev server (http://localhost:5173)
npm run dev
```

### Backend (API)

```bash
# from the repository root
pip install -r requirements.txt

# run the API service (see the api/ directory for the entry point)
python api/app.py
```

### Build for production

```bash
npm run build     # type-checks then builds to dist/
npm run preview   # preview the production build
```

## Project layout

```
api/            Python analysis backend
src/            React + TypeScript frontend (components, views)
index.html      Vite entry point
requirements.txt  Python dependencies
package.json    frontend dependencies & scripts
```

## License

Released under the [MIT License](./LICENSE). © 2026 Raghav Dabra.

## Author

Built by [Raghav Dabra](https://github.com/RaghavDabra).
